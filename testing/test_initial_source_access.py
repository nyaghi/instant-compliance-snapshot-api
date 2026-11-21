"""Recorded organization identities with offline source-failure injection.

The actual public lookup/adapter paths run against local HTTP/browser fakes.
These are not live state searches or independent registration accuracy tests.
"""
import ast,copy,importlib.util,json,os,socket,subprocess,sys,time,threading,unittest,urllib.error
from contextlib import ExitStack
from pathlib import Path
from types import ModuleType,SimpleNamespace
from unittest.mock import Mock,patch
import registry_snapshot_server as c
from deployment import initial_source_access as access

ROOT=Path(__file__).resolve().parents[1]
BASE='abd99345ae851f408c1f59d33d00c1395d96cabb'
CASES=json.loads((ROOT/'testing/fixtures/gate54-state-controls.json').read_text(encoding='utf8'))['cases']
STATES=sorted(access.STATES)


def original_module():
    name='cc_initial_access_baseline'
    if name in sys.modules:return sys.modules[name]
    src=subprocess.check_output(['git','show',BASE+':registry_snapshot_server.py'],cwd=ROOT).decode('utf8')
    m=ModuleType(name);m.__file__=str(ROOT/'registry_snapshot_server.py');sys.modules[name]=m
    exec(compile(src,'<deployed-SH>','exec'),m.__dict__)
    return m


def fault_lookup(master,state,case,denial=False):
    clock=[100000.0];calls=[];unhandled=[];closed=[];slots=threading.BoundedSemaphore(2)
    def step(seconds):clock[0]+=max(.05,float(seconds or .05))
    def duration(value,default):
        if isinstance(value,(tuple,list)):return sum(float(v) for v in value if v is not None)
        return float(value if isinstance(value,(int,float)) else default)
    def fail(kind,url,seconds):
        step(seconds);calls.append(dict(kind=kind,seconds=seconds))
        if denial and len(calls)==1:raise urllib.error.HTTPError(str(url),403,'HTTP Error 403',{},None)
        raise TimeoutError('curl: (28) Operation timed out at the public registry')
    def http(*args,**kw):return fail('http',args[0] if args else '',duration(kw.get('timeout'),8))
    def urlopen(*args,**kw):return fail('urllib',args[0] if args else '',duration(kw.get('timeout'),8))
    class Page:
        url='about:blank'
        def __init__(self):self.frames=[self];self.main_frame=self;self.context=SimpleNamespace(pages=[self],request=SimpleNamespace(get=http,post=http))
        def goto(self,url,**kw):
            if url=='about:blank':self.url=url;return SimpleNamespace(status=200)
            self.url=url;return fail('browser_navigation',url,duration(kw.get('timeout'),30000)/1000)
        def locator(self,*a,**kw):
            v=Mock();v.count.return_value=0;v.is_visible.return_value=False;v.inner_text.return_value='';v.text_content.return_value='';v.all.return_value=[];v.first=v;v.nth.return_value=v;v.locator.return_value=v;return v
        get_by_role=locator;get_by_text=locator;get_by_label=locator
        def content(self):return ''
        def wait_for_timeout(self,ms):step(ms/1000)
        def wait_for_load_state(self,*a,**kw):pass
        def set_default_timeout(self,*a,**kw):pass
        def set_default_navigation_timeout(self,*a,**kw):pass
        def route(self,*a,**kw):pass
        def on(self,*a,**kw):pass
        def close(self,*a,**kw):closed.append('page')
        def evaluate(self,*a,**kw):return None
        def title(self):return ''
    class Browser:
        def new_context(self,**kw):
            v=Mock();v.new_page.side_effect=Page;v.pages=[];v.close.side_effect=lambda:closed.append('context');return v
        def new_page(self,**kw):return Page()
        def close(self):closed.append('browser')
    session=SimpleNamespace(headers={},cookies=Mock(),get=Mock(side_effect=http),post=Mock(side_effect=http),close=lambda:closed.append('session'))
    fakep=Mock();fakep.__enter__=lambda self:Mock();fakep.__exit__=lambda *a:None
    def forbidden(*a,**kw):unhandled.append('network');raise AssertionError('No live network in local tests')
    with ExitStack() as stack:
        stack.enter_context(patch.object(master,'BROWSER_LOOKUP_SEMAPHORE',slots))
        stack.enter_context(patch.object(master,'ME_LOOKUP_LOCK',threading.Lock()))
        stack.enter_context(patch.object(master,'ME_LAST_LOOKUP_FINISHED',0.0))
        stack.enter_context(patch.object(master.checker,'_REAL_SLEEP',step))
        for obj,key,value in [(master,'APP_VERSION','2026.09.29.2-performance-lab'),(master,'trial_identity',lambda:True),(master,'known_names_for_ein',lambda x:[]),(master,'launch_lookup_browser',lambda *a,**kw:Browser()),(master.checker,'sync_playwright',lambda:fakep),(time,'monotonic',lambda:clock[0]),(time,'perf_counter',lambda:clock[0]),(time,'sleep',step),(socket.socket,'connect',forbidden),(subprocess,'Popen',forbidden),(master.urllib.request,'urlopen',urlopen),(master.urllib.request.OpenerDirector,'open',urlopen),(master.curl_requests,'Session',lambda *a,**kw:session),(master.curl_requests,'get',http),(master.curl_requests,'post',http)]:stack.enter_context(patch.object(obj,key,value))
        stack.enter_context(patch.dict(os.environ,{'CE_FINAL_FOUR_CHILD':'1'}))
        from deployment.state_snapshots import task_deadline
        with task_deadline({'run_seconds':300,'_deadline_monotonic':clock[0]+300}):
            result=master.run_single_state_lookup_reliably(case['name'],case['ein'],state)
    assert slots._value==2, ('Browser admission leaked',state,slots._value)
    return result,calls,clock[0]-100000,unhandled,closed


class InitialAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.baseline=original_module()

    def test_70_recorded_inputs_each_nine_actual_routes_stop_after_two_connections(self):
        proof=[]
        for state in STATES:
            for case in CASES:
                with self.subTest(state=state,ein=case['ein']):
                    data,calls,seconds,unhandled,closed=fault_lookup(c,state,case)
                    self.assertEqual(unhandled,[])
                    self.assertEqual(data['status'],'Site Not Reachable')
                    self.assertFalse(data['success'])
                    self.assertEqual(data['reason_code'],state+'_INITIAL_SOURCE_UNREACHABLE')
                    self.assertEqual(len(calls),2)
                    self.assertEqual(len(data['initial_source_access']['transport_failures']),2)
                    self.assertTrue(data['source_availability']['terminal'])
                    self.assertEqual(access.CURRENT.get(),None)
                    if state in {'AK','AR','HI','MI','OH','WV'}:self.assertIn('browser',closed)
                    proof.append(dict(state=state,name=case['name'],ein=case['ein'],transport_calls=len(calls),virtual_seconds=round(seconds,3),status=data['status']))
        self.assertEqual(len(proof),630)
        output=os.environ.get('CC_INITIAL_ACCESS_OUTPUT')
        if output:Path(output,'LOCAL-630-OUTAGES.json').write_text(json.dumps({'offline_synthetic':True,'recorded_organizations_per_state':70,'rows':proof},indent=2),encoding='utf8')

    def test_70_each_denial_keeps_existing_recovery_and_final_classification(self):
        # These deny the first access, then time out. They must not be stopped
        # by the new transport rule before legacy alternate access completes.
        total=0
        for state in STATES:
            for case in CASES:
                with self.subTest(state=state,ein=case['ein']):
                    original,old_calls,_,old_unhandled,_=fault_lookup(self.baseline,state,case,denial=True)
                    actual,new_calls,_,new_unhandled,_=fault_lookup(c,state,case,denial=True)
                    keys=('status','success','reason_code','matched_registry_name','matched_registry_identifier','confirmation_required')
                    self.assertEqual({k:actual.get(k) for k in keys},{k:original.get(k) for k in keys})
                    self.assertEqual(new_calls,old_calls)
                    self.assertEqual(new_unhandled,old_unhandled)
                    self.assertNotIn('initial_source_access',actual)
                    total+=1
        self.assertEqual(total,630)

    def test_70_each_healthy_and_one_timeout_then_recovery_preserve_supplied_outcome(self):
        # The selected result/evidence objects come through unchanged, covering
        # negative, exempt, adverse, pending, identity-review and current paths.
        statuses=['Not Registered','Exempt','Delinquent','Pending','Current','Upcoming Filing','Unable to Confirm']
        for state in STATES:
            for i,case in enumerate(CASES):
                for recover in (False,True):
                    result={'state':state,'organization_name':case['name'],'ein':case['ein'],'status':statuses[i%len(statuses)],'success':i%len(statuses)!=6,'state_snapshot_url':'/original-evidence','confirmation_required':i%len(statuses)==6}
                    calls=[]
                    def operation(name,ein,st):
                        if recover:
                            try:access.call(st,lambda:(_ for _ in ()).throw(TimeoutError('initial timeout')))
                            except TimeoutError:pass
                        access.call(st,lambda:calls.append('entry'))
                        # Later detail/evidence timeouts retain their existing
                        # owner and cannot be misclassified as initial outage.
                        for _ in range(3):
                            try:access.call(st,lambda:(_ for _ in ()).throw(TimeoutError('detail timeout')))
                            except TimeoutError:pass
                        return result
                    with patch.object(c,'trial_identity',return_value=True):actual=access.run(c,operation,case['name'],case['ein'],state)
                    self.assertIs(actual,result);self.assertEqual(calls,['entry'])

    def test_nontransport_and_http_errors_do_not_newly_terminate(self):
        for state in STATES:
            for exc in [urllib.error.HTTPError('https://registry.test',n,'denied',{},None) for n in (403,404,429,503)]+[ValueError('parser timeout'),RuntimeError('verification required')]:
                scope=access.Scope(state);token=access.CURRENT.set(scope)
                try:
                    for _ in range(3):
                        with self.assertRaises(type(exc)):
                            access.call(state,lambda:(_ for _ in ()).throw(exc))
                    self.assertEqual(scope.failures,[])
                finally:access.CURRENT.reset(token)

    def test_cancel_and_finally_cleanup_are_preserved(self):
        closed=[]
        def operation(name,ein,state):
            try:
                for _ in range(4):
                    try:access.call(state,lambda:(_ for _ in ()).throw(TimeoutError('connection timed out')))
                    except Exception:pass
            finally:closed.append(True)
        with patch.object(c,'trial_identity',return_value=True):data=access.run(c,operation,'Test Charity','123456789','MI')
        self.assertEqual(data['status'],'Site Not Reachable');self.assertEqual(closed,[True]);self.assertIsNone(access.CURRENT.get())
        def canceled(*args):raise KeyboardInterrupt('user canceled')
        with patch.object(c,'trial_identity',return_value=True),self.assertRaises(KeyboardInterrupt):access.run(c,canceled,'Test','123456789','MI')
        self.assertIsNone(access.CURRENT.get())

    def test_other_states_and_production_have_no_new_guard(self):
        for state in ['TN','NV','NC','SC','MA','MN','NJ','WA']:
            sentinel=object()
            with patch.object(c,'trial_identity',return_value=True):self.assertIs(access.run(c,lambda *a:sentinel,'Name','123456789',state),sentinel)
        with patch.object(c,'trial_identity',return_value=False):
            self.assertIsNone(access.run(c,lambda *a:access.CURRENT.get(),'Name','123456789','MI'))


if __name__=='__main__':unittest.main()
