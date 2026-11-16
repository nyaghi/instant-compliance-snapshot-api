"""Offline source-failure/control matrix. Network access is forbidden."""
import copy
import json
import socket
import time
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from deployment.source_availability import apply, classify

STATES = 'AK AL AR CA CO CT DC FL GA HI IL KS KY LA MA MD ME MI MN MS NC ND NH NJ NM NV NY OH OK OR PA RI SC TN VA WA WI WV'.split()
FAILURES = {
    'http503': {'error': 'HTTP Error 503: Service Unavailable'},
    'http504': {'raw_status_text': 'HTTP 504 Gateway Timeout'},
    'http522': {'error': 'HTTPError 522'},
    'connection': {'error': 'ConnectionRefusedError: connection refused'},
    'read_timeout': {'error': 'ReadTimeout: registry read timed out'},
    'dns': {'error': 'net::ERR_NAME_NOT_RESOLVED'},
    'navigation': {'error': 'Page.goto: Timeout 30000ms exceeded'},
    'rate_limit': {'error': 'HTTP 429 Too Many Requests'},
    'deadline': {'reason_code': 'RUNNER_TIMEOUT', 'raw_status_text': 'The registry lookup exhausted its source time limit'},
}


def failure(state, **values):
    return {'state': state, 'organization_name': 'Local fixture', 'ein': '123456789',
            'status': 'Unable to Confirm', 'success': False, 'reason_code': 'PORTAL_ERROR', **values}


