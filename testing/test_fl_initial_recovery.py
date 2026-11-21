"""FL initial connection recovery; recorded identities and offline transport controls."""
import ast,json,subprocess,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from email.message import Message
from unittest.mock import MagicMock,patch
import registry_snapshot_server as c
from deployment.fl_initial_recovery import initial_transport_failure
ROOT=Path(__file__).resolve().parents[1]
CASES=json.loads((ROOT/'testing/fixtures/gate54-state-controls.json').read_text())['cases'][:70]

def run_case(case,first_error=None,unavailable=False,negative=False,wrong_ein=False,partial=False,post_timeout=False,master=c):
    now=[0.];page=MagicMock();visits=[];routes=[];wire=[];registered=[]
    def response():
        r=MagicMock();r.status=200;r.headers=Message();r.headers['Content-Type']='text/html';r.read1.side_effect=[b'<html>Complete registry response</html>',b''];r.__enter__.return_value=r;return r
    opener=MagicMock()
    def open_request(req,**kw):
        wire.append({'method':req.method,'url':req.full_url,'timeout':kw['timeout'],'data':req.data});now[0]+=.2
        if unavailable:now[0]+=kw['timeout'];raise TimeoutError('HTTPS source unavailable')
        r=response()
        if partial:r.read1.side_effect=[b'partial',TimeoutError('Incomplete document')]
        return r
    opener.open.side_effect=open_request
    page.route.side_effect=lambda pattern,callback:registered.append(callback)
    def goto(url,**kw):
        visits.append({'url':url,'timeout':kw['timeout']});now[0]+=.1
        if url=='about:blank':return SimpleNamespace(status=200)
        if registered:
            route=MagicMock();route.request=SimpleNamespace(url=url,method='GET',resource_type='document',post_data_buffer=None,all_headers=lambda:{'Cookie':'session=kept'})
            registered[-1](route);routes.append(route)
            if route.abort.called:raise TimeoutError('Recovered GET did not complete')
            assert route.fulfill.called
            return SimpleNamespace(status=200)
        if first_error is not None:
            now[0]+=kw['timeout']/1000;raise first_error
        return SimpleNamespace(status=200)
    page.goto.side_effect=goto
    page.expect_navigation.return_value.__enter__.return_value.value=SimpleNamespace(status=200)
    if post_timeout:page.expect_navigation.return_value.__exit__.side_effect=TimeoutError('Submission response timeout')
    row=case['name']+' License/Registration Number CH12345 Expiration Date 12/31/2027 Status Current EIN '+('999999999' if wrong_ein else case['ein'])
    page.evaluate.return_value=[{'index':0,'text':row}]
    with patch.object(master.time,'monotonic',side_effect=lambda:now[0]),patch.object(master.time,'sleep',side_effect=lambda seconds:now.__setitem__(0,now[0]+seconds)),patch.object(master,'fl_business_lookup_enabled',return_value=False),patch.object(master,'reviewed_queries_first',return_value=[case['name']]),patch.object(master.checker,'find_visible_input',return_value=page),patch.object(master,'readable_page_text',return_value='No records found' if negative else row),patch.object(master,'no_registry_results_seen',return_value=negative),patch.object(master,'registry_candidate_fields',return_value={'status':'Current'}),patch.object(master.urllib.request,'build_opener',return_value=opener):
        r=master.search_fl(page,SimpleNamespace(organization_name=case['name'],ein=case['ein']))
    return r,visits,wire,now[0],page,routes

