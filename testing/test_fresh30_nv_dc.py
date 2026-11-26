import copy
import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import registry_snapshot_server as cc
from deployment import source_availability, state_snapshots


class November25(date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 25)


class MixedHistory(unittest.TestCase):
    def setUp(self):
        data = json.loads((Path(__file__).parent / 'fixtures/nv-risd-mixed-filings.json').read_text())
        self.enterContext(patch.object(cc, 'date', November25))
        self.enterContext(patch.object(cc, 'trial_identity', return_value={'label': 'trial'}))
        self.history = data['filings']
        self.row = cc.nv_charity_detail_evidence(data['fields'], data['query']['identifier'])

    def test_registration_supersedes_old_exemption_in_any_order(self):
        self.history['rows'].reverse()
        selected = cc.nv_charity_filings_evidence(self.row, self.history)
        self.assertEqual(selected['status'], 'Upcoming Filing')
        self.assertEqual(str(selected['solicitation_statement_filed']), '2026-03-04')

    def test_newer_exemption_and_adverse_standing(self):
        self.history['rows'][-1][1] = '11/01/2026'
        self.row['solicitation_declared'] = False
        self.assertEqual(cc.nv_charity_filings_evidence(self.row, self.history)['status'], 'Exempt')
        self.row['raw_status'] = 'Revoked'
        self.assertEqual(cc.nv_charity_filings_evidence(self.row, self.history)['status'], 'Revoked')

    def test_conflicting_missing_future_and_wrong_entity(self):
        for value in ('03/04/2026', '', '03/04/2099'):
            history = copy.deepcopy(self.history)
            history['rows'][-1][1] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                cc.nv_charity_filings_evidence(self.row, history)
        for overrides in ({'identifier': 'NV111'}, {'complete': False}):
            with self.assertRaises(ValueError):
                cc.nv_charity_filings_evidence(self.row, {**self.history, **overrides})
        with self.assertRaises(ValueError):
            cc.nv_charity_filings_evidence({**self.row, 'solicitation_declared': False}, self.history)

    def test_failed_archive_receipt_is_per_entity_and_bounded(self):
        rec = {'state': 'NV'}
        for i in range(20):
            state_snapshots.connector_archive(rec, {'query_id': str(i)}, {'operation':'detail','identifier':str(i)}, {})
        self.assertEqual(len(rec['nv_capture_audit']), 16)
        self.assertEqual(rec['nv_capture_audit'][-1], {'query_id':'19','identifier':'19','disposition':'no_pixels'})


class DcUnavailable(unittest.TestCase):
    def test_count_only_observed_attempts(self):
        for count in (0, 1, 2):
            row = dict(state='DC', status='Site Not Reachable', success=False, reason_code='DC_LICENSE_SOURCE_UNREACHABLE',
                       source_attempts=[{'source':'DC_LICENSE_API','attempt':n+1} for n in range(count)])
            source_availability.apply(row)
            self.assertIn('no completed search', row['comments'])
            self.assertEqual('two attempts' in row['comments'], count == 2)
            self.assertEqual('one attempt' in row['comments'], count == 1)
            self.assertFalse(row.get('evidence_url'))
