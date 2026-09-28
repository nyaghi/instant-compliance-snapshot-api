"""Selected request gets remaining original time; queries and identity stay exact."""
import ast,os,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as m
from testing.capacity_lab.test_nj_public_query import PublicQuery,DETAIL
from testing.capacity_lab.nj_patient_scope import strip_nj_patient_detail

ENV={'PUBLIC_BASE_URL':'https://instant-compliance-snapshot-api-hn4v.onrender.com',
     'CE_LAB_NJ_PUBLIC_QUERY':'1','CE_LAB_NJ_PATIENT_DETAIL':'1'}

class PatientDetail(unittest.TestCase):
    def setUp(self):
        p=patch.dict(os.environ,ENV);p.start();self.addCleanup(p.stop)
        p=patch.object(m,'APP_VERSION','test-performance-lab');p.start();self.addCleanup(p.stop)
        token=m.LAB_LOOKUP_MODE_CONTEXT.set('sales');self.addCleanup(m.LAB_LOOKUP_MODE_CONTEXT.reset,token)

    def test_only_selected_detail_gets_longer_request_within_original_remaining(self):
        self.assertEqual(m.nj_public_request_timeout('/CHR-Public-Details-Page/?id=known&rid=known',18),10)
        self.assertEqual(m.nj_public_request_timeout('/CHR-Public-Details-Page/?id=known&rid=known',2),2)
        for path in ['/Charity-Registration/CHR-Public-Search-Page/','/_layout/tokenhtml',
                     '/_services/entity-grid-data.json/known','/retrieveRegistration/?name=test',
                     'https://other.test/CHR-Public-Details-Page/?id=bad']:
            self.assertEqual(m.nj_public_request_timeout(path,18),4)

    def test_standard_nonlab_and_disabled_keep_four_seconds(self):
        for mode,version,host,flag in [('standard','v-performance-lab',ENV['PUBLIC_BASE_URL'],'1'),
            ('sales','v',ENV['PUBLIC_BASE_URL'],'1'),
            ('sales','v-performance-lab','https://staging.compliance-express.com','1'),
            ('sales','v-performance-lab',ENV['PUBLIC_BASE_URL'],'0')]:
            with patch.object(m,'APP_VERSION',version),patch.dict(os.environ,{'PUBLIC_BASE_URL':host,'CE_LAB_NJ_PATIENT_DETAIL':flag}):
                token=m.LAB_LOOKUP_MODE_CONTEXT.set(mode)
                try:self.assertEqual(m.nj_public_request_timeout('/CHR-Public-Details-Page/?id=known',18),4)
                finally:m.LAB_LOOKUP_MODE_CONTEXT.reset(token)

    def fixture(self,detail_seconds=7,body=DETAIL):
        f=PublicQuery();f.setUp();self.addCleanup(f.doCleanups);f.detail=body
        original=f.request;seen=[]
        def request(method,url,**kwargs):
            seen.append(kwargs['timeout'])
            detail='/CHR-Public-Details-Page/' in url
            # The inherited fixture asserts the original4s contract. Observe
            # the actual limit above, then reuse only its response construction.
            response=original(method,url,**{**kwargs,'timeout':min(4,kwargs['timeout'])})
            f.clock[0]+=detail_seconds if detail else 1
            return response
        f.session.request.side_effect=request
        return f,seen

    def test_complete_detail_after_seven_seconds_keeps_confirmed_result(self):
        f,seen=self.fixture()
        with patch.object(m.time,'monotonic',side_effect=lambda:f.clock[0]):
            result,_=m.search_nj_public_details(f.org)
        self.assertTrue(result.success);self.assertEqual(result.matched_registry_identifier,f.org.ein)
        self.assertEqual(result.computed_due_date,'6/30/2027')
        self.assertEqual(seen,[4,4,4,4,4,10]);self.assertEqual(f.clock[0],12)
        self.assertTrue(all(r.close.call_count==1 for r in f.responses))

    def test_body_after_original_eighteen_second_deadline_is_rejected(self):
        f,seen=self.fixture(detail_seconds=13.1)
        with patch.object(m.time,'monotonic',side_effect=lambda:f.clock[0]):
            self.assertIsNone(m.search_nj_public_details(f.org))
        self.assertEqual(len(seen),6);self.assertAlmostEqual(f.clock[0],18.1)
        self.assertTrue(all(r.close.call_count==1 for r in f.responses))

    def test_longer_wait_never_accepts_wrong_identity_or_incomplete_body(self):
        for body in [DETAIL.replace('123456789','987654321'),DETAIL.replace('CH12345','CH54321'),
                     DETAIL.replace('</html>',''),DETAIL.replace('crsm_fiscalyearenddate','missing')]:
            with self.subTest(body=body):
                f,_=self.fixture(body=body)
                with patch.object(m.time,'monotonic',side_effect=lambda:f.clock[0]):
                    self.assertIsNone(m.search_nj_public_details(f.org))
                f.doCleanups()

    def test_entire_master_except_selected_detail_limit_is_unchanged(self):
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','d7d0afa:registry_snapshot_server.py'],cwd=root).decode())
        new=ast.parse((root/'registry_snapshot_server.py').read_text());strip_nj_patient_detail(new)
        self.assertEqual(ast.dump(old),ast.dump(new))
        for path in ['deployment/durable_queue.py','deployment/lab_capacity.py','deployment/queue_schema.sql']:
            if path=='deployment/durable_queue.py':
                from testing.capacity_lab.me_application_scope import assert_queue_recovery_only
                assert_queue_recovery_only(root,'d7d0afa')
            else:subprocess.run(['git','diff','--exit-code','d7d0afa','--',path],cwd=root,check=True)

if __name__=='__main__':unittest.main(verbosity=2)
