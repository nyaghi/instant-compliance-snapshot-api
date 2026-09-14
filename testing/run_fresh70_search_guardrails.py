"""Identity, discovery and first-page policy controls for the September 14 cases."""
import sys, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc


class IdentityTests(unittest.TestCase):
    def setUp(self):
        p = patch.object(cc, 'known_names_for_ein', return_value=[])
        p.start(); self.addCleanup(p.stop)

    def test_subject_overlap_does_not_merge_distinct_entities(self):
        for original, candidate in [('Autism Research Institute', 'Organization for Autism Research, Inc.'),
                                    ('Organization for Autism Research, Inc.', 'Autism Research Institute')]:
            self.assertFalse(cc.registry_name_is_safe_for_org(candidate, original, '952548452'))
            self.assertFalse(cc.ms_registry_name_is_safe(candidate, original, '952548452'))
            self.assertFalse(cc.registry_name_is_safe_against_targets(candidate, [original], original, '952548452'))

    def test_exact_ein_and_conflicting_ein(self):
        name = 'Chemical Coaters Association International Finishing Education Foundation, Inc.'
        candidate = 'Chemical Coaters Association International'
        self.assertEqual(cc.score_candidate(name, '83-2985088', {'name': candidate, 'ein': '832985088'})['decision'], 'accepted')
        self.assertEqual(cc.score_candidate(name, '83-2985088', {'name': candidate, 'ein': '237159835'})['reason'], 'REJECT_DIFFERENT_EIN')
        self.assertNotEqual(cc.score_candidate(name, '83-2985088', {'name': candidate})['decision'], 'accepted')

    def test_existing_identity_controls(self):
        for original, candidate in [('Aeon', 'Aeon (dba Aeon Homes)'),
                                    ('American Farrier’s Association Foundation Inc.', "American Farriers Association Foundation Inc."),
                                    ('Autism Research Institute', 'Autism Research Institute, Inc.')]:
            self.assertTrue(cc.registry_name_is_safe_for_org(candidate, original), (original, candidate))
        for original, candidate in [('Beth Israel Deaconess Hospital - Milton, Inc.', 'Beth Israel Deaconess Hospital - Needham, Inc.'),
                                    ('Children’s Health Care Foundation', 'Children’s Healthcare of Atlanta'),
                                    ('Children’s Health Care Foundation', 'Children’s Health Defense')]:
            self.assertFalse(cc.registry_name_is_safe_for_org(candidate, original), (original, candidate))

    def test_nd_possessive_discovery(self):
        for name in ["Children's Health Care Foundation", 'Children’s Health Care Foundation']:
            queries = cc.nd_search_queries(cc.checker.Organization(name, '411814223'))
            self.assertIn('Children Health Care Foundation', queries)
            self.assertFalse(any(' s ' in q.casefold() or q.casefold().startswith('s ') for q in queries))
            self.assertEqual(len(queries), len({q.casefold() for q in queries}))
            self.assertLessEqual(len(queries), 8)
        self.assertIn('American Farrier Association Foundation Inc', cc.nd_search_queries(cc.checker.Organization('American Farrier’s Association Foundation Inc.', '872999231')))
        self.assertEqual(cc.nd_search_queries(cc.checker.Organization('Aeon', '411558711'))[0], 'Aeon')

    def sc(self, records):
        session = Mock(); session.get.return_value.text = '<form></form>'
        picked = []
        def post(url, data, **kwargs):
            response = Mock()
            if 'ctl00$MainContent$Hidden_CharityID' in data:
                identifier = data['ctl00$MainContent$Hidden_CharityID']; picked.append(identifier)
                record = next(r for r in records if r[0] == identifier)
                response.text = f'Public Id P{identifier} Status {record[2]} Due Date 11/15/2026'
            else:
                response.text = '<table><tr><th>Name</th><th>Status</th></tr>' + ''.join(f'<tr><td><a href="javascript:CharityInfo({i})">{n}</a></td><td>{s}</td></tr>' for i,n,s in records) + '</table>'
            return response
        session.post.side_effect = post
        with patch.object(cc, 'curl_requests', Mock(Session=Mock(return_value=session))), patch.object(cc, 'build_search_queries', return_value=['Call to Action']):
            result = cc.sc_official_detail_lookup(cc.checker.Organization('Call to Action', '363003308'))
        return result, picked

    def test_sc_literal_name_precedes_relaxed_article_and_status(self):
        records = [('29528', 'A Call To Action', 'Registered'), ('24426', 'CALL TO ACTION', 'Closed'), ('34489', 'A Call to Action Oconee', 'Registered')]
        for order in [records, list(reversed(records))]:
            result, picked = self.sc(order)
            self.assertEqual(picked, ['24426']); self.assertEqual(result.matched_registry_identifier, 'P24426')

    def test_sc_equal_identity_active_wins_and_article_fallback_remains(self):
        records = [('1', 'CALL TO ACTION, INC.', 'Closed'), ('2', 'Call to Action', 'Registered')]
        for order in [records, list(reversed(records))]:
            result, picked = self.sc(order); self.assertEqual(picked, ['2'])
        result, picked = self.sc([('29528', 'A Call To Action', 'Registered')]); self.assertEqual(picked, ['29528'])


