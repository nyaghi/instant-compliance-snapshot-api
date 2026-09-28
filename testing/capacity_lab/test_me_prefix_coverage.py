"""Complete literal-prefix proofs, private scope, negatives, and unchanged rules."""
import ast,io,json,os,subprocess,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import registry_snapshot_server as m
from testing.capacity_lab.me_prefix_scope import strip_me_prefix_coverage

ENV={'PUBLIC_BASE_URL':'https://instant-compliance-snapshot-api-hn4v.onrender.com',
     'CE_LAB_ME_PREFIX_COVERAGE':'1'}
BODY='<html><body><input id="cbActiveOnly" type="checkbox">2 records found.</body></html>'
ROWS=[{'name':'Example Relief','number':'CO1','status':'ACTIVE'},
      {'name':'Example Relief Chapter','number':'CO2','status':'ACTIVE'}]
QUERIES=['Example Relief','Example-Relief','ExampleRelief','The Example Relief']
EMPTY_FORM='''<html><body><form id="SearchForm">
<input name="ctl00$scCompanyName" value="example" maxlength="30">
<select name="ctl00$scRegulator"><option selected="selected" value="4076">CHARITABLE SOLICITATION</option></select>
<input name="ctl00$ctl24" type="radio" value="BW" checked="checked">
No records found for the search criteria entered.</form></body></html>'''

