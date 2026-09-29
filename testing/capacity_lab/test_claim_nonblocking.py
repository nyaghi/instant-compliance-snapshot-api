"""Claim contention must not delay supervision or bypass scheduling fences."""
import ast,subprocess,unittest
from pathlib import Path
from unittest.mock import MagicMock
from deployment.durable_queue import Queue

class NonblockingClaims(unittest.TestCase):
 def queue(self, acquired):
  q=Queue.__new__(Queue);q.pool=MagicMock();q.lock=123
  c=q.pool.connection.return_value.__enter__.return_value
  lock=MagicMock();lock.fetchone.return_value={'acquired':acquired}
  clock=MagicMock();clock.fetchone.return_value={'t':10}
  c.execute.side_effect=[lock,clock]
  return q,c,lock,clock

 def test_busy_try_lock_yields_no_connection_or_clock_and_no_admission(self):
  q,c,lock,clock=self.queue(False)
  with q.transaction(blocking=False) as value:self.assertIsNone(value)
  self.assertIn('pg_try_advisory_xact_lock',c.execute.call_args_list[0].args[0])
  clock.fetchone.assert_not_called()
  self.assertEqual(c.execute.call_count,2)

 def test_acquired_try_lock_preserves_authoritative_clock(self):
  q,c,lock,clock=self.queue(True)
  with q.transaction(blocking=False) as value:self.assertEqual(value,(c,10.0))

 def test_completion_heartbeat_cancel_default_still_block_and_fence(self):
  q,c,lock,clock=self.queue(False)
  with q.transaction() as value:self.assertEqual(value,(c,10.0))
  self.assertEqual(c.execute.call_args_list[0].args[0],'SELECT pg_advisory_xact_lock(%s)')
  lock.fetchone.assert_not_called()

 def test_only_claim_entry_and_transaction_acquisition_changed(self):
  root=Path(__file__).resolve().parents[2]
  old=subprocess.check_output(['git','show','7104970:deployment/durable_queue.py'],cwd=root,text=True)
  new=(root/'deployment/durable_queue.py').read_text()
  before,after=ast.parse(old),ast.parse(new)
  from testing.capacity_lab.tail_scope import strip_tail_latency
  strip_tail_latency(after)
  oldq=next(n for n in before.body if isinstance(n,ast.ClassDef) and n.name=='Queue')
  newq=next(n for n in after.body if isinstance(n,ast.ClassDef) and n.name=='Queue')
  originals={n.name:n for n in oldq.body if isinstance(n,ast.FunctionDef)}
  changed={n.name:n for n in newq.body if isinstance(n,ast.FunctionDef)}
  claim=changed['claim'];oldclaim=originals['claim']
  self.assertEqual(ast.dump(ast.Module(body=claim.body[0].body[2:],type_ignores=[])),
                   ast.dump(ast.Module(body=oldclaim.body[0].body,type_ignores=[])))
  self.assertEqual(claim.body[0].items[0].context_expr.keywords[0].arg,'blocking')
  self.assertIs(claim.body[0].items[0].context_expr.keywords[0].value.value,False)
  for index,node in enumerate(newq.body):
   if isinstance(node,ast.FunctionDef) and node.name in {'claim','transaction'}:newq.body[index]=originals[node.name]
  self.assertEqual(ast.dump(before),ast.dump(after))

if __name__=='__main__':unittest.main()
