"""State-specific regressions; mocked source transport, actual PDF processing."""
import base64,copy,io,time,unittest
from types import SimpleNamespace
from unittest.mock import patch,Mock
import fitz
from PIL import Image
from pypdf import PdfReader
import registry_snapshot_server as c
from deployment import nm_registration_document as nm,ok_certificate_evidence as ok

def pdf(text,pages=1):
    d=fitz.open()
    for i in range(pages):d.new_page().insert_text((30,40),text)
    return d.tobytes()

class NMOriginalFiling(unittest.TestCase):
    def setUp(self):
        self.number='20242222530857770'; self.ein='131610451'; self.query={'state':'NM','operation':'detail','identifier':self.ein}
        self.record={'state':'NM','ein':self.ein,'organization_name':'United Service Organizations Inc.','issued':time.time()}
        self.evidence={'name':'The Franklin Institute','ein':self.ein,'history_rows':[['2024','Registration Submitted '+self.number,'11/4/2025']]}
        self.asset={'identifier':self.ein,'kind':'source_pdf','content':base64.b64encode(pdf('Original detail')).decode()}
        self.document={'query':self.query,'registration_number':self.number,'tax_year':2024,'submitted_on':'11/4/2025',
            'source_url':'https://secure.nmdoj.gov/coros/getregdoc.aspx?RegNumber='+self.number,'captured_at':time.time()}
        self.text='United Service Organizations, Incorporated\n13-1610451\nRegistration Submitted ('+self.number+')\nTax Year 2024'
    def run_document(self,text=None,**changes):
        doc={**self.document,'content':base64.b64encode(pdf(self.text if text is None else text,2)).decode(),**changes}
        return nm.append_to_asset(self.asset,doc,self.record,self.query,self.evidence)
    def test_requested_name_and_ein_accept_original_despite_heading_error(self):
        r=self.run_document();self.assertEqual(len(PdfReader(io.BytesIO(base64.b64decode(r['content']))).pages),3)
        self.assertIn('heading differs',r['capture_note'])
    def test_conflicting_identity_or_wrong_document_never_attached(self):
        for text in [self.text.replace('13-1610451','12-3456789'),self.text.replace('United Service Organizations, Incorporated','Another Charity'),
                     self.text.replace(self.number,'20242222530857771'),self.text.replace('2024','2023')]:
            with self.subTest(text=text):self.assertIs(self.run_document(text),self.asset)
        for change in [{'query':{**self.query,'identifier':'123456789'}},{'tax_year':2023},{'captured_at':0},
                       {'source_url':'https://other.example/file.pdf'}]:self.assertIs(self.run_document(**change),self.asset)
    def test_original_heading_match_keeps_existing_behavior(self):
        self.evidence['name']='United Service Organizations, Incorporated'
        self.assertNotIn('heading differs',self.run_document()['capture_note'])

class SCChangedHeading(unittest.TestCase):
    def test_twenty_first_page_is_processed_without_extending_deadline(self):
        def page(n):
            pager=(f"<a href=\"javascript:__doPostBack('ctl00$MainContent$GridView_SearchResult','Page${n+1}')\">Next</a>" if n<21 else '')
            return (f'<input id="MainContent_txt_CharitySearchName" value="Veterans">'
                f'<a href="javascript:CharityInfo({n})">Veterans Organization {n}</a>'
                f'<tr align="center"><td colspan="2"><table><span>{n}</span>{pager}</table></td></tr>')
        calls=[]
        def post(fields):
            n=int(fields['__EVENTARGUMENT'].split('$')[1]);calls.append(n);return page(n)
        with patch.object(c,'sc_extract_hidden_fields',side_effect=lambda html:{}):
            rows=list(c.sc_result_page_stream(page(1),post,time.monotonic()+10,'Veterans'))
            self.assertEqual(len(rows),21);self.assertEqual(calls,list(range(2,22)))
            with self.assertRaises(TimeoutError):list(c.sc_result_page_stream(page(1),post,time.monotonic()-1,'Veterans'))
            with self.assertRaises(ValueError):list(c.sc_result_page_stream(page(1),lambda fields:page(1),time.monotonic()+10,'Veterans'))

    def lookup(self,ein, incomplete=False):
        name='Stonestreet-Rone Post No 1983 Veterans of Foreign Wars of the United States'
        class Response:
            def __init__(self,text):self.text=text
            def raise_for_status(self):pass
        class Session:
            headers={}
            def get(self,*a,**kw):return Response('Search')
            def post(self,url,data,**kw):
                if data.get('ctl00$MainContent$Hidden_CharityID'):
                    return Response('<span id="MainContent_lbl_CharityName">Veterans of Foreign Wars of the United States</span><span id="MainContent_lblCharityID">P44840</span>Status Registered Due Date 11/15/2027')
                if data.get('ctl00$MainContent$txt_CharitySearchName')==name:
                    return Response('<a href="javascript:CharityInfo(44840)">'+name+'</a>')
                if incomplete:raise TimeoutError('Incomplete source')
                return Response('No results found')
        with patch.object(c,'curl_requests',SimpleNamespace(Session=lambda **kw:Session())),patch.object(c,'build_search_queries',return_value=[name,'Stonestreet']),patch.object(c,'sc_extract_hidden_fields',side_effect=lambda html:{}),patch.object(c,'sc_detail_filing_ein',return_value=ein):
            return c.sc_official_detail_lookup(c.checker.Organization(name,'640517029'))
    def test_proven_other_ein_is_excluded(self):self.assertEqual(c.public_status(self.lookup('440474290')),'Not Registered')
    def test_unknown_ein_or_incomplete_search_cannot_be_negative(self):
        self.assertNotEqual(self.lookup('').status,'Not Registered')
        self.assertNotEqual(getattr(self.lookup('440474290',True),'status',None),'Not Registered')
    def test_exact_ein_remains_positive(self):self.assertIn(self.lookup('640517029').status,{'Current','Upcoming Filing'})

