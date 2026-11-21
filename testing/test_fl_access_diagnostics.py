import ast,copy,json,subprocess,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from deployment import fl_access_diagnostics as f
from deployment.workflow_observation import Observation,ACTIVE
ROOT=Path(__file__).resolve().parents[1]
class Diagnostics(unittest.TestCase):
 def test_exact_result_arguments_and_exception_preserved(self):
  tr=Observation('test','FL');token=ACTIVE.set(tr)
  try:
   result=object();seen=[]
   self.assertIs(f.call('business_get',lambda *a,**k:seen.append((a,k)) or result,1,timeout=4),result)
   self.assertEqual(seen,[((1,),{'timeout':4})])
   exc=TimeoutError('secret-credential https://example.org/private?token=hidden net::ERR_TIMED_OUT')
   def bad():raise exc
   with self.assertRaises(TimeoutError) as caught:f.call('browser_entry',bad)
   self.assertIs(caught.exception,exc)
   raw=json.dumps(tr.export());self.assertNotIn('secret-credential',raw);self.assertNotIn('hidden',raw);self.assertNotIn('example.org',raw)
   self.assertIn('net::ERR_TIMED_OUT',raw)
  finally:ACTIVE.reset(token)
 def test_protocol_phase_from_exception_frames(self):
  for name,phase in [('getaddrinfo','dns'),('create_connection','tcp_connect'),('do_handshake','tls'),('_read_status','response_headers'),('read1','response_body')]:
   ns={};exec('def '+name+'():\n raise TimeoutError("private")',ns)
   try:ns[name]()
   except TimeoutError as exc:self.assertEqual(f._failure(exc)['protocol_phase'],phase)
 def test_non_florida_unchanged_and_inactive(self):
  for state in ['NC','WI','AK','']:
   tr=Observation('test',state);token=ACTIVE.set(tr)
   try:self.assertEqual(f.call('business_get',lambda:7),7);self.assertFalse(tr.events)
   finally:ACTIVE.reset(token)
 def test_observer_failure_and_cancellation_preserved(self):
  tr=SimpleNamespace(state='FL',emit=lambda *a,**k:(_ for _ in ()).throw(ValueError('observer')));token=ACTIVE.set(tr)
  class Cancel(BaseException):pass
  try:
   self.assertEqual(f.call('business_get',lambda:9),9)
   with self.assertRaises(Cancel):f.call('business_get',lambda:(_ for _ in ()).throw(Cancel()))
   with patch.object(f.time,'perf_counter',side_effect=RuntimeError('clock')):self.assertEqual(f.call('business_get',lambda:11),11)
  finally:ACTIVE.reset(token)
 def test_bounded_journal_preserves_failure(self):
  tr=Observation('test','FL');token=ACTIVE.set(tr)
  try:
   for i in range(1000):f.call('business_body',lambda:b'ok')
   self.assertLessEqual(len(tr.events),96)
   with self.assertRaises(TimeoutError):f.call('business_get',lambda:(_ for _ in ()).throw(TimeoutError()))
   self.assertEqual(tr.events[-1]['outcome'],'exception')
  finally:ACTIVE.reset(token)
 def test_browser_error_and_timing_redacted(self):
  r=SimpleNamespace(failure='net::ERR_CONNECTION_RESET url=https://private/?secret=token',timing={'startTime':1,'connectStart':2,'responseStart':float('nan'),'secret':'never','bool':True})
  data=f.browser_failure_fields(r,True);self.assertEqual(data,{'network_error_code':'net::ERR_CONNECTION_RESET','network_timing_ms':{'startTime':1,'connectStart':2}})
 def test_master_equivalence_removing_diagnostics_only(self):
  old=ast.parse(subprocess.check_output(['git','show','5d31c2b:registry_snapshot_server.py'],cwd=ROOT).decode('utf-8'))
  new=ast.parse((ROOT/'registry_snapshot_server.py').read_text(encoding='utf-8'))
  class Strip(ast.NodeTransformer):
   def visit_ImportFrom(self,n):return None if n.module=='deployment.fl_access_diagnostics' else n
   def visit_Call(self,n):
    n=self.generic_visit(n)
    if isinstance(n.func,ast.Name) and n.func.id=='fl_access_call':return ast.Call(func=n.args[1],args=n.args[2:],keywords=n.keywords)
    return n
   def visit_With(self,n):
    n=self.generic_visit(n);n.items=[x for x in n.items if not(isinstance(x.context_expr,ast.Call) and isinstance(x.context_expr.func,ast.Name) and x.context_expr.func.id=='fl_access_step')];return n
  self.assertEqual(ast.dump(old),ast.dump(Strip().visit(new)))
if __name__=='__main__':unittest.main()