class OklahomaTests(unittest.TestCase):
    def run_queries(self, statuses):
        attempts = []
        def search(page, org, module):
            self.assertEqual(org.ok_search_page_limit, 1); attempts.append(org.organization_name)
            status = statuses[min(len(attempts)-1, len(statuses)-1)]
            return SimpleNamespace(organization_name=org.organization_name, status=status, success=status=='Not Registered', matched_registry_name='', raw_status_text='Completed first page', source_note='')
        module = SimpleNamespace(SearchResult=lambda **kw: SimpleNamespace(**kw), OK_SEARCH_URL='https://www.sos.ok.gov/charity/Default.aspx')
        with patch.object(cc, 'search_ok_precise', side_effect=search), patch.object(cc, 'public_status', lambda r: r.status):
            result = cc.search_ok_with_variants(None, cc.checker.Organization('Children’s Health Care Foundation','411814223'), module)
        return result, attempts

    def test_all_completed_first_pages_support_approved_negative(self):
        result, attempts = self.run_queries(['Not Registered']); self.assertEqual(result.status,'Not Registered')
        self.assertEqual(len(attempts), cc.OK_QUERY_LIMIT); self.assertIn('first page', result.source_attempts[-1])

    def test_unfinished_first_page_cannot_be_overwritten_by_later_negative(self):
        result, attempts = self.run_queries(['Unable to Confirm','Not Registered']); self.assertEqual(result.status,'Unable to Confirm')

    def test_outage_never_negative(self):
        result, _ = self.run_queries(['Not Registered','Site Not Reachable']); self.assertEqual(result.status,'Site Not Reachable')

    def test_extra_pages_are_not_requested_and_read_errors_propagate(self):
        org = cc.checker.Organization('Example Relief', '012345678'); page = Mock()
        with patch.object(cc,'ok_choose_safe_result_row_on_page',return_value=None):
            self.assertIsNone(cc.ok_choose_safe_result_row(page,org,None)); page.locator.assert_not_called()
        with patch.object(cc,'ok_choose_safe_result_row_on_page',side_effect=TimeoutError('unreadable first page')):
            with self.assertRaises(TimeoutError): cc.ok_choose_safe_result_row(page,org,None)


class ArkansasTests(unittest.TestCase):
    name='Chemical Coaters Association International Finishing Education Foundation, Inc.'
    candidate='Chemical Coaters Association International'
    def test_same_record_ein_wins_and_conflict_rejects(self):
        for ein,expected in [('832985088','accept'),('237159835','reject'),('','unconfirmed')]:
            self.assertEqual(cc.ar_candidate_identity({'name':self.candidate,'ein':ein},self.name,[self.name],'83-2985088'),expected)
        self.assertEqual(cc.ar_candidate_identity({'name':self.name,'ein':'237159835'},self.name,[self.name],'83-2985088'),'reject')

    def test_missing_ein_only_flags_substantial_related_name(self):
        for candidate,expected in [('Chemical','reject'),('Unrelated Education Foundation','reject'),(self.name,'accept')]:
            self.assertEqual(cc.ar_candidate_identity({'name':candidate},self.name,[self.name],'832985088'),expected)

    def test_unconfirmed_public_row_is_not_negative(self):
        with patch.object(cc,'ar_preferred_name_variants',return_value=[self.name]),patch.object(cc,'organization_name_variants',return_value=[]),patch.object(cc,'ar_wait_for_search_form',return_value=True),patch.object(cc,'registry_page_body',return_value='Back to Search Form Registration Date'),patch.object(cc,'safe_wait_for_network_idle'),patch.object(cc,'ar_result_rows',return_value=[{'name':self.candidate,'status':'Current','type':'Charity','registration_date':'2020-05-28'}]):
            result=cc.search_ar_precise(Mock(),cc.checker.Organization(self.name,'832985088'))
        self.assertEqual(result.status,'Needs Review');self.assertEqual(result.reason_code,'AR_RELATED_ENTITY_EIN_UNAVAILABLE')
        self.assertIn('no EIN',result.source_note)

if __name__ == '__main__': unittest.main(verbosity=2)
