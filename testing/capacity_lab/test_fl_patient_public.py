"""A slow complete public response must not cause an avoidable browser retry."""
import ast,copy,os,subprocess,time,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
import registry_snapshot_server as m
import testing.capacity_lab.test_fl_business_lookup as fixture
source=fixture.source

class PatientPublic(unittest.TestCase):
    def opener(self,slow=False,partial=False):
        t=fixture.Transport();op=MagicMock();responses=[t.response('<html><input type="hidden" name="__VIEWSTATE" value="fixture"></html>'),t.response(source()[:-7] if partial else source())]
        def open(request,timeout):
            if slow and request.data and timeout<6:raise TimeoutError('simulated complete response requires six seconds')
            return responses.pop(0)
        op.open.side_effect=open;return op

    def lookup(self,op,enabled=True,flag='1',deadline=None):
        with patch.object(m,'fl_business_lookup_enabled',return_value=enabled),patch.dict(os.environ,{'CE_LAB_FL_HTTP_PATIENT':flag}),patch.object(m.urllib.request,'build_opener',return_value=op),patch.object(m,'fl_verified_ssl_context',return_value='verified'):
            return m.fl_business_public_rows('Example Relief',deadline or time.monotonic()+30)

    def test_slow_complete_post_keeps_exact_public_record(self):
        op=self.opener(slow=True);rows=self.lookup(op)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['business_evidence']['identifier'],'CH12345')
        self.assertTrue(all(0<c.kwargs['timeout']<=8 for c in op.open.call_args_list))
        self.assertGreater(op.open.call_args_list[1].kwargs['timeout'],6)

    def test_default_and_non_lab_keep_original_four_second_bound(self):
        for enabled,flag in ((True,'0'),(False,'1')):
            with self.subTest(enabled=enabled,flag=flag):
                op=self.opener(slow=True);self.assertEqual(self.lookup(op,enabled,flag),[])
                self.assertTrue(all(c.kwargs['timeout']<=4 for c in op.open.call_args_list))

    def test_remaining_lookup_deadline_still_wins(self):
        with patch.object(m.time,'monotonic',return_value=100):
            op=self.opener();self.assertEqual(len(self.lookup(op,deadline=105)),1)
        self.assertTrue(all(c.kwargs['timeout']<=5 for c in op.open.call_args_list))

    def test_longer_wait_never_accepts_partial_or_untrusted_response(self):
        self.assertEqual(self.lookup(self.opener(slow=True,partial=True)),[])
        op=MagicMock();op.open.side_effect=m.ssl.SSLCertVerificationError()
        self.assertEqual(self.lookup(op),[]);self.assertEqual(op.open.call_count,1)

    def test_only_lab_bounded_transport_constants_change(self):
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','8f41320:registry_snapshot_server.py'],cwd=root).decode())
        new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'))
        from testing.capacity_lab.ny_body_scope import strip_ny_body_completion
        strip_ny_body_completion(new)
        original=next(n for n in old.body if getattr(n,'name','')=='fl_business_public_rows')
        fn=next(n for n in new.body if getattr(n,'name','')=='fl_business_public_rows')
        assign=next(n for n in fn.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='http_seconds' for t in n.targets))
        expected=ast.parse('http_seconds = 8.0 if fl_business_lookup_enabled() and os.environ.get("CE_LAB_FL_HTTP_PATIENT") == "1" else 4.0').body[0]
        self.assertEqual(ast.dump(assign),ast.dump(expected));fn.body.remove(assign)
        fn.body[0]=copy.deepcopy(original.body[0])
        for n in ast.walk(fn):
            if isinstance(n,ast.BinOp) and isinstance(n.op,ast.Add) and ast.unparse(n.right)=='2 * http_seconds':n.right=ast.Constant(8.0)
            if isinstance(n,ast.Call) and ast.unparse(n.func)=='min' and ast.unparse(n.args[0])=='http_seconds':n.args[0]=ast.Constant(4.0)
        self.assertEqual(ast.dump(old),ast.dump(new))

if __name__=='__main__':unittest.main()
