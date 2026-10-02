"""Reported October 2 defects: retrieval remains separate from identity."""
from datetime import date
import html
import unittest
from unittest.mock import patch, Mock
from types import SimpleNamespace
import registry_snapshot_server as cc


class ReportedNames(unittest.TestCase):
    def test_ok_newest_equivalent_is_selected_by_actual_renewal_date(self):
        org = cc.checker.Organization('Inheritance of Hope', '75-3243566')
        org.ok_equivalent_records = [('INHERITANCE OF HOPE', '4313292546'), ('INHERITANCE OF HOPE, INC.', '4312524349')]
        page = Mock()
        def navigate(url, **kwargs):
            page.url = url
            return SimpleNamespace(status=200)
        page.goto.side_effect = navigate
        page.locator.return_value.count.return_value = 0
        module = cc.state_batch_modules(['OK'])[cc.load_state_batch_bundle().STATE_TO_MODULE['OK']]
        texts = [
            'Entity Name: INHERITANCE OF HOPE\nStatus: In Existence\nFILING HISTORY :\n75415460001 Application for Registration February 2, 2023 1',
            'Entity Name: INHERITANCE OF HOPE, INC.\nStatus: In Existence\nFILING HISTORY :\n75415460002 Renewal Registration March 9, 2026 1',
        ]
        with patch.object(cc, 'trial_identity', return_value={'origin': 'fixture'}), \
             patch.object(module, 'body_text', side_effect=texts):
            self.assertEqual(cc.ok_open_latest_equivalent_detail(page, org, module, (450, None, 'INHERITANCE OF HOPE', '4313292546')), ('INHERITANCE OF HOPE, INC.', '4312524349'))
        self.assertEqual(len(org.ok_compared_records), 2)
        self.assertEqual(page.goto.call_count, 2)

    def test_ok_incomplete_duplicate_cannot_leave_old_record_definitive(self):
        org = cc.checker.Organization('Inheritance of Hope', '75-3243566')
        org.ok_equivalent_records = [('INHERITANCE OF HOPE', '4313292546'), ('INHERITANCE OF HOPE, INC.', '4312524349')]
        module = cc.state_batch_modules(['OK'])[cc.load_state_batch_bundle().STATE_TO_MODULE['OK']]
        for second in ('Entity Name: INHERITANCE OF HOPE, INC.\nStatus: In Existence',
                       'Entity Name: DIFFERENT ORGANIZATION\nStatus: In Existence\nFILING HISTORY :'):
            page = Mock()
            def navigate(url, **kwargs):
                page.url = url
                return SimpleNamespace(status=200)
            page.goto.side_effect = navigate
            page.locator.return_value.count.return_value = 0
            with patch.object(cc, 'trial_identity', return_value={'origin': 'fixture'}), \
                 patch.object(module, 'body_text', side_effect=['Entity Name: INHERITANCE OF HOPE\nStatus: In Existence\nFILING HISTORY :\n75415460001 Application for Registration February 2, 2023 1', second]):
                with self.assertRaises((TimeoutError, ValueError)):
                    cc.ok_open_latest_equivalent_detail(page, org, module, (450, None, 'INHERITANCE OF HOPE', '4313292546'))

    def test_ok_single_record_keeps_existing_navigation(self):
        org = cc.checker.Organization('Example Relief', '12-3456789')
        org.ok_equivalent_records = [('Example Relief', '4312345678')]
        page, link, module = Mock(), Mock(), Mock()
        with patch.object(cc, 'ok_open_selected_detail') as existing:
            self.assertEqual(cc.ok_open_latest_equivalent_detail(page, org, module, (450, link, 'Example Relief', '4312345678')), ('Example Relief', '4312345678'))
            existing.assert_called_once_with(page, link, org, module, '4312345678')
        page.goto.assert_not_called()

    def test_p4l_typed_field_requires_exact_reviewed_identity(self):
        token = cc.REVIEWED_NAME_CONTEXT.set({'204235269': ('P4L',)})
        try:
            self.assertEqual(cc.structured_registry_name('P4L', 'Lemonade Day', '204235269'), 'P4L')
            for value in ('PFL', 'P4', '123', 'DBA', 'INC'):
                self.assertEqual(cc.structured_registry_name(value, 'Lemonade Day', '204235269'), '')
            self.assertEqual(cc.structured_registry_name('P4L', 'Unrelated Charity', '123456789'), '')
        finally:
            cc.REVIEWED_NAME_CONTEXT.reset(token)

    def test_compound_queries_keep_both_sides_without_word_hyphen_splitting(self):
        for sep in (' — ', ' – ', ' - ', ' / '):
            self.assertEqual(cc.licensed_compound_retrieval_names('Lemonade Day'+sep+'P4L'), ['Lemonade Day', 'P4L'])
        for name in ('Make-A-Wish Foundation', 'Al-Ayn Social Care', 'Ordinary Charity'):
            self.assertEqual(cc.licensed_compound_retrieval_names(name), [])

    def test_nv_compound_searches_cannot_certify_absence_from_one_side(self):
        org = cc.checker.Organization('Lemonade Day — P4L', '20-4235269')
        seen = []
        def source(query):
            seen.append(query['name'])
            return {'state': 'NV', 'query': query, 'complete': query['name'] != 'P4L',
                    'verification_pending': False, 'total': 0, 'rows': []}
        with patch.object(cc, 'trial_identity', return_value={'origin': 'fixture'}), \
             patch.object(cc, 'licensed_charity_names', return_value=([org.organization_name], [])):
            with self.assertRaises(ValueError):
                cc.final_four_browser_lookup(org, 'NV', source)
        self.assertEqual(seen, ['Lemonade Day', 'P4L'])

    def test_irs_index_padded_and_unpadded_links_still_require_same_ein(self):
        one, two, other = '202610509349300401', '202631359349315203', '202600499349301960'
        source = f'/organizations/43367888/{one}/full /organizations/043367888/{two}/full /organizations/143367888/{other}/full'
        self.assertEqual(cc.irs_index_object_ids(source, '04-3367888'), [one, two])
        self.assertEqual(cc.irs_index_object_ids(source, '99-9999999'), [])

    def test_ms_article_free_primary_precedes_program_aliases(self):
        token = cc.REVIEWED_NAME_CONTEXT.set({'043367888': ('THE GIVING BACK FUND, INC.', 'Afghan Innovation Fund', 'Africa10')})
        try:
            names = cc.ms_name_search_plan('The Giving Back Fund', '043367888')
            self.assertLess(names.index('Giving Back Fund'), names.index('Afghan Innovation Fund'))
            self.assertIn('Africa10', names)
        finally:
            cc.REVIEWED_NAME_CONTEXT.reset(token)


class ReportedPublicRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = cc.checker.sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.pw.stop()

    def test_ar_p4l_row_is_retained_and_expired_is_delinquent(self):
        page = self.browser.new_page()
        token = cc.REVIEWED_NAME_CONTEXT.set({'204235269': ('P4L',)})
        try:
            page.set_content('<table><tbody><tr><td>P4L</td><td>Charity</td><td>Registration-Expired</td><td>2018-03-29</td></tr></tbody></table>')
            org = cc.checker.Organization('Lemonade Day — P4L', '20-4235269')
            rows = cc.ar_result_rows(page, org)
            self.assertEqual(rows[0]['name'], 'P4L')
            self.assertEqual(cc.ar_candidate_identity(rows[0], org.organization_name, cc.organization_match_target_variants(org.organization_name, org.ein), org.ein), 'accept')
            self.assertEqual(cc.ar_status_from_text(rows[0]['status']), 'Delinquent')
        finally:
            cc.REVIEWED_NAME_CONTEXT.reset(token); page.close()

    def test_ok_retains_reviewed_short_name_and_only_equivalent_duplicates(self):
        page = self.browser.new_page()
        token = cc.REVIEWED_NAME_CONTEXT.set({'204235269': ('P4L',)})
        try:
            page.set_content('<table><tr><td><a href="charityDetail.aspx?id=4312345678">4312345678</a></td><td>P4L</td><td>Charitable Organization</td></tr></table>')
            org = cc.checker.Organization('Lemonade Day — P4L', '20-4235269')
            self.assertEqual(cc.ok_choose_safe_result_row_on_page(page, org, None)[2], 'P4L')
            org = cc.checker.Organization('Inheritance of Hope', '75-3243566')
            candidates = [('4313292546', 'INHERITANCE OF HOPE'), ('4312524349', 'INHERITANCE OF HOPE, INC.'), ('4313804944', 'THE VILLAGE OF HOPE')]
            page.set_content('<table>'+''.join(f'<tr><td><a href="charityDetail.aspx?id={ident}">{ident}</a></td><td>{html.escape(name)}</td><td>Charitable Organization</td></tr>' for ident,name in candidates)+'</table>')
            cc.ok_choose_safe_result_row_on_page(page, org, None)
            self.assertEqual({ident for _,ident in org.ok_equivalent_records}, {'4313292546', '4312524349'})
        finally:
            cc.REVIEWED_NAME_CONTEXT.reset(token); page.close()


if __name__ == '__main__':
    unittest.main()
