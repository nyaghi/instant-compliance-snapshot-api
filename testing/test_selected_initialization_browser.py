"""Real isolated Chromium; blank dependency delay and clock are explicitly modeled."""
import contextvars,copy,html,json,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from playwright.sync_api import TimeoutError as BrowserTimeout,sync_playwright
from deployment import source_visual_adapters as a,state_snapshots as s

CONTEXTS=json.loads((Path(__file__).parent/'fixtures/selected-initialization-contexts.json').read_text())
class Borrowed:
    def __init__(self,browser,route,clock,state):self.browser=browser;self.route=route;self.clock=clock;self.state=state
    def close(self):pass
    def new_context(self,**options):
        context=self.browser.new_context(**options);context.route('**/*',self.route)
        def finish_interceptors():
            while self.route.pending:self.route.pending.pop().abort()
        real_close=context.close
        def close():
            finish_interceptors();context.unroute_all(behavior='wait');real_close()
        context.close=close
        original=context.new_page
        def new_page():
            page=original();by_text=page.get_by_text;by_role=page.get_by_role
            real_reload=page.reload
            def reload(**kwargs):
                # Complete the held fixture interceptor before native navigation
                # aborts it, so no orphan callback survives fixture teardown.
                finish_interceptors();return real_reload(**kwargs)
            page.reload=reload
            real_pause=page.wait_for_timeout
            def pause(milliseconds):
                self.clock[0]+=milliseconds/1000;real_pause(min(milliseconds,1))
            page.wait_for_timeout=pause
            first=[True]
            def wrapped(locator,is_first):
                if not is_first:return locator
                real_wait=locator.wait_for
                def wait(**kwargs):
                    if first[0]:
                        # Let actual script/fetch events start before advancing
                        # the source adapter's clock, not Chromium's clock.
                        first[0]=False
                        try:return real_wait(**{**kwargs,'timeout':80})
                        except BrowserTimeout:
                            self.clock[0]=29;raise
                    try:return real_wait(**{**kwargs,'timeout':80})
                    except BrowserTimeout:
                        self.clock[0]=40;raise
                return SimpleNamespace(wait_for=wait)
            page.get_by_text=lambda value,**kw:wrapped(by_text(value,**kw),self.state=='CA'and value=='Registration Number')
            page.get_by_role=lambda role,**kw:wrapped(by_role(role,**kw),self.state=='VA'and role=='heading'and kw.get('name')=='Registration Information')
            return page
        context.new_page=new_page;return context

