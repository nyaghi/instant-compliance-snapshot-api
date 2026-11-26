import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch, Mock

import registry_snapshot_server as app
from deployment import ct_budget


class ConnecticutBudget(unittest.TestCase):
    def test_actual_error_redirect_is_unavailable_not_negative(self):
        body = '1|#||4|60|pageRedirect||%2fErrorPage.aspx%3fe%3d70d10745-e771-41c6-b76f-128df308311b|'
        response = Mock(text=body)
        session = Mock()
        session.post.return_value = response
        with (patch.object(app, 'known_names_for_ein', return_value=[]),
              patch.object(app, 'ct_direct_prepare_session', return_value=(session, {}, {}))):
            result = app.search_ct_direct(app.checker.Organization('Partnership for Civil Justice Fund', '262851211'))
        self.assertEqual(result.status, 'Site Not Reachable')
        self.assertFalse(result.success)
        self.assertEqual(session.post.call_count, 1)
        self.assertIn('application error page', result.error)

    def test_completed_empty_and_positive_payloads_are_unchanged(self):
        for body in ['Showing 0 results', 'Showing 1 result <tr>PARTNERSHIP</tr>',
                     '1|#||4|20|pageRedirect||/lookup/licenselookup.aspx|']:
            self.assertIsNone(ct_budget.check_response(body))

    def test_complete_source_dispatch_cannot_restart_allowance(self):
        now = [0.0]
        calls = []

        def stalled_form(cap):
            duration = ct_budget.timeout(cap)
            calls.append(duration)
            now[0] += duration
            raise TimeoutError('source did not respond')

        with (patch.object(time, 'perf_counter', side_effect=lambda: now[0]),
              patch.object(app, 'CT_DIRECT_MAX_SECONDS', 30),
              patch.object(app, 'trial_identity', return_value=False),
              patch.object(app, 'known_names_for_ein', return_value=[]),
              patch.object(app, 'response_data_for_lookup', side_effect=lambda result, *args: vars(result)),
              patch.object(app, 'ct_direct_prepare_session', side_effect=stalled_form)):
            result = app._run_single_state_lookup_reliably_core('Partnership for Civil Justice Fund', '262851211', 'CT')
        self.assertEqual(result['status'], 'Site Not Reachable')
        self.assertFalse(result['success'])
        self.assertEqual(result['semantic_attempts'], 1)
        self.assertLessEqual(now[0], 30)
        self.assertLessEqual(len(calls), 2)

    def test_repeated_stalled_forms_share_existing_allowance(self):
        now = [0.0]
        calls = []

        def stalled_form(cap):
            duration = ct_budget.timeout(cap)
            calls.append(duration)
            now[0] += duration
            raise TimeoutError('source did not respond')

        with (patch.object(time, 'perf_counter', side_effect=lambda: now[0]),
              patch.object(app, 'CT_DIRECT_MAX_SECONDS', 30),
              patch.object(app, 'known_names_for_ein', return_value=[]),
              patch.object(app, 'ct_direct_prepare_session', side_effect=stalled_form)):
            result = app.search_ct_direct(app.checker.Organization('Partnership for Civil Justice Fund', '262851211'))
        self.assertEqual(result.status, 'Site Not Reachable')
        self.assertFalse(result.success)
        self.assertLessEqual(now[0], 30)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.reason_code, 'CT_SEARCH_FORM_UNAVAILABLE')
        self.assertIn('could not open Connecticut\'s registry search form after 2 attempts',
                      app.comments_for_result(result, '', result.status))

    def test_outer_loop_does_not_restart_failed_connecticut(self):
        failure = {'state': 'CT', 'status': 'Site Not Reachable', 'success': False}
        with patch.object(app, 'run_state_lookup', return_value=failure) as lookup:
            result = app._run_single_state_lookup_reliably_core('Example', '123456789', 'CT')
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(result['semantic_attempts'], 1)

    def test_context_restored_and_nested_allowance_cannot_extend(self):
        with patch.object(time, 'perf_counter', return_value=100):
            token = ct_budget.STOP.set(110)
            try:
                self.assertEqual(ct_budget.run(lambda _: ct_budget.timeout(30), None, 30), 10)
                self.assertEqual(ct_budget.STOP.get(), 110)
            finally:
                ct_budget.STOP.reset(token)
        self.assertEqual(ct_budget.STOP.get(), float('inf'))

    def test_expired_allowance_cannot_start_another_request(self):
        token = ct_budget.STOP.set(time.perf_counter() - 1)
        try:
            with self.assertRaises(TimeoutError):
                app.ct_direct_prepare_session(15)
        finally:
            ct_budget.STOP.reset(token)

    def test_real_delayed_http_is_cut_off_by_remaining_budget(self):
        from curl_cffi import requests

        class Slow(BaseHTTPRequestHandler):
            def do_POST(self):
                time.sleep(1)
                try:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'Showing 0 results')
                except (BrokenPipeError, ConnectionResetError):
                    pass
            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Slow)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        session = requests.Session()

        class LocalSession:
            def post(self, url, **kwargs):
                return session.post('http://127.0.0.1:' + str(server.server_port), **kwargs)

        started = time.perf_counter()
        try:
            with self.assertRaises(requests.exceptions.Timeout):
                ct_budget.run(lambda _: app.ct_direct_post_query(LocalSession(), {}, {}, 'Example', 15), None, 0.3)
            self.assertLess(time.perf_counter() - started, 0.8)
        finally:
            server.shutdown()
            server.server_close()
            session.close()


if __name__ == '__main__':
    unittest.main()
