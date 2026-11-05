"""Replay the live MA failure through final response formatting, without source calls."""
import copy
import json
import socket
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as m

FIXTURE = Path(__file__).parent / 'fixtures/gate25/ma-live-deactivated.json'

class FinalStatus(unittest.TestCase):
    def setUp(self):
        p = patch.object(socket, 'create_connection', side_effect=AssertionError('Offline replay only'))
        p.start(); self.addCleanup(p.stop)
        self.saved = json.loads(FIXTURE.read_text(encoding='utf-8'))

    def replay(self, evidence=None):
        d = self.saved
        org = m.checker.Organization(d['organization_name'], d['ein'])
        r = m.checker.StateResult(org.organization_name, org.ein, 'MA', 'Delinquent', d['source_url'])
        for key in ['success', 'matched_registry_name', 'matched_registry_identifier']:
            setattr(r, key, d[key])
        m.annotate_ma_visible_form_pc_due(r, copy.deepcopy(evidence or d['ma_filing_evidence']))
        body = 'Annual Filings and Documents\nNo documents found.\nCharity Registration Documents\nNo documents found.'
        return org, r, body

    def test_actual_live_record_survives_final_response_and_comments(self):
        org, r, body = self.replay()
        data = m.response_data_for_lookup(r, body, org, org.organization_name, org.ein, 'MA', time.perf_counter())
        self.assertEqual(data['status'], 'Closed / Withdrawn / Canceled')
        self.assertEqual(data['status_reason'], 'MA_EXPLICIT_DEACTIVATED')
        self.assertEqual(data['matched_registry_identifier'], '034900')
        self.assertIn('Deactivated', data['comments'])
        self.assertIn('does not establish that the organization itself dissolved', data['comments'])
        self.assertNotIn('Confirmation with the state is needed', data['comments'])

    def test_invalid_or_unsupported_evidence_cannot_take_precedence(self):
        for field, value in [('ago_account', '999999'), ('ago_account', ''),
                             ('registry_status', 'Suspended'), ('registry_status', 'Unknown'),
                             ('contrary_status', False)]:
            with self.subTest(field=field, value=value):
                org, r, body = self.replay()
                r.ma_filing_evidence[field] = value
                self.assertEqual(m.true_status_from_body(r, body), 'Unable to Confirm')
        for field, value in [('success', False), ('matched_registry_name', ''),
                             ('raw_status_text', 'Charity Status: Active')]:
            with self.subTest(field=field):
                org, r, body = self.replay(); setattr(r, field, value)
                self.assertNotEqual(m.true_status_from_body(r, body), 'Closed / Withdrawn / Canceled')

    def test_existing_pending_empty_and_incomplete_histories_unchanged(self):
        cases = [
            ({'registration_pending': True, 'ago_account': '034900', 'registry_status': 'Pending'}, 'Pending'),
            ({'empty_history_confirmed': True, 'ago_account': '034900'}, 'Delinquent'),
            ({'contrary_status': True, 'ago_account': '034900', 'registry_status': 'Unknown'}, 'Needs Review'),
            ({'contrary_status': True, 'ago_account': '034900', 'registry_status': 'Suspended'}, 'Needs Review'),
        ]
        for evidence, expected in cases:
            with self.subTest(evidence=evidence):
                org, r, body = self.replay(evidence)
                self.assertEqual(m.true_status_from_body(r, body), expected)

if __name__ == '__main__': unittest.main(verbosity=2)
