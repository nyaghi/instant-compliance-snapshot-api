"""Unique public EIN records only; all other evidence preserves browser fallback."""
import ast,copy,json,os,subprocess,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
import registry_snapshot_server as m

BASE='https://charportal.dca.njoag.gov'
VIEW='Portal - Charity - Public Search Subgrid'
GRID='/_services/entity-grid-data.json/11111111-1111-1111-1111-111111111111'
ROW={'name':'Example Relief','accountnumber':'CH12345','crsm_filestanding':'Compliant','crsm_federalein':'123456789'}
CFG={'filterenabled':False,'getDataUrl':GRID,'defaultViewId':'view-id','layouts':[{
    'ViewName':VIEW,'Base64SecureConfiguration':'public-test-configuration',
    'Configuration':{'ViewId':'view-id','EntityName':'account','Search':{'Enabled':True}},
    'Columns':[{'LogicalName':k} for k in ROW]}]}
DATA={'ItemCount':1,'MoreRecords':False,'PageNumber':1,'Records':[{'Attributes':[
    {'Name':k,'DisplayValue':v} for k,v in ROW.items()]}]}
SEL={'charityName':'Example Relief','numberOfResults':'3','accountId':'22222222-2222-2222-2222-222222222222',
     'charityRegistrationId':'33333333-3333-3333-3333-333333333333'}
DETAIL='''<html><body><input id="crsm_federalein" value="123456789">
<input id="accountnumber" value="CH12345"><input id="crsm_fiscalyearenddate" value="2025-12-31T00:00:00">
</body></html>'''

