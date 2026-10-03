"""Illinois query coverage and terminal cleanup do not weaken identity checks."""
import sys, time, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc


class IllinoisCoverage(unittest.TestCase):
    def test_all_reviewed_names_stay_in_plan(self):
        required = ['Air Force Academy Foundation', 'USAFA Endowment, Inc.']
        plan = cc.il_browser_name_queries(required, ['Air Force Academy', 'air force', 'USAFA Endowment', 'Endowment'])
        self.assertEqual(plan, required + ['air force', 'Endowment'])

    def test_punctuation_and_distinct_aliases_are_not_conflated(self):
        self.assertEqual(cc.il_browser_name_queries(['Example Charity'],
            ['Air-Force Academy', 'air force', 'Other Alias']),
            ['Example Charity', 'Air-Force Academy', 'air force', 'Other Alias'])

    def test_case_insensitive_literal_superset_covers_generated_variation(self):
        self.assertEqual(cc.il_browser_name_queries(['Example'], ['THE AIR FORCE FOUNDATION', 'air force']),
                         ['Example', 'air force'])

    def test_generated_narrower_than_reviewed_name_is_redundant(self):
        self.assertEqual(cc.il_browser_name_queries(['Example Charity'], ['Example Charity Incorporated']), ['Example Charity'])

    def test_incomplete_covering_search_cannot_return_negative(self):
        org = cc.checker.Organization('Example Charity', '123456789')
        def evidence(query):
            if query.get('orgName') == 'Example': raise TimeoutError('Incomplete broad search')
            return {'rows': []}
        with patch.object(cc, 'licensed_charity_names', return_value=(['Example Charity'], ['Example Foundation', 'Example'])):
            with self.assertRaises(TimeoutError): cc.il_ga_browser_lookup(org, 'IL', evidence)

    def test_ga_plan_is_unchanged(self):
        org = cc.checker.Organization('Example Charity', '123456789')
        seen = []
        def evidence(query): seen.append(query['orgName']); return {'rows': []}
        with patch.object(cc, 'licensed_charity_names', return_value=(['Example Charity'], ['Example Foundation', 'Example'])):
            cc.il_ga_browser_lookup(org, 'GA', evidence)
        self.assertEqual(seen, ['Example Charity', 'Example Foundation', 'Example'])


class DeadlineCleanup(unittest.TestCase):
    def setUp(self):
        for name, value in [('NY_CONNECTOR_SIGNING_KEY', 'test-only-cleanup-key-at-least-thirty-two-characters'),
                            ('is_verified_internal_passcode', lambda *args: True),
                            ('licensed_charity_names', lambda *args: (['Example Charity'], []))]:
            p = patch.object(cc, name, value); p.start(); self.addCleanup(p.stop)
        self.auth = {'email':'test@compliance-express.com', 'admin_passcode':'test-only', 'device_id':'test-cleanup-device'}

    def request(self, **payload):
        return cc.ny_connector_request({**self.auth, **payload}, cc.NY_CONNECTOR_ORIGIN)

    def start(self, state='IL'):
        with patch.object(cc.time, 'time', return_value=1000):
            code, result = self.request(action='start', state=state, organization_name='Example Charity', ein='123456789', connector_version='0.5.6')
        self.assertEqual(code, 200)
        return result

    def test_late_failure_saves_structured_inconclusive_for_both_states(self):
        for state in ['IL', 'GA']:
            check = self.start(state)
            with patch.object(cc.time, 'time', return_value=1301):
                code, result = self.request(action='fail', check_token=check['check_token'], reason='NY_CONNECTOR_TIMEOUT')
            self.assertEqual(code, 200); self.assertEqual(result['result']['state'], state)
            self.assertEqual(result['result']['status'], 'Unable to Confirm')
            self.assertIn('five-minute', result['result']['comments'])

    def test_late_evidence_is_not_accepted_or_used_to_extend_search(self):
        check = self.start()
        with patch.object(cc.time, 'time', return_value=1301), patch.object(cc, 'ny_connector_advance') as advance:
            code, result = self.request(action='advance', check_token=check['check_token'], query_id=check['query_id'], evidence={})
        self.assertEqual(code, 200); self.assertEqual(result['result']['status'], 'Unable to Confirm')
        advance.assert_not_called()

    def test_cleanup_grace_is_bounded_and_bound_to_device(self):
        check = self.start()
        with patch.object(cc.time, 'time', return_value=1361):
            self.assertEqual(self.request(action='fail', check_token=check['check_token'])[0], 410)
        with patch.object(cc.time, 'time', return_value=1301):
            self.assertEqual(self.request(action='fail', check_token=check['check_token'], device_id='wrong-device-value')[0], 410)

    def test_ny_still_expires_at_original_deadline(self):
        with patch.object(cc, 'ny_connector_advance', return_value={'phase':'search', 'query_id':'test-query', 'query':{'ein':'123456789'}}):
            check = self.start('NY')
        with patch.object(cc.time, 'time', return_value=1301):
            self.assertEqual(self.request(action='fail', check_token=check['check_token'])[0], 410)


