"""Longer source searches start earlier without changing single-run behavior."""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock
from deployment.durable_queue import DurationEstimates, Queue, order_pending, sales_tail_scores
from testing.capacity_lab.test_sales_tail import job, workflow


class TailPercentile(unittest.TestCase):
    def fixture(self):
        return DurationEstimates([{'state':'SC','seconds':3,'tail_seconds':30},
                                  {'state':'MI','seconds':12,'tail_seconds':15}])

    def test_rare_long_searches_get_priority_over_lower_variation(self):
        estimates=self.fixture();ws=[workflow('a'),workflow('b')]
        pending={w['id']:[job('SC',w['id']),job('MI',w['id'])] for w in ws}
        scores=sales_tail_scores(ws,pending,[],estimates,{'SC':4,'MI':4})
        self.assertEqual(scores,{'SC':15,'MI':7.5})
        order_pending(ws[0],pending['a'],estimates,scores,0)
        self.assertEqual([j['state'] for j in pending['a']],['SC','MI'])
        self.assertEqual(estimates,{'SC':3,'MI':12})

    def test_single_sales_and_standard_keep_median_order(self):
        estimates=self.fixture()
        for mode,expected in [('sales',['SC','MI']),('standard',['MI','SC'])]:
            w=workflow(mode=mode);jobs=[job('MI'),job('SC')]
            scores=sales_tail_scores([w],{'a':jobs},[],estimates,{'SC':1,'MI':4})
            self.assertEqual(scores,{})
            order_pending(w,jobs,estimates,scores,0)
            self.assertEqual([j['state'] for j in jobs],expected)

    def test_tail_is_only_urgency_not_a_reason_to_skip_feasible_work(self):
        w=workflow();jobs=[job('SC'),job('MI')];estimates=self.fixture()
        order_pending(w,jobs,estimates,{'SC':15,'MI':7.5},55)
        self.assertEqual([j['state'] for j in jobs],['SC','MI'])
        self.assertEqual(len(jobs),2)

    def test_empty_history_keeps_original_default_and_uses_one_query(self):
        c=Mock();c.execute.return_value=[]
        estimates=Queue.duration_estimates(c,100000,{'SC','MI'})
        self.assertEqual(estimates,{});self.assertEqual(estimates.tails,{})
        c.execute.assert_called_once()
        query=c.execute.call_args.args[0]
        self.assertIn('LIMIT 20',query);self.assertIn('percentile_cont(0.5)',query)
        self.assertIn('percentile_cont(0.95)',query)
        self.assertNotIn('payload',query);self.assertNotIn('result',query)

    def test_only_tail_timing_changes_entire_queue_ast(self):
        from testing.capacity_lab.tail_scope import strip_tail_latency
        source=Path(__file__).resolve().parents[2]/'deployment/durable_queue.py'
        strip_tail_latency(ast.parse(source.read_text()))


if __name__=='__main__':unittest.main()
