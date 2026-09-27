"""Empty claims must not monopolize the queue or delay task termination."""
import ast
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch
from deployment import queue_worker as w


class Clock:
    def __init__(self, end): self.now=0.0;self.end=end
    def is_set(self): return self.now >= self.end
    def wait(self, delay): self.now += delay


class EmptyClaims(unittest.TestCase):
    def run_worker(self, end, deadline, defer=False):
        clock=Clock(end);queue=Mock();queue.claim.return_value=None
        queue.heartbeat.return_value=['running']
        supervisor=w.Supervisor(queue,'fixture-performance-lab',8,command=['fixture'],env={})
        supervisor.stop_event=clock
        if defer: supervisor.claim_backoff.next_attempt=10
        tree=Mock();tree.poll.return_value=None;stopped=[]
        tree.stop.side_effect=lambda:stopped.append(clock.now)
        output=Mock();output.is_file.return_value=False
        supervisor.active={'running':{'job':{'id':'running','state':'CO','weight':1,'token':'token'},
            'tree':tree,'output':output,'temp':Mock(),'deadline':deadline}}
        with patch.object(w.time,'monotonic',side_effect=lambda:clock.now):supervisor.run()
        return supervisor,queue,clock,stopped

    def test_empty_polling_drops_without_stalling_heartbeats(self):
        _,queue,clock,_=self.run_worker(10,100)
        self.assertLess(queue.claim.call_count,25)  # Old active loop tried about100.
        self.assertGreater(queue.claim.call_count,8)
        self.assertGreaterEqual(queue.heartbeat.call_count,4)

    def test_task_deadline_is_enforced_during_long_claim_backoff(self):
        supervisor,queue,_,stopped=self.run_worker(.8,.35,True)
        self.assertGreaterEqual(stopped[0],.35);self.assertLessEqual(stopped[0],.5)
        completion=queue.complete_many.call_args.args[1][0]
        self.assertEqual(completion[3],'TASK_TIME_LIMIT')
        self.assertEqual(supervisor.active,{})

    def test_new_capacity_resets_backoff_only_after_persistence(self):
        from testing.capacity_lab.test_completion_batch import CompletionBatchTests
        s=CompletionBatchTests().supervisor();s.claim_backoff.observe(False,10)
        s.queue.complete_many.side_effect=OSError('database offline')
        s.persist_terminated();self.assertFalse(s.claim_backoff.ready(10));self.assertEqual(len(s.active),3)
        s.queue.complete_many.side_effect=None;s.persist_terminated()
        self.assertTrue(s.claim_backoff.ready(10));self.assertEqual(set(s.active),{'2'})

    def test_eligible_work_has_no_added_claim_delay(self):
        b=w.EmptyClaimBackoff()
        for tick in range(20):
            self.assertTrue(b.ready(tick*.01));b.observe(True,tick*.01)

    def test_backoff_is_bounded_and_workers_have_different_phases(self):
        low,high=w.EmptyClaimBackoff(0),w.EmptyClaimBackoff(1)
        for tick in range(20):low.observe(False,tick);high.observe(False,tick)
        self.assertAlmostEqual(low.next_attempt-19,.5)
        self.assertAlmostEqual(high.next_attempt-19,.75)
        self.assertFalse(high.ready(19.74));self.assertTrue(high.ready(19.75))

    def test_only_claim_pacing_changed_in_worker(self):
        from testing.capacity_lab.parsing_scope import strip_empty_claim_backoff
        root=Path(__file__).resolve().parents[2]
        old=ast.parse(subprocess.check_output(['git','show','c6e1a7a:deployment/queue_worker.py'],cwd=root).decode())
        new=ast.parse((root/'deployment/queue_worker.py').read_text());strip_empty_claim_backoff(new)
        self.assertEqual(ast.dump(old),ast.dump(new))


if __name__=='__main__':unittest.main()