class InitialRecovery(unittest.TestCase):
    proof=[]
    def test_70_recorded_orgs_recover_same_record_and_keep_healthy_paths(self):
        from testing import test_initial_source_access as t
        t.BASE='ce4ca85';baseline=t.original_module()
        self.assertEqual(len({x['ein'] for x in CASES}),70)
        for case in CASES:
            with self.subTest(ein=case['ein']):
                old,ov,ow,ot,*_=run_case(case,master=baseline)
                healthy,hv,hw,ht,*_=run_case(case)
                recovered,rv,rw,rt,_,routes=run_case(case,first_error=TimeoutError('Initial document timeout'))
                self.assertEqual((old.status,old.success,old.matched_registry_identifier),(healthy.status,healthy.success,healthy.matched_registry_identifier))
                self.assertEqual((ov,ow,ot),(hv,hw,ht));self.assertTrue(healthy.success)
                self.assertEqual((healthy.status,healthy.matched_registry_identifier),(recovered.status,recovered.matched_registry_identifier))
                self.assertTrue(recovered.success);self.assertEqual(len(rw),1);self.assertEqual(rw[0]['method'],'GET');self.assertLess(rt,44)
                self.assertTrue(routes[0].fulfill.called)
                self.proof.append(dict(ein=case['ein'],name=case['name'],healthy_unchanged=True,recovered_status=recovered.status,recovered_seconds=rt))
    def test_70_unavailable_and_70_partial_sources_never_become_negative(self):
        for case in CASES:
            for partial in [False,True]:
                with self.subTest(ein=case['ein'],partial=partial):
                    r,_,wire,seconds,*_=run_case(case,first_error=TimeoutError('Initial timeout'),unavailable=not partial,partial=partial)
                    self.assertFalse(r.success);self.assertNotEqual(r.status,c.checker.STATUS_NOT_REGISTERED);self.assertLessEqual(seconds,44.5)
                    self.assertTrue(all(0 < x['timeout']<=8 for x in wire))
    def test_70_recovered_negative_and_70_wrong_ein_rejections(self):
        for case in CASES:
            for negative,wrong in [(True,False),(False,True)]:
                with self.subTest(ein=case['ein'],negative=negative):
                    r,*_=run_case(case,first_error=TimeoutError('Initial timeout'),negative=negative,wrong_ein=wrong)
                    self.assertTrue(r.success);self.assertEqual(r.status,c.checker.STATUS_NOT_REGISTERED);self.assertFalse(r.matched_registry_identifier)
    def test_post_timeout_does_not_enable_alternative_transport(self):
        r,_,wire,*_=run_case(CASES[0],post_timeout=True)
        self.assertFalse(r.success);self.assertEqual(wire,[])
    def test_only_recognized_pre_response_transport_errors_qualify(self):
        for e in [TimeoutError(),RuntimeError('net::ERR_CONNECTION_RESET'),RuntimeError('net::ERR_EMPTY_RESPONSE')]:self.assertTrue(initial_transport_failure(e))
        for e in [ValueError('HTTP 403'),ValueError('HTTP 503'),RuntimeError('net::ERR_CERT_AUTHORITY_INVALID'),RuntimeError('net::ERR_BLOCKED_BY_CLIENT'),RuntimeError('Browser closed'),ValueError('parse failed')]:self.assertFalse(initial_transport_failure(e))
    def test_denial_does_not_switch_transport(self):
        for e in [ValueError('HTTP 403'),ValueError('Verification required')]:
            r,_,wire,*_=run_case(CASES[0],first_error=e);self.assertFalse(r.success);self.assertEqual(wire,[])
    def test_assets_stay_native_and_prior_error_clears_only_for_fresh_document(self):
        tr=c.FloridaVerifiedTransport(MagicMock());tr.initial_timeout_recovery=True;tr.deadline=0;tr.error=TimeoutError('prior')
        route=MagicMock();route.request.url=c.FL_CHECK_A_CHARITY_URL;route.request.resource_type='script'
        tr.route(route);route.fallback.assert_called_once();self.assertIsInstance(tr.error,TimeoutError)
        route=MagicMock();route.request.url=c.FL_CHECK_A_CHARITY_URL;route.request.resource_type='document'
        tr.error=c.FloridaCertificateError('untrusted');old=tr.error;tr.route(route);self.assertIs(tr.error,old)
    def test_master_scope_only_FL_class_loader_import(self):
        before=ast.parse(subprocess.check_output(['git','show','ce4ca85:registry_snapshot_server.py'],cwd=ROOT).decode())
        after=ast.parse((ROOT/'registry_snapshot_server.py').read_text(encoding='utf-8'))
        for name in ['FloridaVerifiedTransport','search_fl_with_transport']:
            old=next(x for x in before.body if getattr(x,'name','')==name);new=next(x for x in after.body if getattr(x,'name','')==name);after.body[after.body.index(new)]=old
        after.body=[x for x in after.body if not(isinstance(x,ast.ImportFrom) and x.module=='deployment.fl_initial_recovery')]
        self.assertEqual(ast.dump(before),ast.dump(after))
    @classmethod
    def tearDownClass(cls):
        target=Path(__import__('os').environ.get('CC_FL_PROOF','FL-RECOVERY-70.json'))
        target.write_text(json.dumps({'identities':len(cls.proof),'offline':True,'live_searches':0,'rows':cls.proof},indent=2))

if __name__=='__main__':unittest.main()