class VerificationRecovery(DeadlineCleanup):
    def start_recovery(self, state='IL', **overrides):
        args=dict(action='start',state=state,organization_name='Example Charity',ein='123456789',
                  connector_version='0.5.10',recovery_protocol='il-fresh-page-v1')
        with patch.object(cc.time,'time',return_value=1000):
            code, check=self.request(**{**args,**overrides})
        self.assertEqual(code,200)
        return check

    def fail(self, check, at=1060, **overrides):
        args=dict(action='fail',check_token=check['check_token'],query_id=check['query_id'],
                  reason='NY_CONNECTOR_IL_VERIFICATION_PENDING')
        with patch.object(cc.time,'time',return_value=at):
            code, result=self.request(**{**args,**overrides})
        self.assertEqual(code,200)
        return result

    def test_one_recovery_preserves_query_and_signed_deadline(self):
        check=self.start_recovery(); retry=self.fail(check)
        self.assertEqual(retry['phase'],'search');self.assertEqual(retry['query'],check['query'])
        self.assertNotEqual(retry['query_id'],check['query_id'])
        with patch.object(cc.time,'time',return_value=1060):
            record=cc.ny_connector_unpack(retry['check_token'],self.auth['email'],self.auth['device_id'])
        self.assertEqual(record['issued'],1000);self.assertEqual(record['expires'],1360)
        self.assertEqual(record['completed'],[])
        terminal=self.fail(retry,at=1120)
        self.assertEqual(terminal['phase'],'complete');self.assertEqual(terminal['result']['status'],'Unable to Confirm')
        self.assertEqual(terminal['result']['connector_recovery']['attempt'],1)
        self.assertIn('fresh-page recovery',terminal['result']['comments'])

    def test_no_recovery_for_other_states_errors_old_clients_or_low_budget(self):
        for changes in [dict(state='GA'),dict(connector_version='0.5.9'),dict(recovery_protocol=''),dict(purpose='identity')]:
            self.assertEqual(self.fail(self.start_recovery(**changes))['phase'],'complete')
        for reason in ['NY_CONNECTOR_IL_DETAIL_BLANK','NY_CONNECTOR_IL_RESPONSE_TIMEOUT','NY_CONNECTOR_INCOMPLETE']:
            self.assertEqual(self.fail(self.start_recovery(),reason=reason)['phase'],'complete')
        self.assertEqual(self.fail(self.start_recovery(),at=1180)['phase'],'complete')

    def test_stale_failure_cannot_authorize_recovery(self):
        self.assertEqual(self.fail(self.start_recovery(),query_id='old-query')['phase'],'complete')

    def test_completed_evidence_retained_and_old_query_response_rejected(self):
        check=self.start_recovery()
        with patch.object(cc.time,'time',return_value=1010):
            _, name=self.request(action='advance',check_token=check['check_token'],query_id=check['query_id'],
                evidence={'query':check['query'],'complete':True,'total':0,'rows':[]})
        retry=self.fail(name)
        self.assertEqual(retry['query'],name['query'])
        with patch.object(cc.time,'time',return_value=1070):
            record=cc.ny_connector_unpack(retry['check_token'],self.auth['email'],self.auth['device_id'])
            self.assertEqual(len(record['completed']),1)
            evidence={'query':retry['query'],'complete':True,'total':0,'rows':[]}
            self.assertEqual(self.request(action='advance',check_token=retry['check_token'],query_id=name['query_id'],evidence=evidence)[0],409)
            code, result=self.request(action='advance',check_token=retry['check_token'],query_id=retry['query_id'],evidence=evidence)
        self.assertEqual(code,200);self.assertEqual(result['result']['status'],'Not Registered / Non-Compliant')
        self.assertEqual(result['result']['connector_recovery']['reason'],'NY_CONNECTOR_IL_VERIFICATION_PENDING')

    def test_recovery_does_not_accept_late_evidence(self):
        retry=self.fail(self.start_recovery())
        with patch.object(cc.time,'time',return_value=1301):
            _, result=self.request(action='advance',check_token=retry['check_token'],query_id=retry['query_id'],
                evidence={'query':retry['query'],'complete':True,'total':0,'rows':[]})
        self.assertEqual(result['result']['status'],'Unable to Confirm')
        self.assertIn('five-minute',result['result']['comments'])


if __name__ == '__main__': unittest.main()
