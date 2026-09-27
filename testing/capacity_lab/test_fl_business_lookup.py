"""Official alternative source, same shared FL rules, no negative inference."""
import ast,copy,os,subprocess,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
from urllib.parse import parse_qs
import registry_snapshot_server as m

URL='https://csapp.fdacs.gov/CSPublicApp/BusinessSearch/BusinessSearch.aspx'

def card(name='Example Relief',identifier='CH12345',status='Registered',issue='01/01/20',expiry='12/31/27',index=0):
    return f'''<div id="cpMainContent_MasterGv_maindiv_{index}"><table id="cpMainContent_MasterGv_dataTab_{index}"><tr><td><strong>{name}</strong></td></tr><tr><td>100 MAIN ST, CHICAGO, IL 60601 Phone: 123</td></tr></table><table><tr><td>License Type</td><td>License#</td><td>Issued</td><td>Expires</td><td>Status</td></tr><tr><td>Charitable Organization</td><td>{identifier}</td><td>{issue}</td><td>{expiry}</td><td>{status}</td></tr></table></div><div id="cpMainContent_MasterGv_dvContractMovers_{index}"></div>'''

def source(body=None,count=1):
    return f'<html><body>Records Found : {count}'+(card() if body is None else body)+'</body></html>'

class BusinessLookup(unittest.TestCase):
    def setUp(self):
        self.org=SimpleNamespace(organization_name='Example Relief',ein='123456789')
        self.page=MagicMock();self.page.goto.side_effect=RuntimeError('original browser path')
        self.transport=SimpleNamespace(deadline=None,error=None,enabled=False)
        for name,value in [('fl_business_lookup_enabled',True),('CAPTURE_EVIDENCE_SCREENSHOTS',False),('CAPTURE_LIGHTWEIGHT_SOURCE_SNAPSHOT',False)]:
            p=patch.object(m,name,return_value=value) if name=='fl_business_lookup_enabled' else patch.object(m,name,value)
            p.start();self.addCleanup(p.stop)

    def run_source(self,html,**extra):
        rows=m.fl_business_candidate_rows(html)
        with patch.object(m,'fl_business_public_rows',return_value=rows),patch.object(m,'reviewed_queries_first',return_value=['Example Relief']),patch.object(m.time,'sleep'):
            return m.search_fl_with_transport(self.page,self.org,self.transport)

    def test_complete_public_record_uses_same_status_and_name_anchor(self):
        r=self.run_source(source())
        self.assertTrue(r.success);self.assertEqual(r.status,'Current');self.assertEqual(r.matched_registry_identifier,'CH12345')
        self.assertEqual(r.matched_registry_name,'Example Relief');self.assertNotEqual(getattr(r,'identity_anchor',''),'EIN')
        self.assertEqual(r.source_url,URL);self.assertIn('FDACS Business Lookup',r.source_note)
        self.assertEqual(r._cc_registration_date_evidence['initial'],'01/01/20');self.page.goto.assert_not_called()

    def test_first_public_query_preserves_entered_plural_when_no_distinct_alias(self):
        # Discovery removes an alias identical to the entered name. A generated
        # singular spelling must not displace that complete identity on the one
        # alternate-source attempt; the legacy variant plan remains unchanged.
        self.org.organization_name='Hope for Communities, Inc.'
        rows=m.fl_business_candidate_rows(source(card(name=self.org.organization_name)))
        with patch.object(m,'known_names_for_ein',return_value=[]), \
                patch.object(m,'reviewed_queries_first',return_value=['Hope for Community']), \
                patch.object(m,'fl_business_public_rows',return_value=rows) as read:
            result=m.search_fl_with_transport(self.page,self.org,self.transport)
        self.assertEqual(read.call_args.args[0],self.org.organization_name)
        self.assertTrue(result.success)
        self.assertEqual(result.matched_registry_identifier,'CH12345')
        self.page.goto.assert_not_called()

    def test_adverse_status_overrides_future_expiration(self):
        for status in ['Suspended','Revoked']:
            with self.subTest(status=status):self.assertEqual(self.run_source(source(card(status=status))).status,status)

    def test_expired_and_small_charity_use_existing_deadline_rule(self):
        self.assertEqual(self.run_source(source(card(expiry='01/01/20'))).status,'Delinquent')
        self.assertEqual(self.run_source(source(card(status='Active Small Charity'))).status,'Current')

    def test_partial_and_ambiguous_document_evidence_is_never_accepted(self):
        for html in [source()[:-7],source(count=2),source()+source(),source(card(identifier='SS12345')),
                     source(card(issue='12/31/40')),source(card(expiry='unknown')),source(card()).replace('CH12345','CH12345 CH99999'),
                     source(card()).replace('Records Found : 1','Records Found : 1 Records Found : 1')]:
            with self.subTest(html=html[:80]):self.assertEqual(m.fl_business_candidate_rows(html),[])

    def test_no_records_and_incomplete_source_keep_original_path(self):
        for html in [source('',0),'<html>Verification required</html>','',source(count=2)]:
            with self.subTest(html=html):
                r=self.run_source(html);self.assertFalse(r.success);self.assertNotEqual(r.status,'Not Registered')
                self.assertTrue(self.page.goto.called)

    def test_unknown_or_closed_status_stays_on_original_path(self):
        for status in ['Closed - Out of Business','Pending','Unknown']:
            r=self.run_source(source(card(status=status)));self.assertFalse(r.success)

    def test_unrelated_closed_row_does_not_displace_exact_match(self):
        r=self.run_source(source(card(name='Other Relief',status='Closed - Out of Business')+card(index=1),2))
        self.assertTrue(r.success);self.assertEqual(r.matched_registry_identifier,'CH12345')

    def test_duplicate_exact_credentials_require_existing_browser_disambiguation(self):
        r=self.run_source(source(card()+card(identifier='CH99999',index=1),2));self.assertFalse(r.success)

    def test_chapter_or_unverified_name_never_matches(self):
        for name in ['Example Relief Wisconsin Chapter','Another Relief','Friends of Example Relief']:
            self.assertFalse(self.run_source(source(card(name=name))).success)

    def test_cross_state_address_conflict_remains_rejected(self):
        with patch.object(m,'fl_reviewed_alias_address',return_value={'decision':'conflict','registry_location':'CHICAGO, IL'}):
            r=self.run_source(source());self.assertFalse(r.success);self.assertEqual(r.reason_code,'FL_ALIAS_IDENTITY_UNCONFIRMED')

    def test_cross_state_address_corroboration_is_preserved(self):
        with patch.object(m,'fl_reviewed_alias_address',return_value={'decision':'corroborated','registry_location':'CHICAGO, IL'}):
            r=self.run_source(source());self.assertTrue(r.success);self.assertEqual(r.identity_anchor,'cross_state_name_address')

    def test_evidence_screenshot_keeps_real_browser_source(self):
        self.org.evidence_mode=True
        with patch.object(m,'fl_business_public_rows') as read,patch.object(m,'reviewed_queries_first',return_value=['Example Relief']),patch.object(m.time,'sleep'):
            m.search_fl_with_transport(self.page,self.org,self.transport);read.assert_not_called()

    def test_discovered_alias_uses_actual_city_state_and_shared_office_check(self):
        token=m.REVIEWED_NAME_CONTEXT.set({'123456789':('Community Care',)})
        try:
            with patch.object(m,'reconciled_registry_address',return_value={'decision':'corroborated'}) as address:
                r=self.run_source(source(card(name='Community Care')))
            self.assertTrue(r.success);self.assertEqual(r.identity_anchor,'cross_state_name_address')
            self.assertEqual(address.call_args.args[2],'CHICAGO, IL')
        finally:m.REVIEWED_NAME_CONTEXT.reset(token)

    def test_already_bound_issue_date_avoids_duplicate_lookup(self):
        r=self.run_source(source())
        with patch.object(m.curl_requests,'Session') as session:
            m.enrich_registration_date_sources(r);session.assert_not_called()

    def test_exact_refactor_preserves_entire_remaining_master(self):
        from testing.capacity_lab.parsing_scope import strip_fl_business_lookup
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','3ad7d63:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'));strip_fl_business_lookup(new)
        self.assertEqual(ast.dump(old),ast.dump(new))

