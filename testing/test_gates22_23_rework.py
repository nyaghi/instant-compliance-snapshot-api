"""Real saved markup through capture/normalization/archive and signed searches.

All browser requests are fulfilled from local fixtures; no live source calls.
"""
import copy, html, io, json, os, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs
from pypdf import PdfReader
import registry_snapshot_server as m
from deployment import ma_withheld_evidence as ma, mn_empty_response as mn, state_snapshots as ss
from testing import run_ny_connector_guardrails as ny_harness

FIXTURES = Path(__file__).parent/'fixtures/gates22-23/rework'


class ObservedPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = m.checker.sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context()
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.markup = ''
        self.page.route('**/*', lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=self.markup)
                        if r.request.resource_type == 'document' else r.abort())

    def load_mn(self, markup=None, url='https://www.ag.state.mn.us/Charity/Search/Results.asp'):
        # HTTP supplies no charset; the document declares UTF-8 but includes
        # a raw 0xA0 separator. Reproduce the browser's replacement glyph.
        self.markup = markup if markup is not None else (FIXTURES/'mn-empty-observed.html').read_bytes().decode('utf-8', errors='replace')
        self.page.goto(url, wait_until='domcontentloaded')

    def test_mn_observed_empty_requires_exact_query_and_completed_structure(self):
        self.load_mn()
        self.assertTrue(mn.complete(self.page, 'The Johns Hopkins Hospital'))
        self.assertFalse(mn.complete(self.page, 'Another Hospital'))
        original = self.markup
        for change in [original.replace('Conduct New Search','Loading'),
                       original.replace('</h4>','</h4><p>Service unavailable</p>'),
                       original.replace('</h4>','</h4><table><tr><td>Other charity</td></tr></table>'),
                       original.replace('</h4>','</h4><p role="alert"></p>'),
                       original.replace('id="content"','id="incomplete"'), '<body></body>']:
            with self.subTest(markup=change[-80:]):
                self.load_mn(change);self.assertFalse(mn.complete(self.page,'The Johns Hopkins Hospital'))
        self.load_mn(original,url='https://www.ag.state.mn.us/Charity/Search/')
        self.assertFalse(mn.complete(self.page,'The Johns Hopkins Hospital'))

    def test_mn_source_response_runs_through_real_name_lookup(self):
        fixture = (FIXTURES/'mn-empty-observed.html').read_bytes().decode('utf-8', errors='replace')
        name='The Johns Hopkins Hospital';self.markup=fixture
        # Serve the actual form/result transaction locally. The lookup's parser,
        # input selection, click and completion guards are not replaced.
        form='<form action="Results.asp" method="post"><input id="txtEIN" name="txtEIN"><input id="txtOrg" name="txtOrg"><input type="submit" name="cmdSearch" value="Search"></form>'
        def route(r):
            if r.request.resource_type != 'document': return r.abort()
            fields=parse_qs(r.request.post_data or '')
            query=(fields.get('txtOrg') or fields.get('txtEIN') or [name])[0]
            body=fixture.replace(name,html.escape(query)) if r.request.method=='POST' else form
            return r.fulfill(status=200,content_type='text/html; charset=utf-8',body=body)
        self.page.unroute('**/*');self.page.route('**/*',route)
        from deployment.search_observation import observe_browser_context
        run=ss.CaptureRun(name,'520591656','MN');observe_browser_context(self.context,run)
        token=ss.CURRENT.set(run);self.addCleanup(ss.CURRENT.reset,token)
        with patch.object(m,'build_search_queries',return_value=[name]), patch.object(m.time,'sleep'), patch.object(m.checker,'safe_wait_for_network_idle'):
            result=m.search_mn(self.page,m.checker.Organization(name,'520591656'))
        self.assertTrue(result.success);self.assertEqual(m.public_status(result),'Not Registered')
        self.assertEqual(result.queries_attempted,[name]);self.assertFalse(result.matched_registry_identifier)
        row={**m.checker.asdict(result),'status':m.public_status(result),'comments':result.source_note}
        private=run.finish(row)
        with tempfile.TemporaryDirectory() as folder:
            store=ss.SQLiteStore(Path(folder)/'mn.sqlite')
            public=ss.persist_worker_result(None,private,{'state':'MN','payload':{'ein':run.ein}},store=store)
            self.assertTrue(public.get('search_history_url'),public)

    def ma_page(self):
        observed=json.loads((FIXTURES/'ma-withheld-observed.json').read_text(encoding='utf-8'))
        parts=['<html><body><h1>OFFLINE SOURCE STRUCTURE REPLAY</h1>']
        for select in observed['selects']:
            if not select['visible']:continue
            # outerHTML does not reflect a live selectedIndex on the mode field.
            markup=select['html']
            if select['value']=='ein':markup=markup.replace('value="ein"','value="ein" selected')
            parts.append(markup)
        parts.append('<input value="520591656" disabled>')
        parts.append('<p>'+ma.MESSAGE+'</p></body></html>')
        self.markup=''.join(parts);self.page.goto(ma.URL)
        return {'value':observed['selects'][1]['value'],'label':observed['selects'][1]['text']}

    def test_ma_capture_normalization_archive_and_pdf_are_one_path(self):
        candidate=self.ma_page();org=m.checker.Organization('The Johns Hopkins Hospital','52-0591656')
        run=ss.CaptureRun(org.organization_name,org.ein,'MA')
        self.markup=self.markup.replace(' disabled','').replace('<p>'+ma.MESSAGE+'</p>',
            '<div id="notice" hidden>'+ma.MESSAGE+'</div>')
        self.markup=self.markup.replace('</body>',
            '<button onclick="document.getElementById(\'selection\').hidden=false">Search</button>'
            '<p id="selection" hidden>Select a Charity</p>'
            '<button onclick="document.getElementById(\'notice\').hidden=false">Get Filings</button></body>')
        token=ss.CURRENT.set(run);self.addCleanup(ss.CURRENT.reset,token)
        result,body=m.search_ma_master(self.page,org,{})
        self.assertTrue(ma.preserves_identity(result))
        with patch.object(m,'apply_confirmed_feedback_correction',return_value=''):
            row=m.response_data_for_lookup(result,body,org,org.organization_name,org.ein,'MA',time.perf_counter())
        self.assertEqual(row['status'],'Unable to Confirm');self.assertEqual(row['matched_registry_identifier'],candidate['value'])
        private=run.finish(row);self.assertEqual(len(private.get('_worker_source_archives',[])),1)
        with tempfile.TemporaryDirectory() as folder:
            store=ss.SQLiteStore(Path(folder)/'ma.sqlite')
            public=ss.persist_worker_result(None,private,{'state':'MA','payload':{'ein':org.ein}},store=store)
            self.assertTrue(public.get('evidence_url'))
            meta,pdf=ss.saved_pdf(public['evidence_url'].split('/')[-1][:-4],store)
            self.assertEqual(len(PdfReader(io.BytesIO(pdf)).pages),1)
            self.assertEqual(meta['record_name'],candidate['label'])

    def test_ma_changed_identity_notice_and_status_do_not_preserve_binding(self):
        candidate=self.ma_page();run=ss.CaptureRun('The Johns Hopkins Hospital','520591656','MA')
        self.assertFalse(ma.capture(self.page,run,{**candidate,'value':'a094U00001vhxguQAA'},run.ein))
        self.assertFalse(ma.capture(self.page,run,candidate,'123456789'))
        self.page.get_by_role('combobox').first.select_option('charityNumber')
        self.assertFalse(ma.capture(self.page,run,candidate,run.ein))
        org=m.checker.Organization(run.name,run.ein)
        for change in [{}, {'_ma_withheld_identity':('123456789',candidate['value'],candidate['label'],ma.URL)}]:
            result=m.checker.StateResult(run.name,run.ein,'MA','Unable to Confirm',ma.URL)
            result.status_reason=ma.REASON;result.success=True
            result.matched_registry_name=candidate['label'];result.matched_registry_identifier=candidate['value']
            for k,v in change.items():setattr(result,k,v)
            m.normalize_registry_match_fields(result,org)
            self.assertFalse(result.matched_registry_identifier)


