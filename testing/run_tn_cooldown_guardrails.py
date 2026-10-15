"""TN source throttling stays inconclusive; no registry requests."""
import time
import unittest
from unittest.mock import patch
import registry_snapshot_server as cc


class TennesseeCooldownControls(unittest.TestCase):
    def test_rate_limit_explained_without_identity_or_negative_result(self):
        for state in ['TN', 'NV']:
            captured = []
            def render(result, *args):
                captured.append(result)
                return {'status': result.status, 'success': result.success}
            record = dict(state=state, organization_name='Independent Literacy Charity',
                          ein='123456789', mode='standard', alternate_names=[],
                          issued=time.time()-1, completed=[], pending={})
            with patch.object(cc, 'response_data_for_lookup', side_effect=render):
                result = cc.final_four_connector_failure(record, 'NY_CONNECTOR_REGISTRY_TN_RATE_LIMITED')
            self.assertEqual(result['status'], 'Unable to Confirm')
            self.assertFalse(result['success'])
            self.assertEqual('HTTP 429' in result['comments'], state == 'TN')
            self.assertEqual('source cooldown' in result['comments'], state == 'TN')
            self.assertFalse(getattr(captured[0], '_cc_identity_review', None))


if __name__ == '__main__':
    unittest.main()