class PublicQuery(unittest.TestCase):
    def setUp(self):
        self.org=m.checker.Organization('Example Relief','123456789');self.calls=[]
        self.responses=[];self.cfg=copy.deepcopy(CFG);self.data=copy.deepcopy(DATA);self.sel=copy.deepcopy(SEL)
        self.detail=DETAIL;self.source='<html><body>Charity Public Search</body></html>'
        self.change={};self.clock=[0.0];self.advance=0
        self.session=MagicMock();self.session.__enter__.return_value=self.session
        self.session.request.side_effect=self.request
        for obj,name,value in [(m,'CAPTURE_EVIDENCE_SCREENSHOTS',False),(m,'CAPTURE_LIGHTWEIGHT_SOURCE_SNAPSHOT',False),
                               (m,'nj_public_query_enabled',True)]:
            p=patch.object(obj,name,return_value=value) if name=='nj_public_query_enabled' else patch.object(obj,name,value)
            p.start();self.addCleanup(p.stop)
        p=patch.object(m.curl_requests,'Session',return_value=self.session);p.start();self.addCleanup(p.stop)

    def request(self,method,url,**kwargs):
        self.calls.append((method,url,kwargs));self.clock[0]+=self.advance
        self.assertTrue(kwargs['verify']);self.assertTrue(kwargs['stream']);self.assertFalse(kwargs['allow_redirects'])
        self.assertGreater(kwargs['timeout'],0);self.assertLessEqual(kwargs['timeout'],4)
        if '/GetListViewConfiguration/' in url:body=json.dumps(self.cfg);kind='json'
        elif '/_layout/tokenhtml' in url:body='<input name="__RequestVerificationToken" value="synthetic-token">';kind='html'
        elif '/entity-grid-data.json/' in url:
            body=json.dumps(self.data);kind='json'
            payload=kwargs['json'];self.assertEqual(payload['search'],self.org.ein)
            self.assertEqual(payload['page'],1);self.assertEqual(payload['pageSize'],10)
            self.assertFalse(any(payload[k] for k in ['filter','metaFilter','odataFilterQuery','nlSearchFilter']))
            self.assertEqual(kwargs['headers']['__RequestVerificationToken'],'synthetic-token')
        elif '/retrieveRegistration/' in url:body=json.dumps(self.sel);kind='json'
        elif '/CHR-Public-Details-Page/' in url:body=self.detail;kind='html'
        else:body=self.source;kind='html'
        r=MagicMock(status_code=200,url=url,headers={'Content-Type':'application/'+kind})
        r.iter_content.return_value=iter([body.encode()])
        for k,v in self.change.items():setattr(r,k,v)
        self.responses.append(r);return r

    def test_complete_unique_ein_and_credential_use_original_filing_rule(self):
        result,body=m.search_nj_public_details(self.org)
        self.assertTrue(result.success);self.assertEqual(result.status,'Current')
        self.assertEqual(result.last_year_on_record,2025);self.assertEqual(result.computed_due_date,'6/30/2027')
        self.assertEqual(result.matched_registry_name,'Example Relief');self.assertEqual(len(self.calls),6)
        self.assertTrue(all(r.close.call_count==1 for r in self.responses))
        self.assertIn(DETAIL,body)

    def test_negative_duplicate_partial_and_wrong_ein_keep_browser(self):
        variants=[{**DATA,'Records':[],'ItemCount':0},{**DATA,'ItemCount':2,'Records':DATA['Records']*2},
                  {**DATA,'MoreRecords':True},{**DATA,'PageNumber':2},{**DATA,'ItemCount':True}]
        wrong=copy.deepcopy(DATA);wrong['Records'][0]['Attributes'][-1]['DisplayValue']='987654321';variants.append(wrong)
        duplicate=copy.deepcopy(DATA);duplicate['Records'][0]['Attributes'].append({'Name':'crsm_federalein','DisplayValue':'123456789'});variants.append(duplicate)
        for data in variants:
            with self.subTest(data=data):
                self.data=data;self.calls=[];self.assertIsNone(m.search_nj_public_details(self.org))
                self.assertFalse(any('/retrieveRegistration/' in u for _,u,_ in self.calls))

    def test_detail_identity_completeness_and_period_are_required(self):
        for detail in [DETAIL.replace('123456789','987654321'),DETAIL.replace('CH12345','CH54321'),
                       DETAIL.replace('</html>',''),DETAIL.replace('crsm_fiscalyearenddate','missing'),
                       DETAIL.replace('</body>','<input id="crsm_federalein" value="123456789"></body>')]:
            self.detail=detail;self.assertIsNone(m.search_nj_public_details(self.org))

    def test_selection_must_bind_the_unique_ein_row(self):
        for change in [{'charityName':'Other Charity'},{'numberOfResults':'0'},
                       {'numberOfResults':'unknown'},{'accountId':'../other'}]:
            self.sel={**SEL,**change};self.calls=[]
            self.assertIsNone(m.search_nj_public_details(self.org))
            self.assertFalse(any('/CHR-Public-Details-Page/' in u for _,u,_ in self.calls))

    def test_oversized_response_is_closed_and_never_classified(self):
        self.source='x'*1_000_001
        self.assertIsNone(m.search_nj_public_details(self.org));self.assertEqual(len(self.calls),1)
        self.responses[0].close.assert_called_once()

    def test_each_lookup_obtains_a_new_session_and_fresh_source(self):
        m.search_nj_public_details(self.org);m.search_nj_public_details(self.org)
        self.assertEqual(m.curl_requests.Session.call_count,2);self.assertEqual(len(self.calls),12)

    def test_filtered_changed_or_off_origin_portal_configuration_is_rejected(self):
        variants=[{**CFG,'filterenabled':True},{**CFG,'getDataUrl':'https://other.example/query'},
                  {**CFG,'layouts':CFG['layouts']*2},{**CFG,'defaultViewId':'different'}]
        for cfg in variants:
            self.cfg=cfg;self.calls=[];self.assertIsNone(m.search_nj_public_details(self.org))
            self.assertFalse(any(method=='POST' for method,_,_ in self.calls))

    def test_http_errors_redirects_and_challenges_are_not_negative_results(self):
        for status in [302,401,403,429,500]:
            self.change={'status_code':status};self.calls=[]
            self.assertIsNone(m.search_nj_public_details(self.org));self.assertEqual(len(self.calls),1)
        self.change={};self.source='<html><body>Verify you are human</body></html>';self.calls=[]
        self.assertIsNone(m.search_nj_public_details(self.org));self.assertEqual(len(self.calls),1)
        self.session.request.side_effect=TimeoutError('source incomplete')
        self.assertIsNone(m.search_nj_public_details(self.org))

    def test_budget_does_not_reset_between_requests(self):
        self.advance=4
        with patch.object(m.time,'monotonic',side_effect=lambda:self.clock[0]):
            self.assertIsNone(m.search_nj_public_details(self.org))
        self.assertLessEqual(len(self.calls),3);self.assertEqual(self.clock[0],12)

    def test_capture_and_disabled_mode_perform_no_new_requests(self):
        with patch.object(m,'nj_public_query_enabled',return_value=False):self.assertIsNone(m.search_nj_public_details(self.org))
        self.org.evidence_mode=True;self.assertIsNone(m.search_nj_public_details(self.org))
        self.assertFalse(self.calls)

    def test_normal_source_failure_retains_existing_browser_route(self):
        with patch.object(m,'search_nj_public_details',return_value=None),patch.object(m.checker,'sync_playwright',side_effect=RuntimeError('existing browser route')):
            with self.assertRaisesRegex(RuntimeError,'existing browser route'):
                m.run_state_lookup(self.org.organization_name,self.org.ein,'NJ')

    def test_only_source_acquisition_changes_and_classification_moves_verbatim(self):
        from testing.capacity_lab.parsing_scope import strip_nj_public_query
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','b328ca9:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'));strip_nj_public_query(new)
        self.assertEqual(ast.dump(old),ast.dump(new))

class LabOptIn(unittest.TestCase):
    def test_public_query_requires_exact_lab_and_explicit_opt_in(self):
        for version,origin,enabled,expected in [
            ('test-performance-lab','https://instant-compliance-snapshot-api-hn4v.onrender.com','1',True),
            ('test','https://instant-compliance-snapshot-api-hn4v.onrender.com','1',False),
            ('test-performance-lab','https://staging.compliance-express.com','1',False),
            ('test-performance-lab','https://instant-compliance-snapshot-api-hn4v.onrender.com','0',False)]:
            with patch.object(m,'APP_VERSION',version),patch.dict(os.environ,{'PUBLIC_BASE_URL':origin,'CE_LAB_NJ_PUBLIC_QUERY':enabled}):
                self.assertIs(m.nj_public_query_enabled(),expected)

if __name__=='__main__':unittest.main()