class PrefixCoverage(unittest.TestCase):
    def setUp(self):
        p=patch.dict(os.environ,ENV);p.start();self.addCleanup(p.stop)
        p=patch.object(m,'APP_VERSION','test-performance-lab');p.start();self.addCleanup(p.stop)
        token=m.LAB_LOOKUP_MODE_CONTEXT.set('sales');self.addCleanup(m.LAB_LOOKUP_MODE_CONTEXT.reset,token)
    def session(self,body=BODY,rows=ROWS):
        class Session:
            def __init__(self):self.calls=[];self.completed_search_html=body
            def search(self,q):self.calls.append(q);return [dict(r) for r in rows],self
        return Session()
    def test_original_first_query_stays_fast_then_complete_prefix_covers_remaining_variants(self):
        s=self.session()
        for q in QUERIES[:3]:
            rows,reader=m.me_search_with_prefix_coverage(s,q,QUERIES)
            self.assertIs(reader,s);self.assertEqual(rows,ROWS)
            self.assertEqual(s.covered_source_query,'' if q==QUERIES[0] else 'example')
        self.assertEqual(s.calls,[QUERIES[0],'example'])
        m.me_search_with_prefix_coverage(s,QUERIES[-1],QUERIES)
        self.assertEqual(s.calls,[QUERIES[0],'example',QUERIES[-1]])
        self.assertEqual(s.covered_source_query,'')
    def test_partial_filtered_truncated_or_ambiguous_lists_save_no_queries(self):
        for body in [BODY.replace('2 records','3 records'),BODY.replace('</html>',''),
                     BODY.replace('type="checkbox"','type="checkbox" checked'),
                     BODY.replace('2 records found.','2 records found. 2 records found.'),
                     BODY.replace('2 records','1,002 records'),
                     BODY.replace('2 records','0,,02 records'),
                     BODY.replace('cbActiveOnly','other')]:
            with self.subTest(body=body):
                s=self.session(body)
                for q in QUERIES[1:3]:m.me_search_with_prefix_coverage(s,q,QUERIES)
                self.assertEqual(s.calls,['example',*QUERIES[1:3]])
                self.assertEqual(s.covered_source_query,'')
    def test_completed_zero_covers_only_original_literal_prefixes(self):
        s=self.session(BODY.replace('2 records','0 records'),[])
        for q in QUERIES[1:3]:self.assertEqual(m.me_search_with_prefix_coverage(s,q,QUERIES)[0],[])
        self.assertEqual(s.calls,['example'])
        m.me_search_with_prefix_coverage(s,'Different Former Name',QUERIES)
        self.assertEqual(s.calls[-1],'Different Former Name')
    def test_real_empty_form_shape_confirms_exact_query_and_category(self):
        self.assertTrue(m.me_complete_prefix_list(EMPTY_FORM,[],'example'))
        for body,query in [(EMPTY_FORM,'stale query'),(EMPTY_FORM.replace('4076','9999'),'example'),
            (EMPTY_FORM.replace('value="BW"','value="C"'),'example'),
            (EMPTY_FORM.replace('checked="checked"',''),'example'),
            (EMPTY_FORM.replace('</html>',''),'example'),
            (EMPTY_FORM.replace('No records found for the search criteria entered.','Loading'),'example'),
            (EMPTY_FORM.replace('id="SearchForm"','id="Other"'),'example')]:
            self.assertFalse(m.me_complete_prefix_list(body,[],query))
        self.assertFalse(m.me_complete_prefix_list(EMPTY_FORM,ROWS,'example'))
    def test_empty_form_respects_live_truncation_and_literal_apostrophe(self):
        query="example's longer name";body=EMPTY_FORM.replace('value="example"','value="'+query+'"')
        self.assertTrue(m.me_complete_prefix_list(body,[],query))
        body=EMPTY_FORM.replace('maxlength="30"','maxlength="7"')
        self.assertTrue(m.me_complete_prefix_list(body,[],'example with longer words'))
    def test_completed_prefix_resolves_prior_failed_query_without_browser_retry(self):
        org=m.checker.Organization('Example Relief','123456789')
        s=self.session(EMPTY_FORM,[]);base=s.search
        def search(query):
            if query==QUERIES[0]:raise TimeoutError('initial request did not complete')
            return base(query)
        s.search=search;s.close=Mock()
        with patch.object(m,'MaineRegistrySession',return_value=s),patch.object(m,'me_fast_direct_query_variants',return_value=QUERIES),\
             patch.object(m,'me_browser_search_rows') as browser:
            result=m.me_fast_direct_confirmation_result(org,page=Mock())
        self.assertEqual(m.public_status(result),'Not Registered')
        self.assertEqual(s.calls,['example',QUERIES[-1]]);browser.assert_not_called()
    def test_timeout_is_not_coverage_or_a_negative_result(self):
        s=self.session();s.search=Mock(side_effect=TimeoutError('source response incomplete'))
        with self.assertRaises(TimeoutError):m.me_search_with_prefix_coverage(s,QUERIES[1],QUERIES)
        self.assertEqual(s._cc_complete_prefix_lists,{})
    def test_no_rows_are_reused_across_organization_sessions(self):
        a,b=self.session(),self.session()
        m.me_search_with_prefix_coverage(a,QUERIES[1],QUERIES)
        m.me_search_with_prefix_coverage(b,QUERIES[1],QUERIES)
        self.assertEqual(a.calls,b.calls);self.assertEqual(len(a.calls),1)
        self.assertIsNot(a._cc_complete_prefix_lists,b._cc_complete_prefix_lists)
    def test_returned_rows_cannot_mutate_completed_source_evidence(self):
        s=self.session();rows,_=m.me_search_with_prefix_coverage(s,QUERIES[1],QUERIES)
        rows[0]['name']='Changed';rows.clear()
        self.assertEqual(m.me_search_with_prefix_coverage(s,QUERIES[2],QUERIES)[0],ROWS)
    def test_exact_active_first_result_adds_no_prefix_request(self):
        org=m.checker.Organization('Example Relief','123456789')
        row={'name':org.organization_name,'number':'CO1','status':'ACTIVE',
             'location':'Chicago, IL','profession':'CHARITABLE ORGANIZATION','href':'ShowDetail.aspx?id=1'}
        s=self.session(rows=[row]);s.close=Mock()
        s.open=lambda *a,**kw:io.BytesIO(b'Status: ACTIVE Expiration Date: 12/31/2027')
        with patch.object(m,'MaineRegistrySession',return_value=s),patch.object(m,'me_fast_direct_query_variants',return_value=QUERIES),\
             patch.object(m,'reconciled_registry_address',return_value={'decision':'supported'}):
            result=m.me_fast_direct_confirmation_result(org)
        self.assertEqual(result.matched_registry_name,org.organization_name)
        self.assertIn('12/31/2027',result.raw_status_text)
        self.assertEqual(s.calls,[QUERIES[0]])
    def test_complete_broad_list_does_not_accept_unrelated_organization(self):
        org=m.checker.Organization('Example Relief','123456789')
        s=self.session(rows=[{'name':'Unrelated Foundation','number':'CO9','status':'ACTIVE'}])
        s.completed_search_html=BODY.replace('2 records','1 record');s.close=Mock()
        with patch.object(m,'MaineRegistrySession',return_value=s),patch.object(m,'me_fast_direct_query_variants',return_value=QUERIES):
            result=m.me_fast_direct_confirmation_result(org)
        self.assertEqual(m.public_status(result),'Not Registered')
        self.assertEqual(s.calls,[QUERIES[0],'example',QUERIES[-1]])
    def test_short_different_and_wildcard_prefixes_remain_original(self):
        for q,plan in [('The One',['The One','The Two']),('AB Fund',['AB Fund','AB-Fund']),
                       ('Example% One',['Example% One','Example% Two']),
                       ('Different Charity',['Different Charity','Unrelated Alias'])]:
            self.assertEqual(m.me_covering_literal_prefix(q,plan),q)
    def test_standard_flag_off_or_other_hosts_use_original_query(self):
        for mode,version,host,flag in [('standard','v-performance-lab',ENV['PUBLIC_BASE_URL'],'1'),
             ('sales','v',ENV['PUBLIC_BASE_URL'],'1'),('sales','v-performance-lab','https://staging.compliance-express.com','1'),
             ('sales','v-performance-lab',ENV['PUBLIC_BASE_URL'],'0')]:
            with patch.object(m,'APP_VERSION',version),patch.dict(os.environ,{'PUBLIC_BASE_URL':host,'CE_LAB_ME_PREFIX_COVERAGE':flag}):
                token=m.LAB_LOOKUP_MODE_CONTEXT.set(mode)
                try:
                    s=self.session();m.me_search_with_prefix_coverage(s,QUERIES[1],QUERIES)
                    self.assertEqual(s.calls,[QUERIES[1]])
                finally:m.LAB_LOOKUP_MODE_CONTEXT.reset(token)
    def test_entire_matching_status_query_plan_deadlines_and_other_states_unchanged(self):
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','7e25b24:registry_snapshot_server.py'],cwd=root).decode())
        new=ast.parse((root/'registry_snapshot_server.py').read_text());strip_me_prefix_coverage(new)
        self.assertEqual(ast.dump(old),ast.dump(new))
        for p in ['deployment/durable_queue.py','deployment/queue_schema.sql','deployment/queue_worker.py',
                  'deployment/lab_capacity.py','CharityClarity_WA_NM_checker.py']:
            if p=='deployment/queue_worker.py':
                from testing.capacity_lab.me_trace_scope import strip_me_transport_trace
                old_worker=ast.parse(subprocess.check_output(['git','show','7e25b24:'+p],cwd=root).decode())
                new_worker=ast.parse((root/p).read_text());strip_me_transport_trace(new_worker)
                self.assertEqual(ast.dump(old_worker),ast.dump(new_worker))
            elif p=='deployment/durable_queue.py':
                from testing.capacity_lab.me_application_scope import assert_queue_recovery_only
                assert_queue_recovery_only(root,'7e25b24')
            elif p=='deployment/queue_schema.sql':
                from testing.capacity_lab.loaded_timing_scope import assert_loaded_scope
                assert_loaded_scope(root,'7e25b24',p)
            else:subprocess.run(['git','diff','--exit-code','7e25b24','--',p],cwd=root,check=True)

if __name__=='__main__':unittest.main(verbosity=2)
