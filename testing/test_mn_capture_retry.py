"""Recorded organization inputs, synthetic page/timing conditions; no live searches."""
import io,json,os,socket,subprocess,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
from playwright.sync_api import TimeoutError as PWTimeout
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deployment import state_snapshots as s

OUT=Path(os.environ.get('CC_MN_TEST_OUTPUT',tempfile.gettempdir()))
CASES=json.loads((Path(__file__).parent/'fixtures/mn-capture-retry.json').read_text())['cases']
old=subprocess.check_output(['git','show','081780b:deployment/state_snapshots.py'],cwd=Path(__file__).parents[1]).decode('utf8')
baseline=types.ModuleType('mn_capture_baseline');exec(compile(old,'baseline-state-snapshots.py','exec'),baseline.__dict__)

class Clock:
    def __init__(self):self.now=100.
    def tick(self,n):self.now+=n
    def read(self):return self.now

class Page:
    def __init__(self,org,clock,actions=('ok',),state='MN'):
        self.clock=clock;self.url='https://'+sorted(s.OFFICIAL_HOSTS[state])[0]+'/public-record'
        self.text=org['name']+' 12345 EIN '+s.digits(org['ein'])+' Status Registered'
        self.actions=list(actions);self.calls=[];self.reads=0
        im=Image.new('RGB',(900,500),'white');d=ImageDraw.Draw(im)
        d.text((20,30),'SYNTHETIC LOCAL CAPTURE FIXTURE - NOT STATE EVIDENCE',fill='black')
        d.text((20,70),self.text,fill='black');b=io.BytesIO();im.save(b,format='JPEG');self.raw=b.getvalue()
    def locator(self,_):return self
    def evaluate(self,*args,**kwargs):return {'width':900,'height':500}
    def inner_text(self,*args,**kwargs):
        self.reads+=1
        if getattr(self,'change_after',None)==self.reads:self.text='Different organization 999999999'
        return self.text
    def screenshot(self,**kwargs):
        self.calls.append(kwargs);action=self.actions.pop(0)
        if action=='ok':self.clock.tick(.05);return self.raw
        if action=='late_ok':self.clock.tick(4);return self.raw
        if action=='error':raise RuntimeError('Page closed')
        self.clock.tick(kwargs['timeout']/1000+.02)
        if action=='navigate':self.url+='-changed'
        if action=='text':self.text='Different organization 999999999'
        raise PWTimeout('Synthetic screenshot timeout')

def capture(module,org,actions=('ok',),state='MN',deadline=400.,stop=None,change_after=None):
    clock=Clock();page=Page(org,clock,actions,state);page.change_after=change_after
    run=module.CaptureRun(org['name'],org['ein'],state)
    if stop is not None:run.page_capture_stop=stop
    token=module.DEADLINE.set(deadline)
    try:
        with patch.object(module.time,'monotonic',clock.read),patch.object(module.time,'perf_counter',clock.read),patch.object(module.time,'time',return_value=1795210000.):
            run.page(page)
    finally:module.DEADLINE.reset(token)
    return run,page,clock

class MinnesotaRetry(unittest.TestCase):
    def setUp(self):
        p=patch.object(socket.socket,'connect',side_effect=AssertionError('No network in saved-input tests'))
        p.start();self.addCleanup(p.stop)
    def test_seventy_healthy_paired_and_timeout_recovery(self):
        records=[]
        for org in CASES:
            with self.subTest(ein=org['ein']):
                before,bp,bc=capture(baseline,org)
                after,ap,ac=capture(s,org)
                self.assertEqual(before.documents[0][:4],after.documents[0][:4])
                self.assertEqual(bp.calls,ap.calls);self.assertEqual(ac.now,bc.now)
                failed,fp,fc=capture(baseline,org,('timeout','ok'))
                recovered,rp,rc=capture(s,org,('timeout','ok'))
                self.assertEqual(len(fp.calls),1);self.assertFalse(failed.documents)
                self.assertEqual(len(rp.calls),2);self.assertEqual(recovered.documents[0][1],rp.raw)
                self.assertLess(rc.now-100,3)
                row={'state':'MN','ein':org['ein'],'status':'Delinquent','success':True,
                     'matched_registry_name':org['name'],'matched_registry_identifier':'12345'}
                good=recovered.finish(row)
                self.assertEqual(good['status'],row['status']);self.assertEqual(len(good['_worker_source_archives']),1)
                self.assertNotIn('_worker_source_archives',recovered.finish({**row,'matched_registry_identifier':'54321'}))
                records.append({'name':org['name'],'ein':org['ein'],'healthy_exact':True,
                    'first_pass_baseline_missing':True,'retry_recovered':True,'elapsed_seconds':rc.now-100,
                    'same_record_publication_guard':True})
        (OUT/'LOCAL-70-RESULTS.json').write_text(json.dumps({'passed':True,'distinct_organizations':70,
            'scope':'Offline paired captures with recorded organization/EIN inputs; synthetic pixels, timings and failures, not live registry searches.','cases':records},indent=2))
    def test_seventy_failure_bounds_and_source_guards(self):
        for org in CASES:
            for actions,expected in [(('timeout','timeout'),2),(('navigate','ok'),1),
                                     (('text','ok'),1),(('error','ok'),1),(('late_ok',),1)]:
                with self.subTest(ein=org['ein'],actions=actions):
                    run,page,clock=capture(s,org,actions)
                    self.assertFalse(run.documents);self.assertEqual(len(page.calls),expected)
                    self.assertIn('source_page_capture_unavailable',run.errors)
                    if actions[0]!='late_ok':self.assertLessEqual(clock.now-100,3.001)
            for read in [2,3]:
                run,page,_=capture(s,org,('timeout','ok'),change_after=read)
                self.assertFalse(run.documents)
            run,page,clock=capture(s,org,('timeout','ok'),stop=102.)
            self.assertFalse(run.documents);self.assertEqual(len(page.calls),1)
            self.assertLessEqual(page.calls[0]['timeout'],600)
            run,page,_=capture(s,org,('ok',),deadline=102.)
            self.assertFalse(page.calls);self.assertIn('capture_skipped_near_task_deadline',run.errors)
    def test_other_states_keep_original_single_attempt(self):
        for state in ['MN','MD','CT','IL','GA','NY','NV','NC','TN','NH']:
            if state=='MN':continue
            for actions in [('ok',),('timeout','ok')]:
                with self.subTest(state=state,actions=actions):
                    a,ap,ac=capture(baseline,CASES[0],actions,state)
                    b,bp,bc=capture(s,CASES[0],actions,state)
                    self.assertEqual(a.documents,b.documents);self.assertEqual(a.errors,b.errors)
                    self.assertEqual(ap.calls,bp.calls);self.assertEqual(ac.now,bc.now)

if __name__=='__main__':unittest.main()