class Transport(unittest.TestCase):
    def response(self,text):
        r=MagicMock();r.status=200;r.geturl.return_value=URL;r.headers={};r.__enter__.return_value=r
        r.read1.side_effect=[text.encode(),b''];return r

    def test_fresh_unfiltered_verified_search_is_bounded(self):
        op=MagicMock();op.open.side_effect=[self.response('<html><input type="hidden" name="__VIEWSTATE" value="fixture"></html>'),self.response(source())]
        with patch.object(m.urllib.request,'build_opener',return_value=op),patch.object(m,'fl_verified_ssl_context',return_value='verified context') as tls:
            rows=m.fl_business_public_rows('Example Relief',time.monotonic()+20)
        self.assertEqual(len(rows),1);tls.assert_called_once();self.assertEqual(op.open.call_count,2)
        for c in op.open.call_args_list:self.assertGreater(c.kwargs['timeout'],0);self.assertLessEqual(c.kwargs['timeout'],4)
        fields=parse_qs(op.open.call_args_list[1].args[0].data.decode(),keep_blank_values=True)
        self.assertEqual(fields['ctl00$cpMainContent$LicenseTypeDl'],['CH']);self.assertNotIn('ctl00$cpMainContent$chkActive',fields)
        self.assertEqual(fields['ctl00$cpMainContent$BusinessNameTb'],['Example Relief']);self.assertEqual(fields['ctl00$cpMainContent$txtCity'],[''])

    def test_timeout_untrusted_tls_redirect_partial_size_fall_back(self):
        for failure in ['timeout','tls','redirect','partial','form']:
            with self.subTest(failure=failure):
                op=MagicMock();r=self.response('<html><input type="hidden" name="__VIEWSTATE" value="fixture"></html>')
                if failure=='redirect':r.geturl.return_value='https://example.com/'
                if failure=='partial':r.headers={'Content-Length':'999999'}
                if failure=='form':r=self.response('<html>No form</html>')
                if failure in ['timeout','tls']:op.open.side_effect=TimeoutError() if failure=='timeout' else m.ssl.SSLCertVerificationError()
                else:op.open.return_value=r
                with patch.object(m.urllib.request,'build_opener',return_value=op),patch.object(m,'fl_verified_ssl_context',return_value='verified'):
                    self.assertEqual(m.fl_business_public_rows('Example Relief',time.monotonic()+8),[])
                self.assertEqual(op.open.call_count,1)

    def test_exhausted_deadline_sends_nothing(self):
        with patch.object(m.urllib.request,'build_opener') as build,patch.object(m,'fl_verified_ssl_context'):
            self.assertEqual(m.fl_business_public_rows('Example Relief',time.monotonic()-1),[])
            build.return_value.open.assert_not_called()

    def test_exact_lab_opt_in_only(self):
        for version,origin,on,want in [('x-performance-lab','https://instant-compliance-snapshot-api-hn4v.onrender.com','1',True),
              ('x','https://instant-compliance-snapshot-api-hn4v.onrender.com','1',False),
              ('x-performance-lab','https://staging.compliance-express.com','1',False),
              ('x-performance-lab','https://instant-compliance-snapshot-api-hn4v.onrender.com','0',False)]:
            for transport in ['', 'verified-first']:
                with self.subTest(version=version,origin=origin,on=on,transport=transport),patch.object(m,'APP_VERSION',version),patch.dict(os.environ,{'PUBLIC_BASE_URL':origin,'CE_LAB_FL_TRANSPORT':transport,'CE_LAB_FL_BUSINESS_LOOKUP':on}):
                    self.assertIs(m.fl_business_lookup_enabled(),want)
                    if not transport:self.assertFalse(m.fl_verified_transport_first())

if __name__=='__main__':unittest.main()
