"""Staging connector admission, detail and recovery behavior; no live I/O."""
import copy
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc


class ConnectorVersionControls(unittest.TestCase):
    def setUp(self):
        for name, value in [('ny_connector_origin_allowed', lambda _: True),
                            ('is_verified_internal_passcode', lambda *_: True),
                            ('NY_CONNECTOR_SIGNING_KEY', 'test-only-' * 8)]:
            p = patch.object(cc, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.payload = dict(action='start', email='reviewer@example.test',
            admin_passcode='test-only', device_id='test-session-device',
            organization_name='Independent Literacy Foundation', ein='123456789',
            mode='standard', connector_version='0.6.128')

    def test_staging_start_and_signed_continuation_preserve_127_and_admit_128(self):
        for state in ['NY', 'IL', 'GA']:
            for version in ['0.6.127', '0.6.128']:
                with self.subTest(state=state, version=version), patch.object(cc, 'trial_identity', return_value={'permanent_staging': True}), patch.object(cc, 'ny_connector_advance', return_value={'phase': 'complete', 'result': {}}) as advance:
                    code, _ = cc.ny_connector_request(dict(self.payload, state=state, connector_version=version), cc.NY_CONNECTOR_ORIGIN)
                    self.assertEqual(code, 200)
                    record = advance.call_args.args[0]
                    token = cc.ny_connector_pack(record)
                    restored = cc.ny_connector_unpack(token, record['email'], record['device'])
                    self.assertEqual(restored['connector_version'], version)
                    self.assertEqual(restored['state'], state)

    def test_unsupported_and_nonstaging_versions_stay_rejected(self):
        for trial, version in [(None, '0.6.128'), ({'permanent_staging': True}, '0.6.129')]:
            with self.subTest(trial=trial, version=version), patch.object(cc, 'trial_identity', return_value=trial), patch.object(cc, 'ny_connector_advance') as advance:
                code, _ = cc.ny_connector_request(dict(self.payload, connector_version=version), cc.NY_CONNECTOR_ORIGIN)
                self.assertEqual(code, 400)
                advance.assert_not_called()
        with patch.object(cc, 'trial_identity', return_value=None), patch.object(cc, 'ny_connector_advance', return_value={'phase': 'complete', 'result': {}}):
            self.assertEqual(cc.ny_connector_request(dict(self.payload, connector_version='0.5.10'), cc.NY_CONNECTOR_ORIGIN)[0], 200)

    def test_128_keeps_browser_verified_ny_detail_in_staging_only(self):
        record = dict(organization_name=self.payload['organization_name'], ein='12-3456789', state='NY',
                      connector_version='0.6.128', completed=[])
        for trial, enabled in [({'permanent_staging': True}, True), (None, False)]:
            with self.subTest(trial=trial), patch.object(cc, 'trial_identity', return_value=trial), patch.object(cc, 'search_ny_direct', return_value=object()) as search, patch.object(cc, 'response_data_for_lookup', return_value={}):
                self.assertEqual(cc.ny_connector_advance(record)['phase'], 'complete')
                self.assertEqual(search.call_args.kwargs['registry_detail_provider'] is not None, enabled)

    def test_128_keeps_existing_il_recovery_bounds_and_staging_scope(self):
        now = time.time()
        record = dict(state='IL', purpose='registration', connector_version='0.6.128', recovery_protocol='il-fresh-page-v1',
                      issued=now, completed=[], pending={'query_id': 'original', 'query': {'ein': '123456789'}})
        payload = dict(reason='NY_CONNECTOR_IL_VERIFICATION_PENDING', query_id='original')
        with patch.object(cc, 'trial_identity', return_value=None):
            self.assertIsNone(cc.il_verification_recovery(copy.deepcopy(record), payload, now))
        with patch.object(cc, 'trial_identity', return_value={'permanent_staging': True}):
            self.assertIsNone(cc.il_verification_recovery(copy.deepcopy(record), dict(payload, query_id='stale'), now))
            response = cc.il_verification_recovery(record, payload, now)
            self.assertEqual(response['recovery']['action'], 'fresh_browser')
            self.assertNotEqual(response['query_id'], 'original')
            self.assertEqual(record['completed'], [])
            self.assertIsNone(cc.il_verification_recovery(record, payload, now))


if __name__ == '__main__':
    unittest.main()
