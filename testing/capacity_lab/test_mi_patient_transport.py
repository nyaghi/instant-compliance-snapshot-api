"""Keep the same complete-response proof and outer budgets under source load."""
import ast,os,subprocess,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import registry_snapshot_server as m
from testing.capacity_lab.test_mi_name_transport import FORM,URL,RESULT,body

class PatientTransport(unittest.TestCase):
    def setUp(self):
        self.org=SimpleNamespace(organization_name='Example Relief',ein='123456789')
        token=m.LAB_LOOKUP_MODE_CONTEXT.set('sales');self.addCleanup(m.LAB_LOOKUP_MODE_CONTEXT.reset,token)
        for p in [patch.object(m,'APP_VERSION','fixture-performance-lab'),patch.dict(os.environ,{'PUBLIC_BASE_URL':'https://instant-compliance-snapshot-api-hn4v.onrender.com','CE_LAB_MI_PATIENT_TRANSPORT':'1'})]:
            p.start();self.addCleanup(p.stop)

    def response(self,text,url=RESULT):
        r=MagicMock();r.status_code=200;r.url=url;r.history=[];r.text=text;r.iter_content.return_value=[text.encode()];return r

    def test_standard_nonlab_other_host_and_disabled_keep_old_limits(self):
        for mode,version,env in [('standard','fixture-performance-lab',{}),('sales','staging',{}),('sales','fixture-performance-lab',{'PUBLIC_BASE_URL':'https://staging.compliance-express.com'}),('sales','fixture-performance-lab',{'CE_LAB_MI_PATIENT_TRANSPORT':'0'})]:
            token=m.LAB_LOOKUP_MODE_CONTEXT.set(mode)
            try:
                with patch.object(m,'APP_VERSION',version),patch.dict(os.environ,env):
                    self.assertFalse(m.lab_mi_patient_transport_enabled())
                    s=MagicMock();s.request.side_effect=[self.response(FORM,URL),self.response(body())]
                    with patch.object(m,'mi_name_fallback_queries',return_value=['Example Relief']):m.mi_name_http_empty_queries(s,self.org,{},time.perf_counter()+100)
                    self.assertLessEqual(s.request.call_args_list[1].kwargs['timeout'],18)
            finally:m.LAB_LOOKUP_MODE_CONTEXT.reset(token)

    def test_slow_complete_name_zero_uses_remaining_existing_24second_allowance(self):
        clock=[100.0];s=MagicMock()
        def request(method,*args,**kwargs):
            if method=='GET':clock[0]+=.2;return self.response(FORM,URL)
            self.assertGreater(kwargs['timeout'],23);self.assertLessEqual(kwargs['timeout'],24)
            self.assertTrue(kwargs['verify']);clock[0]+=21;return self.response(body())
        s.request.side_effect=request
        with patch.object(m.time,'monotonic',lambda:clock[0]),patch.object(m.time,'perf_counter',lambda:clock[0]),patch.object(m,'mi_name_fallback_queries',return_value=['Example Relief']):
            self.assertEqual(m.mi_name_http_empty_queries(s,self.org,{},200),['Example Relief'])
        self.assertEqual(s.request.call_count,2)

    def test_late_partial_positive_and_wrong_query_still_cannot_prove_zero(self):
        for source,elapsed in [(body(),24.1),(body()[:-7],20),(body('Another Relief'),20),(body('Example Relief','1'),20)]:
            clock=[100.0];s=MagicMock()
            def request(method,*args,**kwargs):
                if method=='GET':return self.response(FORM,URL)
                clock[0]+=elapsed;return self.response(source)
            s.request.side_effect=request
            with patch.object(m.time,'monotonic',lambda:clock[0]),patch.object(m.time,'perf_counter',lambda:clock[0]),patch.object(m,'mi_name_fallback_queries',return_value=['Example Relief']):
                self.assertEqual(m.mi_name_http_empty_queries(s,self.org,{},200),[])

    def test_short_remaining_outer_deadline_still_clamps_name_request(self):
        s=MagicMock();s.request.side_effect=[self.response(FORM,URL),self.response(body())]
        with patch.object(m.time,'monotonic',return_value=100),patch.object(m.time,'perf_counter',return_value=100),patch.object(m,'mi_name_fallback_queries',return_value=['Example Relief']):
            self.assertEqual(m.mi_name_http_empty_queries(s,self.org,{},105),['Example Relief'])
        self.assertEqual(s.request.call_args_list[0].kwargs['timeout'],4)
        self.assertEqual(s.request.call_args_list[1].kwargs['timeout'],5)

    def test_ein_request_can_finish_after_old_sublimit_without_repeating_query(self):
        clock=[100.0];s=MagicMock();s.get.return_value=self.response(FORM,URL)
        def post(url,*args,**kwargs):
            if 'Disclaimer' in url:return self.response(FORM,URL)
            self.assertEqual(kwargs['timeout'],45)
            self.assertEqual(kwargs['data']['ctl00$MainContent$txtEIN'],'12-3456789')
            clock[0]+=40
            return self.response('<html>Results for the following input: 0 record(s) found No records found</html>')
        s.post.side_effect=post
        with patch.object(m.time,'monotonic',lambda:clock[0]),patch.object(m.time,'perf_counter',lambda:clock[0]),patch.object(m.curl_requests,'Session',return_value=s):
            r=m.search_mi_http_completion_probe(self.org)
        self.assertTrue(r.success);self.assertEqual(s.post.call_count,2);s.close.assert_called_once()

    def test_ein_recovery_still_uses_original_total55_and_two_attempts(self):
        clock=[100.0];sessions=[];search_timeouts=[]
        def make(**kwargs):
            s=MagicMock();s.get.return_value=self.response(FORM,URL)
            def post(url,*args,**kwargs):
                if 'Disclaimer' in url:return self.response(FORM,URL)
                search_timeouts.append(kwargs['timeout']);clock[0]+=kwargs['timeout'];raise TimeoutError('Source timed out')
            s.post.side_effect=post;sessions.append(s);return s
        with patch.object(m.time,'monotonic',lambda:clock[0]),patch.object(m.time,'perf_counter',lambda:clock[0]),patch.object(m.time,'sleep',lambda x:clock.__setitem__(0,clock[0]+x)),patch.object(m.curl_requests,'Session',side_effect=make):
            r=m.search_mi_http_completion_probe(self.org)
        self.assertFalse(r.success);self.assertEqual(r.reason_code,'MI_EIN_TRANSPORT_TIMEOUT')
        self.assertEqual(search_timeouts,[45,9]);self.assertEqual(clock[0],155);self.assertEqual(len(sessions),2)

    def test_all_other_master_and_queue_behavior_unchanged(self):
        from testing.capacity_lab.mi_patient_scope import strip_mi_patient_transport
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','5f5de6b:registry_snapshot_server.py'],cwd=root).decode())
        new=ast.parse(Path(m.__file__).read_text());strip_mi_patient_transport(new)
        self.assertEqual(ast.dump(old),ast.dump(new))
        subprocess.run(['git','diff','--exit-code','5f5de6b','--','deployment'],cwd=root,check=True,capture_output=True)

if __name__=='__main__':unittest.main()
