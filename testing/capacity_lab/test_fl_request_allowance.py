"""A slow complete POST succeeds without relaxing identity, TLS or total limits."""
import ast
import http.client
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import registry_snapshot_server as m
from testing.capacity_lab.test_fl_error_recovery import Recovery


class RequestAllowance(unittest.TestCase):
    def run_case(self, enabled=True, duration=9, remaining=30, broken=False):
        tr = Recovery().transport()
        route = Recovery().request()
        route.request.method = 'POST'
        route.request.post_data_buffer = b'query=Same+Organization'
        clock = [100.0]
        tr.deadline = clock[0] + remaining
        response = tr.opener.open.return_value
        if broken:
            response.read1.side_effect = [b'partial', http.client.IncompleteRead(b'missing')]
        def send(request, timeout):
            clock[0] += min(duration, timeout)
            if duration >= timeout:
                raise TimeoutError('response has not finished')
            return response
        tr.opener.open.side_effect = send
        with patch.object(m, 'fl_verified_transport_first', return_value=enabled), patch.object(m.time, 'monotonic', side_effect=lambda: clock[0]):
            tr.route(route)
        return tr, route, clock[0]

    def test_nine_second_complete_post_succeeds_only_in_lab(self):
        for enabled in (False, True):
            tr, route, elapsed = self.run_case(enabled=enabled)
            self.assertEqual(tr.opener.open.call_args.args[0].data, b'query=Same+Organization')
            if enabled:
                route.fulfill.assert_called_once(); route.abort.assert_not_called()
                self.assertEqual(elapsed, 109); self.assertIsNone(tr.error)
            else:
                route.fulfill.assert_not_called(); route.abort.assert_called_once()
                self.assertIsInstance(tr.error, TimeoutError); self.assertEqual(elapsed, 108)

    def test_remaining_lookup_deadline_takes_precedence(self):
        tr, route, elapsed = self.run_case(remaining=5)
        self.assertEqual(tr.opener.open.call_args.kwargs['timeout'], 5)
        self.assertEqual(elapsed, 105); route.fulfill.assert_not_called()

    def test_slow_partial_body_never_becomes_result(self):
        tr, route, _ = self.run_case(broken=True)
        route.fulfill.assert_not_called(); self.assertIsInstance(tr.error, http.client.IncompleteRead)

    def test_twelve_second_cap_still_applies(self):
        tr, route, elapsed = self.run_case(duration=13)
        route.fulfill.assert_not_called(); self.assertEqual(elapsed, 112)

    def test_only_florida_allowance_and_tested_oregon_guard_change(self):
        from testing.capacity_lab.parsing_scope import strip_fl_request_allowance
        from testing.capacity_lab.or_completion_scope import strip_or_completion
        root = Path(m.__file__).parent
        old = ast.parse(subprocess.check_output(['git','show','181ce82:registry_snapshot_server.py'], cwd=root).decode('utf-8'))
        new = ast.parse(Path(m.__file__).read_text(encoding='utf-8'))
        # Old release has no FunctionType import. Normalize only the independently
        # tested Oregon helper/call sites on both sides before comparing all else.
        for tree in (old, new):
            types = next(n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == 'types')
            if not any(n.name == 'FunctionType' for n in types.names):
                types.names.insert(0, ast.alias(name='FunctionType'))
            strip_or_completion(tree)
        strip_fl_request_allowance(new)
        self.assertEqual(ast.dump(old), ast.dump(new))


if __name__ == '__main__':
    unittest.main()