class Availability(unittest.TestCase):
    def setUp(self):
        self.guard = patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden'))
        self.guard.start()
        self.addCleanup(self.guard.stop)

    def test_38_state_failure_matrix(self):
        self.assertEqual(len(STATES), 38)
        for state in STATES:
            for kind, values in FAILURES.items():
                with self.subTest(state=state, kind=kind):
                    original = failure(state, **values)
                    result = apply(copy.deepcopy(original))
                    self.assertEqual(result['status'], 'Site Not Reachable')
                    self.assertFalse(result['success'])
                    self.assertEqual(result['source_availability']['prior_status'], original['status'])
                    self.assertEqual(apply(copy.deepcopy(result)), result)
                    self.assertNotIn('http', result['comments'].lower())

    def test_healthy_results_and_negative_histories_byte_equal(self):
        for state in STATES:
            for status in ['Current', 'Delinquent', 'Exempt', 'Upcoming Filing', 'Pending',
                           'Revoked', 'Suspended', 'Closed / Withdrawn / Canceled', 'Not Registered']:
                with self.subTest(state=state, status=status):
                    original = failure(state, status=status, success=True,
                                       error='prior HTTP 503 attempt; recovered', evidence_url='/original.pdf',
                                       search_history_url='/original-history.pdf')
                    self.assertEqual(apply(copy.deepcopy(original)), original)

    def test_uncertainty_is_not_an_outage(self):
        controls = [
            {'reason_code': 'PARSER_ERROR', 'error': 'HTTP 503 in a malformed record'},
            {'reason_code': 'NY_CONNECTOR_UNAVAILABLE', 'error': 'ReadTimeout'},
            {'status_reason': 'NY_CONNECTOR_QUEUE_TIMEOUT', 'error': 'ReadTimeout'},
            {'status_reason': 'NY_CONNECTOR_RELAY_TIMEOUT', 'error': 'ReadTimeout'},
            {'status_reason': 'NY_CONNECTOR_NC_VERIFICATION_PENDING', 'error': 'HTTP 403'},
            {'reason_code': 'PORTAL_ERROR'},
            {'raw_status_text': 'Missing filing period; unable to interpret status'},
            {'raw_status_text': 'Timeout waiting for selector to match record'},
            {'error': 'HTTP 400 invalid query'},
            {'status_reason': 'NY_CONNECTOR_SEARCH_HTTP_ERROR', 'error': 'HTTP 400 invalid query'},
            {'raw_status_text': 'Batch lookup exceeded the internal batch time limit', 'reason_code': 'RUNNER_TIMEOUT_RETRY_FAILED'},
            {'status_reason': 'NY_CONNECTOR_INVALID_SEQUENCE'},
            {'reason_code': 'RUNNER_TIMEOUT', 'error': 'Snapshot capture timed out'},
            {'status_reason': 'NY_CONNECTOR_DETAIL_RESPONSE_TIMEOUT'},
            {'error': 'HTTP 503', 'identity_review': {'candidates': [{'id': '1', 'decision': 'accept'}]}},
            {'error': 'HTTP 503', 'matched_registry_name': 'Selected charity'},
            {'error': 'HTTP 503', 'confirmation_required': True},
            {'comments': 'HTTP 503; read timed out'},
        ]
        for state in STATES:
            for values in controls:
                with self.subTest(state=state, values=values):
                    original = failure(state, **values)
                    self.assertEqual(apply(copy.deepcopy(original)), original)

    def test_actual_application_error_paths(self):
        for state, values in [
            ('CT', {'error': 'Connecticut registry returned its application error page'}),
            ('NM', {'status_reason': 'NY_CONNECTOR_REGISTRY_NM_SOURCE_ERROR'}),
            ('ME', {'reason_code': 'ME_SOURCE_APPLICATION_ERROR'}),
        ]:
            self.assertEqual(apply(failure(state, **values))['status'], 'Site Not Reachable')

    def test_complete_formatter_and_retry_loop(self):
        import registry_snapshot_server as app
        with patch.object(app, 'trial_identity', return_value=True):
            for state in STATES:
                with self.subTest(state=state):
                    org = app.checker.Organization('Local fixture', '123456789')
                    result = app.checker.StateResult(org.organization_name, org.ein, state, 'Unable to Confirm', 'https://example.invalid')
                    result.success = False
                    result.error = 'HTTP Error 503: Service Unavailable'
                    # Use the actual result formatter; no registry lookup.
                    data = app.response_data_for_lookup(result, '', org, org.organization_name, org.ein, state, time.perf_counter())
                    self.assertEqual(data['status'], 'Site Not Reachable')
                    self.assertEqual(data['source_availability']['kind'], 'source_error')
                    end = failure(state, **FAILURES['deadline'])
                    with (patch.object(app, 'run_state_lookup', return_value=end) as lookup,
                          patch.object(app, 'run_me_lookup_with_lane', return_value=end) as maine):
                        stopped = app._run_single_state_lookup_reliably_core(org.organization_name, org.ein, state)
                    self.assertEqual(lookup.call_count + maine.call_count, 1)
                    self.assertEqual(stopped['semantic_attempts'], 1)
                    self.assertTrue(stopped['source_availability']['terminal'])

    def test_classification_does_not_add_semantic_retries(self):
        import ast
        import subprocess
        import registry_snapshot_server as app
        baseline = ast.parse(subprocess.check_output(['git', 'show', 'HEAD:registry_snapshot_server.py'], text=True, encoding='utf8'))
        core = next(n for n in baseline.body if isinstance(n, ast.FunctionDef) and n.name == '_run_single_state_lookup_reliably_core')
        for state in STATES:
            original = failure(state, **FAILURES['http503'])
            counts = []
            for candidate in [False, True]:
                response = lambda *a, **k: apply(copy.deepcopy(original)) if candidate else copy.deepcopy(original)
                with (patch.object(app, 'trial_identity', return_value=True),
                      patch.object(time, 'sleep'),
                      patch.object(app, 'run_state_lookup', side_effect=response) as lookup,
                      patch.object(app, 'run_me_lookup_with_lane', side_effect=response) as maine):
                    namespace = dict(vars(app))
                    exec(compile(ast.Module(body=[core], type_ignores=[]), '<QP-baseline>', 'exec'), namespace)
                    function = app._run_single_state_lookup_reliably_core if candidate else namespace[core.name]
                    function('Local fixture', '123456789', state)
                counts.append(lookup.call_count + maine.call_count)
            self.assertEqual(counts[0], counts[1], (state, counts))

    def test_actual_connector_failure_boundaries(self):
        import registry_snapshot_server as app
        with patch.object(app, 'trial_identity', return_value=True):
            for state, code in [('NY','NY_CONNECTOR_SEARCH_RESPONSE_TIMEOUT'),
                                ('IL','NY_CONNECTOR_IL_RESPONSE_TIMEOUT')]:
                record = {'state':state, 'organization_name':'Local fixture', 'ein':'123456789',
                          'completed':[], 'purpose':'registration'}
                got=app.ny_connector_failure(record,code)
                self.assertEqual(got['status'],'Site Not Reachable')
                self.assertFalse(got['success'])
            record['state']='NY'
            got=app.ny_connector_failure(record,'NY_CONNECTOR_SEARCH_HTTP_ERROR')
            self.assertNotEqual(got['status'],'Site Not Reachable')

    def test_oregon_application_error_keeps_existing_bounded_recovery(self):
        import registry_snapshot_server as app
        def response(url, body):
            r=Mock(url=url);r.__enter__=lambda self:r;r.__exit__=lambda *a:None
            r.read.return_value=body;return r
        bad=response('https://justice.oregon.gov/Charities/Error/ErrorMessage?code=666&app=1',
                     b'The provided anti-forgery token is not valid.')
        readable=response('https://justice.oregon.gov/Charities/Charity/details?charityID=71024',b'<table id="info"></table>')
        for responses, expected in [([bad,bad],'Site Not Reachable'),([bad,readable],'Unable to Confirm')]:
            org=app.checker.Organization('Daffy','863177440')
            result=app.checker.StateResult('Daffy','863177440','OR','Delinquent','')
            with (patch.object(app,'trial_identity',return_value=True),
                  patch.object(app,'or_snapshot_row_for_ein',return_value=['71024']),
                  patch.object(app,'or_live_period_evidence',return_value={}),
                  patch.object(app.urllib.request,'urlopen',side_effect=responses) as request):
                got=app.or_confirm_snapshot_delinquency(org,result)
                public=app.response_data_for_lookup(got,'',org,org.organization_name,org.ein,'OR',time.perf_counter())
            self.assertEqual(public['status'],expected)
            self.assertEqual(got.status,'Unable to Confirm')
            self.assertEqual(request.call_count,2)

    def test_oregon_error_does_not_add_outer_retry(self):
        import registry_snapshot_server as app
        original=failure('OR',status_reason='OR_SOURCE_ACCESS_REFUSED',reason_code='OR_SOURCE_ACCESS_REFUSED')
        with (patch.object(app,'trial_identity',return_value=True),
              patch.object(app,'run_state_lookup',side_effect=lambda *a,**k:apply(copy.deepcopy(original))) as lookup):
            app._run_single_state_lookup_reliably_core('Daffy','863177440','OR')
        self.assertEqual(lookup.call_count,1)

    def test_rate_limit_keeps_existing_recovery_policy(self):
        for state in STATES:
            got=classify(failure(state,error='HTTP 429 Too Many Requests'))
            self.assertFalse(got['terminal'])

    def test_prepare_cross_language_fixtures(self):
        output = Path(__file__).parent / 'source_availability_matrix.json'
        rows = [apply(failure(state, **values)) for state in STATES for values in FAILURES.values()]
        output.write_text(json.dumps(rows), encoding='utf8')


if __name__ == '__main__':
    unittest.main()
