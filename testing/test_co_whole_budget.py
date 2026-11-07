import ast,time,unittest
from pathlib import Path
from unittest.mock import patch
from deployment import co_budget as budget
from deployment.state_snapshots import DEADLINE

class WholeBudget(unittest.TestCase):
 def scope(self,lookup):
  source=Path('registry_snapshot_server.py').read_text(encoding='utf-8')
  names={'_run_single_state_lookup_reliably_source','_run_single_state_lookup_reliably_core','search_co_with_name_fallback'}
  tree=ast.Module(body=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[])
  scope=dict(time=time,SINGLE_STATE_SEMANTIC_RETRY_ATTEMPTS=2,SINGLE_STATE_SEMANTIC_RETRY_STATES={'CO','NJ'},SINGLE_STATE_SEMANTIC_RETRY_DELAY_SECONDS=0,run_state_lookup=lookup,transient_negative_text=lambda r:'',is_incomplete_no_match_result=lambda *a:False)
  exec(compile(tree,'registry_snapshot_server.py','exec'),scope);return scope
 def test_semantic_retry_shares_original_deadline(self):
  clock=[100.0];allowances=[];scope=None
  def lookup(*args):
   def inner(*unused):
    allowances.append(budget.timeout(45000));clock[0]+=min(35,allowances[-1]/1000)
    return {'status':'Site Not Reachable','reason_code':'RUNNER_TIMEOUT','success':False}
   scope['search_co_with_name_fallback_core']=inner
   return scope['search_co_with_name_fallback'](None,None)
  scope=self.scope(lookup)
  with patch.object(budget.time,'monotonic',side_effect=lambda:clock[0]):
   result=scope['_run_single_state_lookup_reliably_source']('Example','123456789','CO')
  self.assertEqual(allowances,[45000,25000]);self.assertEqual(result['co_budget_metrics']['elapsed_seconds'],60)
  self.assertEqual(result['status'],'Site Not Reachable');self.assertEqual(budget.STOP.get(),float('inf'))
 def test_exhausted_first_attempt_does_not_start_second(self):
  clock=[100.0];calls=[]
  def lookup(*args):calls.append(args);clock[0]+=60;return {'status':'Site Not Reachable','success':False}
  scope=self.scope(lookup)
  with patch.object(budget.time,'monotonic',side_effect=lambda:clock[0]):result=scope['_run_single_state_lookup_reliably_source']('Example','123456789','CO')
  self.assertEqual(len(calls),1);self.assertEqual(result['semantic_attempts'],1)
 def test_healthy_result_and_other_state_unchanged(self):
  for state in ['CO','NJ']:
   calls=[]
   def lookup(*args):calls.append(args);return {'status':'Current','success':True,'evidence_url':'original.pdf'}
   result=self.scope(lookup)['_run_single_state_lookup_reliably_source']('Example','123456789',state)
   self.assertEqual(len(calls),1);self.assertEqual(result['evidence_url'],'original.pdf')
   self.assertEqual('co_budget_metrics' in result,state=='CO')
 def test_deadline_and_context_restored_after_exception(self):
  old=DEADLINE.get()
  with self.assertRaises(ValueError):budget.run(lambda:(_ for _ in ()).throw(ValueError()))
  self.assertEqual(DEADLINE.get(),old);self.assertEqual(budget.STOP.get(),float('inf'))

if __name__=='__main__':unittest.main()
