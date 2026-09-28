"""Bounded CO grace retains exact identity, source permits and total cutoff."""
import ast,json,os,subprocess,time,unittest
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as m
from deployment.lab_capacity import sales_identity_seconds
from deployment.queue_engine import execute

class IdentityGrace(unittest.TestCase):
    def test_lab_only_opt_in(self):
        for flag in ('0','1'):
            with patch.dict(os.environ,{'CE_LAB_SALES_IDENTITY_GRACE':flag}):
                self.assertEqual(sales_identity_seconds('release-staging'),6)
                self.assertEqual(sales_identity_seconds('release-production'),6)
                self.assertEqual(sales_identity_seconds('release-performance-lab'),10 if flag=='1' else 6)

    def test_only_co_gets_extra_time_and_partial_failure_stays_conservative(self):
        def co(ein,deadline,**kw):
            self.assertEqual(ein,'123456789');self.assertEqual(kw,{'request_timeout':10})
            self.assertAlmostEqual(deadline-start,10,delta=.2)
            raise TimeoutError()
        def irs(ein,deadline,**kw):
            self.assertAlmostEqual(deadline-start,6,delta=.2)
            self.assertEqual(kw,{'latest_only':True});return {'complete':True,'names':[]}
        with patch.object(m,'identity_co_names',side_effect=co),patch.object(m,'identity_irs_names',side_effect=irs),patch.object(m,'identity_or_names',return_value={'complete':True,'names':[]}):
            start=time.monotonic();r=m.sales_identity_evidence('Example','123456789',budget_seconds=10)
        self.assertEqual(r['errors'],{'CO':'TimeoutError'});self.assertEqual(set(r['source_seconds']),{'CO','IRS','OR'})
        self.assertEqual(m.sales_result_with_identity({'ein':'123456789','state':'DC','status':'Not Registered'},r)['status'],'Unable to Confirm')

    def test_co_default_transport_and_exact_ein_remain(self):
        rows=[{'fein':'98-7654321','name':'Wrong entity'},{'fein':'12-3456789','name':'Requested entity','entityid':'a'}]
        for seconds in (6,10):
            with patch.object(m,'identity_fetch',return_value=json.dumps(rows).encode()) as fetch:
                r=m.identity_co_names('123456789',100,**({'request_timeout':10} if seconds==10 else {}))
            self.assertEqual(fetch.call_args.kwargs,{'request_timeout':seconds})
            self.assertEqual([n['name'] for n in r['names']],['Requested entity'])
            self.assertTrue(r['complete'])

    def test_only_worker_preparation_receives_lab_allowance(self):
        job={'version':'fixture-performance-lab','state':'@sales_identity','payload':{'ein':'123456789','organization_name':'Example'}}
        with patch.object(m,'APP_VERSION',job['version']),patch.dict(os.environ,{'CE_LAB_SALES_IDENTITY_GRACE':'1'}),patch.object(m,'sales_identity_evidence',return_value={}) as call:
            execute(m,job)
            call.assert_called_once_with('Example','123456789',budget_seconds=10)
        with self.assertRaises(ValueError):m.sales_identity_evidence('Example','123456789',budget_seconds=60)

    def test_master_scope_preserves_every_other_function(self):
        from testing.capacity_lab.nj_budget_scope import strip_nj_name_budget
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','be53a50:registry_snapshot_server.py'],cwd=root).decode())
        new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'));strip_nj_name_budget(new)
        self.assertEqual(ast.dump(old),ast.dump(new))

    def test_queue_and_engine_preserve_every_other_operation(self):
        from testing.capacity_lab.identity_grace_scope import strip_identity_grace_queue,strip_identity_grace_engine
        root=Path(m.__file__).parent
        for path,strip in [('deployment/durable_queue.py',strip_identity_grace_queue),('deployment/queue_engine.py',strip_identity_grace_engine)]:
            old=ast.parse(subprocess.check_output(['git','show','be53a50:'+path],cwd=root).decode())
            new=ast.parse((root/path).read_text());strip(new)
            self.assertEqual(ast.dump(old),ast.dump(new),path)

if __name__=='__main__':unittest.main()