def replay(browser,pw,state,org,*,wrong_id=False,answered_dependency=False,seconds=100,selected_object=None,blocked=False,other_object=False,stays_pending=False):
    name=org['name'];ein=s.digits(org['ein']);clock=[0.0];requests=[];documents=[]
    identifier='117962'if state=='CA'else'677523'
    url=('https://ca-rcf.evokeplatform.com/app/publicPortal/registrationDetails/1006488'if state=='CA'else'https://vdacs.evokeplatform.com/app/publicPortal/registration/677523')
    origin=url.split('/app/')[0];boot=origin+'/api/webContent/themes'
    shell=''
    if selected_object:
        url=origin+'/app/publicPortal/registrationDetails/'+selected_object
        boot=origin+'/api/data/objects/registrations/instances/'+('1' if other_object else selected_object)+'/object'
        shell='<h1>Registration</h1><h2>Initial Applications</h2>'
        if blocked:shell+='<p>Access denied</p>'
    if state=='CA':
        core='<p>Entity Related</p><p>'+html.escape(name)+'</p><p class="formio-component-registrationNumber">Registration Number</p><p>'+('999999'if wrong_id else identifier)+'</p><p>Registration Type</p><p>Charitable Organization</p><p>Registration Status</p><p>Registered</p><p>Initial Registration Date</p><p>06/30/2006</p><p>Current Expiration Date</p><p>11/15/2025</p><h2>CHARITABLE ORGANIZATION DETAILS</h2>'
        body='<div class="formio-form">'+core+'</div>';hint={'name':name,'url':url}
    else:
        fields=[('calculatedRegistrationStatusLabel','Status','Registered'),('renewalStatus','Renewal Status','Eligible'),('initialIssueDate','Initial Registration Date','05/07/2020'),('dateOfLastRenewal','Date of Last Renewal','04/20/2026'),('issueDate','Current Registration Date','04/20/2026'),('expirationDate','Expiration Date','11/15/2026'),('extensionDate','Extension Date','')]
        body='<p>'+html.escape(name)+'</p><p>Registration ID: '+('999999'if wrong_id else identifier)+'</p><div class="formio-form"><h3>Registration Information</h3><p>Registration ID</p>'+''.join('<div class="formio-component-'+key+'"><label>'+label+'</label><p>'+value+'</p></div>'for key,label,value in fields)+'</div>'
        hint={'name':name,'url':url,'source_record_id':identifier,'registration_type':'Charity','source_fields':{key:value for key,label,value in fields}}
    loaded='<h1>LOCAL MODELED FIXTURE — NOT STATE EVIDENCE</h1>'+body
    def route(r):
        requests.append(r.request.url)
        if r.request.url==url:
            documents.append(r.request.url)
            raw=(f'<html><head><script>fetch({json.dumps(boot)})</script></head><body>{shell}</body></html>'
                 if len(documents)==1 or stays_pending else loaded)
            r.fulfill(status=200,content_type='text/html; charset=utf-8',body=raw)
        elif r.request.url==boot:
            if answered_dependency:r.fulfill(status=200,content_type='application/json',body='{}')
            else:route.pending.append(r)
            # Otherwise leave this one modeled bootstrap response pending.
        else:raise AssertionError('Unexpected live request: '+r.request.url)
    route.pending=[]
    mode=contextvars.ContextVar('mode',default='standard')
    master=SimpleNamespace(trial_identity=lambda:True,LAB_LOOKUP_MODE_CONTEXT=mode,BROWSER_LOOKUP_SEMAPHORE=threading.BoundedSemaphore(1),checker=SimpleNamespace(sync_playwright=lambda:SimpleNamespace()))
    class PW:
        def __enter__(self):return pw
        def __exit__(self,*args):pass
    master.checker.sync_playwright=lambda:PW();master.launch_lookup_browser=lambda *args,**kwargs:Borrowed(browser,route,clock,state)
    result={'state':state,'ein':ein,'organization_name':name,'status':'Delinquent'if state=='CA'else'Upcoming Filing','success':True,'matched_registry_name':name,'matched_registry_identifier':identifier,'source_url':url}
    original=copy.deepcopy(result);run=s.CaptureRun(name,ein,state);run.source_detail_hints[identifier]=hint
    # Only the adapter clock is modeled. Browser/network/screenshot timing is real.
    fake_time=SimpleNamespace(monotonic=lambda:clock[0],perf_counter=time.perf_counter,sleep=time.sleep,time=time.time)
    with patch.object(a,'time',fake_time):
        (a.capture_selected_ca_source if state=='CA'else a.capture_selected_va_source)(master,result,run,seconds)
    assert result==original
    return {'run':run,'documents':documents,'requests':requests,'clock':clock[0],'fact':run.visual_adapter_facts[-1]}

class BrowserRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.p=sync_playwright().start();cls.browser=cls.p.chromium.launch(headless=True)
    @classmethod
    def tearDownClass(cls):cls.browser.close();cls.p.stop()
    def test_same_detail_reload_recovers_two_selected_pages_without_new_search(self):
        for state in ['CA','VA']:
            r=replay(self.browser,self.p,state,CONTEXTS[0]);self.assertEqual(len(r['documents']),2)
            self.assertEqual(r['fact']['outcome'],'captured',r['fact']);self.assertEqual(len(r['run'].documents),1)
            self.assertEqual(r['fact']['initialization_reload']['count'],1)
            self.assertEqual(r['fact']['selected_readiness_observation']['requests'],3)
    def test_wrong_record_and_parent_cutoff_cannot_become_evidence(self):
        for state in ['CA','VA']:
            for kwargs in [{'wrong_id':True},{'seconds':33},{'answered_dependency':True}]:
                r=replay(self.browser,self.p,state,CONTEXTS[0],**kwargs);self.assertEqual(r['run'].documents,[],r['fact'])
                if kwargs!={'wrong_id':True}:self.assertEqual(len(r['documents']),1)
    def test_ca_selected_object_stall_reloads_only_the_same_registration(self):
        for detail_id in ['1451199','1011132']:
            with self.subTest(detail_id=detail_id):
                r=replay(self.browser,self.p,'CA',CONTEXTS[0],selected_object=detail_id)
                self.assertEqual(r['fact']['outcome'],'captured',r['fact'])
                self.assertEqual(len(r['run'].documents),1)
                self.assertEqual(len(r['documents']),2)
                self.assertEqual(len(set(r['documents'])),1)
                self.assertEqual(len(r['requests']),3)
                self.assertEqual(r['fact']['ca_selected_object_retry']['extra_granted_seconds'],15)
    def test_ca_selected_object_stall_is_bounded_and_rejects_unbound_sources(self):
        for opts,count in [({'other_object':True},1),({'answered_dependency':True},1),({'blocked':True},1),
                           ({'seconds':36},1),({'wrong_id':True},2),({'stays_pending':True},2)]:
            with self.subTest(opts=opts):
                r=replay(self.browser,self.p,'CA',CONTEXTS[0],selected_object='1451199',**opts)
                self.assertEqual(len(r['documents']),count,r['fact'])
                self.assertEqual(r['run'].documents,[],r['fact'])

if __name__=='__main__':unittest.main()
