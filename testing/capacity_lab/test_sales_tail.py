"""Scheduling controls: no organization names, classifications or fixtures in runtime."""
import unittest
from unittest.mock import Mock
from deployment.durable_queue import Queue, sales_tail_scores, sales_tail_capacity, order_pending

def job(state, org='a'):
    return {'id':org+state,'state':state,'workflow_id':org,'weight':1}
def workflow(org='a',mode='sales',deadline=60):
    return {'id':org,'mode':mode,'deadline':deadline}

class TailScheduling(unittest.TestCase):
    def test_scarce_capacity_preserves_fast_first(self):
        ws=[workflow('a'),workflow('b')]
        pending={w['id']:[job(s,w['id']) for s in ('ME','CO')] for w in ws}
        workers=[{'source_version':'v','slots':1,'heartbeat':0,'retired':False}]
        self.assertFalse(sales_tail_capacity(ws,pending,[],{'ME':40,'CO':1},workers,'v',1))
        workers[0]['slots']=2
        self.assertTrue(sales_tail_capacity(ws,pending,[],{'ME':40,'CO':1},workers,'v',1))
        workers[0]['retired']=True
        self.assertFalse(sales_tail_capacity(ws,pending,[],{'ME':40,'CO':1},workers,'v',1))

    def test_stale_foreign_workers_and_held_standard_work_do_not_create_capacity(self):
        ws=[workflow('a'),workflow('b')]
        pending={w['id']:[job('CO',w['id'])] for w in ws}
        worker={'source_version':'v','slots':1,'heartbeat':0,'retired':False}
        estimates={'CO':2,'ME':100}
        self.assertFalse(sales_tail_capacity(ws,pending,[],estimates,[worker],'v',21))
        self.assertFalse(sales_tail_capacity(ws,pending,[],estimates,[worker],'other',1))
        self.assertFalse(sales_tail_capacity(ws,pending,[{**job('ME','standard'),'claimed':0}],estimates,[worker],'v',1))

    def test_duration_cache_is_bounded_and_never_reuses_missing_states_or_versions(self):
        q=object.__new__(Queue);q._duration_cache=None
        q.duration_estimates=Mock(side_effect=[{'CO':1},{'CO':2},{'ME':5},{'ME':6},{'ME':7}])
        self.assertEqual(q.cached_duration_estimates(None,10,{'CO'},'v'),{'CO':1})
        self.assertEqual(q.cached_duration_estimates(None,14,{'CO'},'v'),{'CO':1})
        self.assertEqual(q.duration_estimates.call_count,1)
        self.assertEqual(q.cached_duration_estimates(None,15,{'CO'},'v'),{'CO':2})
        self.assertEqual(q.cached_duration_estimates(None,16,{'ME'},'v'),{'ME':5})
        self.assertEqual(q.cached_duration_estimates(None,17,{'ME'},'new'),{'ME':6})
        self.assertEqual(q.cached_duration_estimates(None,16,{'ME'},'new'),{'ME':7})

    def test_single_org_preserves_fast_first(self):
        jobs=[job('ME'),job('CO')];w=workflow()
        scores=sales_tail_scores([w],{'a':jobs},[],{'ME':12,'CO':1},{'ME':1})
        self.assertEqual(scores,{})
        order_pending(w,jobs,{'ME':12,'CO':1},scores,0)
        self.assertEqual([j['state'] for j in jobs],['CO','ME'])

    def test_backlog_per_lane_prioritizes_bottleneck(self):
        ws=[workflow('a'),workflow('b')]
        pending={w['id']:[job(s,w['id']) for s in ('AR','ME','CO')] for w in ws}
        estimates={'AR':6,'ME':8,'CO':1}
        scores=sales_tail_scores(ws,pending,[],estimates,{'AR':1,'ME':4,'CO':4})
        self.assertEqual(scores,{'AR':12,'ME':4,'CO':.5})
        order_pending(ws[0],pending['a'],estimates,scores,0)
        self.assertEqual([j['state'] for j in pending['a']],['AR','ME','CO'])

    def test_standard_and_identity_order_are_preserved(self):
        estimates={'ME':15,'CO':2,'@sales_identity':1}
        for mode in ('sales','standard'):
            jobs=[job('CO'),job('ME'),job('@sales_identity')]
            order_pending(workflow(mode=mode),jobs,estimates,{'CO':99,'ME':1},0)
            self.assertEqual(jobs[0]['state'],'@sales_identity')
            self.assertEqual(jobs[1]['state'],'ME' if mode=='standard' else 'CO')

    def test_too_slow_work_does_not_displace_feasible_result(self):
        jobs=[job('ME'),job('CO')]
        order_pending(workflow(),jobs,{'ME':20,'CO':2},{'ME':100,'CO':1},55)
        self.assertEqual([j['state'] for j in jobs],['CO','ME'])

    def test_foreign_mode_work_cannot_inflate_sales_demand(self):
        ws=[workflow('a'),workflow('b'),workflow('c','standard')]
        pending={'a':[job('AR')],'b':[job('AR','b')],'c':[job('CO','c')]}
        scores=sales_tail_scores(ws,pending,[job('ME','a'),job('CO','c')],{'AR':3,'ME':5,'CO':100},{'AR':2})
        self.assertEqual(scores,{'AR':3,'ME':1.25})

if __name__=='__main__':unittest.main()
