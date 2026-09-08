"""Verify Alaska's parallel allowance without live registry calls."""
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc

class AlaskaBatchTests(unittest.TestCase):
    def test_all_supported_state_requests_keep_results_and_independent_budgets(self):
        states = {r['state'] for r in json.loads(Path(__file__).with_name('weekly-data-regression-baseline.json').read_text())}
        for state in states:
            with self.subTest(state=state):
                expected = {'state': state, 'status': 'Current', 'matched_registry_identifier': 'control'}
                with patch.object(cc, 'BATCH_FANOUT_STATE_TIMEOUT_SECONDS', 87), patch.object(cc.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps({'results':[expected]}).encode())) as request:
                    result = cc.run_fanout_state_lookup_for_batch('Control', '123456789', state)
                self.assertEqual(request.call_args.kwargs['timeout'], 115 if state in {'AK','OK'} else 87)
                self.assertEqual(result, {**expected, 'batch_fanout':'single_state_http'})

    def test_alaska_timeout_remains_inconclusive_and_reports_actual_allowance(self):
        with patch.object(cc.urllib.request, 'urlopen', side_effect=TimeoutError('test timeout')):
            result = cc.run_fanout_state_lookup_for_batch('Control', '123456789', 'AK')
        self.assertEqual(result['status'], 'Unable to Verify')
        self.assertFalse(result['success'])
        self.assertAlmostEqual(result['lookup_seconds'], 115, delta=1)

if __name__ == '__main__': unittest.main()