class PackagedContract(unittest.TestCase):
    def setUp(self):
        self.h=ny_harness.ConnectorTests('runTest');self.h.setUp();self.addCleanup(self.h.doCleanups)

    def test_actual_candidate_manifest_supported_by_three_signed_start_handlers(self):
        directory=Path(os.environ['CC_CANDIDATE_CONNECTOR'])
        version=json.loads((directory/'manifest.json').read_text(encoding='utf-8-sig'))['version']
        with patch.object(m,'trial_identity',return_value={'origin':m.NY_CONNECTOR_ORIGIN}):
            for state in ['NY','IL','GA']:
                code,reply=self.h.request(action='start',state=state,organization_name='Example Foundation',ein='123456789',connector_version=version)
                self.assertEqual(code,200,(state,version,reply));self.assertEqual(reply['phase'],'search')
            for state in ['NY','IL','GA']:
                code,_=self.h.request(action='start',state=state,organization_name='Example Foundation',ein='123456789',connector_version='0.6.136')
                self.assertEqual(code,400)

    def test_actual_hopkins_queries_complete_without_redundant_parenthetical_article(self):
        names=['The Johns Hopkins Hospital','Johns Hopkins Hospital (The)','The John Hopkins Hospital','The Johns Hopkin Hospital']
        with patch.object(m,'build_search_queries',return_value=names), patch.object(m,'trial_identity',return_value={'origin':m.NY_CONNECTOR_ORIGIN}):
            code,reply=self.h.request(action='start',organization_name=names[0],ein='520591656',connector_version='0.6.135')
            self.assertEqual(code,200);seen=[]
            for _ in range(4):
                seen.append(reply['query']);code,reply=self.h.submit(reply,[]);self.assertEqual(code,200)
            self.assertEqual(reply['phase'],'complete');self.assertEqual(reply['result']['status'],'Not Registered')
        self.assertEqual(seen,[{'ein':'520591656'}, *[{'orgName':x} for x in [names[0],names[2],names[3]]]])
        self.h.session.get.assert_not_called()

    def test_ny_only_article_is_moved_other_identity_words_are_kept(self):
        for before,after in [('Example Hospital (The)','The Example Hospital'),('Example Center (An)','An Example Center'),
                             ('Example Fund (A)','A Example Fund'),('Example Hospital (Children)','Example Hospital (Children)'),
                             ('Example Hospital Foundation','Example Hospital Foundation'),("Children's Hospital","Childrens Hospital")]:
            self.assertEqual(m.ny_name_search_term(before).casefold(),after.casefold())


if __name__=='__main__':unittest.main(verbosity=2)
