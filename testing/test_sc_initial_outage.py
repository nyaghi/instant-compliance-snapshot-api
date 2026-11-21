"""SC initial transport recovery: recorded identities, synthetic source replies.

No live state calls. Healthy query sequences and identity decisions are compared
against the deployed SF function; failures run the real master retry boundary.
"""
import ast,copy,html,json,os,socket,subprocess,time,unittest,urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import registry_snapshot_server as c
from deployment.source_availability import classify,apply

ROOT=Path(__file__).resolve().parents[1]
CASES=json.loads((ROOT/'testing/fixtures/gate54-state-controls.json').read_text(encoding='utf-8'))['cases']
BASE='7f96381fb747a99abfe4c111e46cfd949009b5c7'

class Response:
    def __init__(self,text):self.text=text
    def raise_for_status(self):pass

def baseline():
    tree=ast.parse(subprocess.check_output(['git','show',BASE+':registry_snapshot_server.py'],cwd=ROOT).decode('utf-8'))
    node=next(n for n in tree.body if getattr(n,'name','')=='sc_official_detail_lookup')
    env=dict(vars(c));exec(compile(ast.Module(body=[node],type_ignores=[]),'<SF-sc>','exec'),env)
    return env['sc_official_detail_lookup']

class SCInitialOutage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.original=staticmethod(baseline())
    def setUp(self):
        self.guard=patch.object(socket.socket,'connect',side_effect=AssertionError('Offline only'))
        self.guard.start();self.addCleanup(self.guard.stop)

    def source(self,case,behavior='empty',initial_failures=0,clock=None):
        name=case['name'];calls=[];state={'get':0}
        session=SimpleNamespace(headers={})
        def get(url,**kw):
            calls.append(('GET',url,kw['timeout']));state['get']+=1
            if state['get']<=initial_failures:
                if clock is not None:clock[0]+=kw['timeout']
                raise TimeoutError('SC initial registry read timed out')
            return Response('<form></form>')
        def post(url,data,**kw):
            calls.append(('POST',dict(data),kw['timeout']))
            if behavior=='malformed':return Response('<h1>Checking your browser</h1>')
            if behavior=='search-timeout':raise TimeoutError('search response timed out')
            if 'ctl00$MainContent$Hidden_CharityID' in data:
                if behavior=='detail-timeout':raise TimeoutError('detail response timed out')
                return Response('<span id="MainContent_lbl_CharityName">'+html.escape(name)+'</span><span id="MainContent_lblCharityID">P1234</span> Status: Exempt')
            return Response('<div>No results found</div>' if behavior=='empty' else
                '<a href="javascript:CharityInfo(1234)">'+html.escape(name)+'</a>')
        session.get=Mock(side_effect=get);session.post=Mock(side_effect=post)
        return session,calls

    def test_70_recorded_healthy_inputs_paired_positive_negative_and_uncertain(self):
        count=0
        for case in CASES:
            for behavior in ['empty','positive','malformed','search-timeout','detail-timeout']:
                outcomes=[];sequences=[]
                for fn in [self.original,c.sc_official_detail_lookup]:
                    session,calls=self.source(case,behavior)
                    with patch.object(c.curl_requests,'Session',return_value=session),patch.object(c,'known_names_for_ein',return_value=[]),patch.object(c,'build_search_queries',return_value=[case['name']]):
                        if fn is self.original:
                            fn.__globals__['build_search_queries']=c.build_search_queries
                            fn.__globals__['known_names_for_ein']=c.known_names_for_ein
                        result=fn(c.checker.Organization(case['name'],case['ein']))
                    outcomes.append(None if result is None else vars(result));sequences.append(calls)
                    if behavior=='positive':
                        self.assertIsNotNone(result,case['name']);self.assertEqual(result.status,'Exempt')
                self.assertEqual(outcomes[0],outcomes[1],(case['name'],behavior))
                self.assertEqual([(a,b) for a,b,_ in sequences[0]],[(a,b) for a,b,_ in sequences[1]])
            count+=1
        self.assertEqual(count,70)

    def test_70_initial_outages_stop_before_preflight_browser_and_outer_retry(self):
        results=[]
        for case in CASES:
            clock=[100.0];session,calls=self.source(case,initial_failures=2,clock=clock)
            with patch.object(c.curl_requests,'Session',return_value=session),patch.object(c,'build_search_queries',return_value=[case['name']]),patch.object(c.time,'monotonic',side_effect=lambda:clock[0]),patch.object(c,'trial_identity',return_value=True),patch.object(c,'quick_registry_preflight',side_effect=AssertionError('No duplicate preflight')),patch.object(c,'launch_lookup_browser',side_effect=AssertionError('No browser on exhausted initial access')):
                result=c._run_single_state_lookup_reliably_core(case['name'],case['ein'],'SC')
            self.assertEqual((result['status'],result['success'],result['semantic_attempts']),('Site Not Reachable',False,1))
            self.assertEqual(result['reason_code'],'SC_INITIAL_SOURCE_UNREACHABLE')
            self.assertTrue(classify(result)['terminal'])
            self.assertEqual(session.get.call_count,2);session.post.assert_not_called()
            self.assertEqual(clock[0]-100,16)
            results.append(dict(name=case['name'],ein=case['ein'],source_gets=2,name_submissions=0,virtual_source_seconds=16,status=result['status']))
        path=os.environ.get('CC_SC_TEST_OUTPUT')
        if path:Path(path,'SC-70-RESULTS.json').write_text(json.dumps(dict(passed=True,recorded_organizations=70,synthetic_outage_conditions=True,healthy_paired_behaviors_per_org=5,rows=results),indent=2),encoding='utf-8')

    def test_70_first_timeout_then_recovery_keeps_first_required_query(self):
        for case in CASES:
            clock=[100.0];session,calls=self.source(case,'positive',1,clock)
            with patch.object(c.curl_requests,'Session',return_value=session),patch.object(c,'build_search_queries',return_value=[case['name']]),patch.object(c,'known_names_for_ein',return_value=[]),patch.object(c.time,'monotonic',side_effect=lambda:clock[0]):
                result=c.sc_official_detail_lookup(c.checker.Organization(case['name'],case['ein']))
            self.assertIsNotNone(result);self.assertTrue(result.success,case['name']);self.assertNotEqual(result.status,'Site Not Reachable')
            queries=[b['ctl00$MainContent$txt_CharitySearchName'] for a,b,_ in calls if a=='POST' and 'ctl00$MainContent$txt_CharitySearchName' in b]
            self.assertEqual(len(queries),1)
            self.assertEqual(queries[0],c.literal_name_retrieval_forms(case['name'])[0])

    def test_terminal_scope_does_not_override_identity_or_other_states(self):
        item=dict(state='SC',status='Site Not Reachable',success=False,reason_code='SC_INITIAL_SOURCE_UNREACHABLE')
        self.assertTrue(classify(item)['terminal'])
        self.assertIsNone(classify(item|{'confirmation_required':True}))
        self.assertIsNone(classify(item|{'success':True,'status':'Current'}))
        # Other existing outage codes retain their delayed recovery policy.
        self.assertFalse(classify(item|{'reason_code':'OR_SOURCE_UNREACHABLE'})['terminal'])

    def test_70_access_denials_preserve_existing_browser_fallback(self):
        for case in CASES:
            for code in [403,404,429,503]:
                outcomes=[];calls=[]
                for fn in [self.original,c.sc_official_detail_lookup]:
                    session,_=self.source(case)
                    session.get.side_effect=urllib.error.HTTPError(c.NAME_SEARCH_PREFLIGHT_URLS['SC'],code,'HTTP Error '+str(code),{},None)
                    with patch.object(c.curl_requests,'Session',return_value=session),patch.object(c,'build_search_queries',return_value=[case['name'],case['name']+' Extra']):
                        if fn is self.original:fn.__globals__['build_search_queries']=c.build_search_queries
                        result=fn(c.checker.Organization(case['name'],case['ein']))
                    session.get.side_effect.close()
                    outcomes.append(result);calls.append(session.get.call_count)
                self.assertIsNone(outcomes[0]);self.assertIsNone(outcomes[1],(case['name'],code))
                self.assertEqual(calls,[2,2])

if __name__=='__main__':unittest.main()