class NVExpiredReservations(unittest.TestCase):
    def lookup(self,change=None,complete=True):
        calls=[];name="Children's Hospital Corporation"
        row={'name':name,'identifier':'NR20210916-12621','entity_number':'NR20210916-12621','entity_type':'Name Reservation','raw_status':'Expired'}
        row.update(change or {})
        def source(q):
            calls.append(q)
            if q['operation']=='detail':raise RuntimeError('Detail required')
            return {'query':q,'state':'NV','complete':complete,'verification_pending':False,'rows':[row],'total':1}
        with patch.object(c,'licensed_charity_names',return_value=([name],[])),patch.object(c,'trial_identity',return_value=True):
            r=c.final_four_browser_lookup(c.checker.Organization(name,'042774441'),'NV',source)
        return r,calls
    def test_complete_expired_explicit_reservation_needs_no_detail(self):
        r,calls=self.lookup();self.assertEqual(r.status,'Not Registered')
        self.assertTrue(all(q['operation']=='search' for q in calls));self.assertIn('Expired name reservation',str(r.rejected_candidates))
    def test_missing_type_active_or_missing_entity_number_keeps_old_detail_path(self):
        for changes in [{'entity_type':''},{'raw_status':'Active'},{'entity_number':''}]:
            with self.subTest(changes=changes),self.assertRaisesRegex(RuntimeError,'Detail required'):self.lookup(changes)
    def test_incomplete_grid_cannot_be_negative(self):
        with self.assertRaises(ValueError):self.lookup(complete=False)

class OKHistoricalEvidence(unittest.TestCase):
    def setup_source(self):
        run=SimpleNamespace(state='OK',visual_adapter_facts=[])
        page=Mock(url='https://business.sos.ok.gov/corp/charityDetail.aspx?id=4312076742')
        page.get_by_text.return_value.locator.return_value.get_by_role.return_value.get_attribute.return_value='window.open("../CharityDocs/3222200001.pdf"); return false;'
        raw=pdf('United Service Organizations Inc.\nHistorical exemption notice',2)
        page.request.get.return_value=SimpleNamespace(ok=True,url='https://business.sos.ok.gov/CharityDocs/3222200001.pdf',body=lambda:raw)
        return run,page
    def test_original_full_historical_document_is_retained_and_labeled(self):
        run,page=self.setup_source();num=ok.retain_exemption_notice(page,run,['3222200001 Notice of Registration Exemption June 27, 2005 2'],'United Service Organizations Inc.')
        self.assertEqual(num,'3222200001');self.assertEqual(run.ok_original_certificates[('4312076742','United Service Organizations Inc.')]['pages'],2)
        self.assertTrue(run.ok_original_certificates[('4312076742','United Service Organizations Inc.')]['historical_exemption'])
    def test_wrong_action_different_name_wrong_page_count_fail_closed(self):
        for kind in ['action','name','pages']:
            run,page=self.setup_source()
            if kind=='action':page.get_by_text.return_value.locator.return_value.get_by_role.return_value.get_attribute.return_value='wrong'
            number=ok.retain_exemption_notice(page,run,['3222200001 Notice of Registration Exemption June 27, 2005 '+('3'if kind=='pages'else'2')], 'Other Charity'if kind=='name'else'United Service Organizations Inc.')
            self.assertEqual(number,'');self.assertFalse(hasattr(run,'ok_original_certificates'))

if __name__=='__main__':unittest.main()
