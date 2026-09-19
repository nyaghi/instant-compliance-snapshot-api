"""Replay partial detail failures without transferring identity across entities."""
import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c


class SameCredentialLocations(unittest.TestCase):
    name = 'Regional Learning Association'
    ein = '123456789'
    href = 'CredSummaryDetails.aspx?chid=123'

    def row(self, kind, city, number='76543-800', name=None, href=None):
        name, href = name or self.name, href or self.href
        if kind == 'html':
            cells = [number, 'Charitable Organization', f'<a href="{href}">{name}</a>', city, '06/13/2025', '07/31/2027']
            return '<tr>' + ''.join(f'<td>{v}</td>' for v in cells) + '</tr>'
        return f'| {number} | Charitable Organization | [{name}]({href}) | {city} | 06/13/2025 | 07/31/2027 |'

    def run_rows(self, kind, first_changes=None, details=None):
        first = self.row(kind, 'BOSTON, MA', **(first_changes or {}))
        second = self.row(kind, 'NEW YORK, NY')
        page = first + '\n' + second
        if kind == 'html':
            page = '<table id="ctl00_cphMainContent_OrgCredentialSearch_gvCredentialSearchResults">' + page + '</table>'
        detail = f'Name: {self.name} Credential Type: Charitable Organization Credential Number: 76543-800 Location: NEW YORK, NY Status License is current (Active)'
        method = c.wi_best_match_from_html if kind == 'html' else c.wi_best_match_from_markdown
        def evidence(ein, location):
            return {'decision': 'corroborated' if ein == self.ein and location == 'BOSTON, MA' else 'conflict', 'registry_location': location}
        with patch.object(c, 'wi_http_detail_text', side_effect=details or ['', detail]), \
             patch.object(c, 'wi_reader_text', side_effect=details or ['', detail]), \
             patch.object(c, 'registry_address_evidence', side_effect=evidence), \
             patch.object(c, 'registry_cross_state_identity', return_value={}), \
             patch.object(c, 'registry_identity_preference', return_value=0), \
             patch.object(c, 'known_names_for_ein', return_value=[]):
            return method(page, [self.name], original_name=self.name, ein=self.ein)

    def test_failed_first_detail_does_not_discard_same_credential_location(self):
        for kind in ['html', 'markdown']:
            with self.subTest(kind=kind):
                result = self.run_rows(kind)
                self.assertFalse(result['identity_conflict'])
                self.assertEqual(result['address_evidence']['registry_location'], 'BOSTON, MA')
                self.assertEqual(c.wi_status_from_detail_status(result['detail_status']), 'Current')

    def test_different_credential_or_url_cannot_share_address(self):
        for kind in ['html', 'markdown']:
            for changes in [{'number': '99999-800'}, {'href': 'CredSummaryDetails.aspx?chid=999'}]:
                with self.subTest(kind=kind, changes=changes):
                    self.assertTrue(self.run_rows(kind, changes)['identity_conflict'])

    def test_missing_detail_stays_unconfirmed(self):
        for kind in ['html', 'markdown']:
            with self.subTest(kind=kind):
                result = self.run_rows(kind, details=['', ''])
                self.assertTrue(result['identity_conflict'])
                self.assertTrue(result['identity_detail_unavailable'])

    def test_full_name_and_credential_url_are_part_of_identity_key(self):
        key = c.wi_row_identity_key('76543-800', self.name, self.href)
        for name in [self.name + ' Foundation', self.name + ' Wisconsin Chapter']:
            self.assertNotEqual(key, c.wi_row_identity_key('76543-800', name, self.href))

    def test_wrong_ein_or_unverified_primary_cannot_clear_conflict(self):
        candidate = dict(license_number='76543-800', registry_name=self.name, detail_href=self.href,
                         primary_registry_name=self.name, detail_status='License is current (Active)',
                         identity_conflict=True, address_evidence={'decision': 'conflict'})
        locations = {c.wi_row_identity_key('76543-800', self.name, self.href): {'BOSTON, MA'}}
        with patch.object(c, 'registry_address_evidence', return_value={'decision': 'different_ein'}):
            self.assertTrue(c.wi_reconcile_query_locations(candidate, locations, self.ein)['identity_conflict'])
        for changes in [{'primary_registry_name': ''}, {'identity_detail_unavailable': True}, {'detail_status': ''}]:
            with patch.object(c, 'registry_address_evidence') as evidence:
                self.assertTrue(c.wi_reconcile_query_locations(dict(candidate, **changes), locations, self.ein)['identity_conflict'])
                evidence.assert_not_called()


if __name__ == '__main__':
    unittest.main()
