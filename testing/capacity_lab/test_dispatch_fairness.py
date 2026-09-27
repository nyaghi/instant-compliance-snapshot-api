"""Fair opportunities for slow and fast Sales organizations; unchanged fences."""
import ast, collections, os, subprocess, unittest
from pathlib import Path
from unittest.mock import patch
from deployment.durable_queue import order_workflows, normalize_submission
from testing.capacity_lab.dispatch_scope import strip_dispatch_fairness
from testing.capacity_lab import test_durable_queue as dbtests

def workflow(ident, mode='sales', kind='registration', size=32):
    return {'id':ident,'mode':mode,'kind':kind,'payload':{'states':list(range(size))},
            'submitted':0,'dispatched':0}

def pending(count):
    return [{'state':f'T{i:02}'} for i in range(count)]

class DispatchFairness(unittest.TestCase):
    def ordered(self, ws, waiting, running, policy='tail-aware', version='fixture-performance-lab', flag='1'):
        before = [dict(w) for w in ws]
        with patch.dict(os.environ, {'CE_LAB_SALES_DISPATCH_FAIRNESS':flag}):
            order_workflows(ws, waiting, collections.Counter(running), policy, version)
        self.assertEqual(sorted(ws,key=lambda w:w['id']),sorted(before,key=lambda w:w['id']))
        return [w['id'] for w in ws]

    def test_slow_workflow_gets_opportunity_instead_of_repeatedly_rewarding_fast_completions(self):
        # At halfway: hard has started 11/32, easy 31/32. Seven versus five
        # still running used to penalize the hard workflow for slow sources.
        ws=[workflow('easy'),workflow('hard')]
        wait={'easy':pending(1),'hard':pending(21)}
        self.assertEqual(self.ordered(ws,wait,{'easy':5,'hard':7}),['hard','easy'])
        self.assertEqual(self.ordered(ws,wait,{'easy':5,'hard':7},flag=''),['easy','hard'])

    def test_ties_keep_existing_dispatch_age_then_submission_then_identity(self):
        ws=[workflow('b'),workflow('a')];ws[0]['dispatched']=9;ws[1]['dispatched']=10
        self.assertEqual(self.ordered(ws,{'a':pending(20),'b':pending(20)},{'a':1,'b':9}),['b','a'])
        ws[0]['dispatched']=ws[1]['dispatched']=10
        self.assertEqual(self.ordered(ws,{'a':pending(20),'b':pending(20)},{'a':1,'b':9}),['a','b'])

    def test_single_sales_standard_mixed_discovery_nonlab_and_optout_keep_original_order(self):
        cases=[([workflow('a')],{}),
            ([workflow('a','standard'),workflow('b','standard')],{}),
            ([workflow('a','sales'),workflow('b','standard')],{}),
            ([workflow('a'),workflow('b',kind='discovery')],{}),
            ([workflow('a'),workflow('b')],{'policy':'shortest'}),
            ([workflow('a'),workflow('b')],{'version':'production'}),
            ([workflow('a'),workflow('b')],{'flag':'0'})]
        for ws,kwargs in cases:
            with self.subTest(kwargs=kwargs,ws=ws):
                expected=sorted(ws,key=lambda w:({'a':4,'b':0}[w['id']],0,0,w['id']))
                self.assertEqual(self.ordered(ws,{'a':pending(31),'b':pending(1)},{'a':4,'b':0},**kwargs),[w['id'] for w in expected])

    def test_identity_helpers_are_not_counted_as_registration_dispatches(self):
        ws=[workflow('a'),workflow('b')]
        wait={'a':pending(32),'b':pending(32)+[{'state':'@sales_identity'}]}
        self.assertEqual(self.ordered(ws,wait,{'a':1,'b':0}),['a','b'])

    def test_smaller_selected_state_sets_count_actual_checks_offered(self):
        ws=[workflow('a',size=2),workflow('b',size=32)]
        self.assertEqual(self.ordered(ws,{'a':pending(1),'b':pending(30)},{'a':1,'b':0}),['a','b'])

    def test_entire_queue_outside_ordering_is_identical(self):
        root=Path(__file__).resolve().parents[2]
        before=ast.parse(subprocess.check_output(['git','show','4c9b3af:deployment/durable_queue.py'],cwd=root).decode())
        after=ast.parse((root/'deployment/durable_queue.py').read_text())
        strip_dispatch_fairness(after)
        self.assertEqual(ast.dump(before),ast.dump(after))


@unittest.skipUnless(os.environ.get('CE_TEST_DATABASE_URL'),'Real lab Postgres required')
class DispatchRealDB(unittest.TestCase):
    setUp=dbtests.DurableTests.setUp
    tearDown=dbtests.DurableTests.tearDown
    submit=dbtests.DurableTests.submit
    worker=dbtests.DurableTests.worker
    finish=dbtests.DurableTests.finish

    def test_slow_workflow_gets_next_claim_but_source_slot_and_deadline_fences_hold(self):
        with patch.dict(os.environ,{'CE_LAB_SALES_DISPATCH_FAIRNESS':'1'}):
            self.q.sales_policy='tail-aware'
            states=['CA','CO','LA','ME']
            def request(ein):
                return normalize_submission({'ein':ein,'organization_name':'Dispatch fixture',
                    'mode':'sales','alternate_names':['Reviewed name'],'states':states,'state_concurrency':5},states)
            hard=self.submit(request('123456789'));easy=self.submit(request('987654321'))
            w=self.worker(slots=12)
            with self.q.transaction() as (c,now):
                # Two checks already running for hard, while easy completed
                # three. Retain real reservations for hard's active calls.
                for state in ['CA','CO']:
                    c.execute("UPDATE cc_lab_jobs SET phase='running',owner=%s,token='fixture',attempt=1,claimed=%s,lease_until=%s,run_until=%s WHERE workflow_id=%s AND state=%s",(w,now,now+20,now+60,hard,state))
                c.execute("UPDATE cc_lab_jobs SET phase='done',attempt=1,claimed=%s,finished=%s WHERE workflow_id=%s AND state!='ME'",(now-2,now-1,easy))
                c.execute("UPDATE cc_lab_workflows SET started=%s,phase='active' WHERE id IN (%s,%s)",(now,hard,easy))
            first=self.q.claim(w)
            self.assertEqual(first['workflow_id'],hard)
            # Actual physical capacity remains authoritative, irrespective of
            # the new preferred workflow. No zero-slot claim is permitted.
            self.assertIsNone(self.q.claim(w,slot_limit=0))
            self.finish(first)
            with self.q.transaction() as (c,now):
                c.execute('UPDATE cc_lab_workflows SET deadline=%s WHERE id=%s',(now-1,hard))
            next_job=self.q.claim(w)
            if next_job:self.assertEqual(next_job['workflow_id'],easy)
            status=self.q.status('a',hard)
            self.assertEqual(status['stop_reason'],'deadline')
            self.assertTrue(all(j['phase']!='running' for j in status['jobs']))

if __name__=='__main__':unittest.main()
