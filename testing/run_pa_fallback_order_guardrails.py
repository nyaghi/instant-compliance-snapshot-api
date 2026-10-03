"""PA fallback: complete names before broad contains queries; preserve evidence boundaries."""
import json, sys, unittest, urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class FallbackControls(unittest.TestCase):
    def setUp(self):
        self.org = c.checker.Organization('Focus on the Family', '95-3188150')
        self.exact = dict(EntityName=self.org.organization_name, PersonId=101, EIN=None,
                          StatusName=None, ExpDate=None, CertificateNumber=None)
        self.ein = dict(step='search', ein='953188150', complete=True, http_status=200, row_eins=[])

    def run_search(self, responses, plan=None):
        initial = c.checker.StateResult(self.org.organization_name, self.org.ein, 'PA', 'Not Registered', '')
        def fetch(*args, **kw):
            item = responses.pop(0)
            if isinstance(item, Exception): raise item
            return item if isinstance(item, bytes) else json.dumps(item).encode()
        with patch.object(c.checker, 'search_pa', return_value=initial), \
             patch.object(c, 'identity_fetch', side_effect=fetch) as request, \
             patch.object(c, 'pa_name_search_plan', return_value=plan or [self.org.organization_name, 'Family']):
            result = c.search_pa_with_name_fallback_core(None, self.org, lambda x:x)
        guarded = c.pa_guard_search_completion(result, self.org, [self.ein, *getattr(result, '_pa_api_attempts', [])])
        return guarded, request

    def test_full_organization_name_is_first_not_pruned_by_common_word(self):
        self.assertEqual(c.pa_name_search_plan(self.org)[0], self.org.organization_name)

    def test_exact_probe_keeps_distinctive_fallbacks_without_generic_single_words(self):
        org=c.checker.Organization('Junior Achievement USA','84-1267604')
        plan=c.pa_name_search_plan(org)
        self.assertEqual(plan[0], 'Junior Achievement USA')
        self.assertIn('junior achievement', plan)
        self.assertNotIn('Junior', plan)
        self.assertNotIn('Achievement', plan)

    def test_plan_is_bounded_and_keeps_distinct_aliases(self):
        with patch.object(c, 'known_names_for_ein', return_value=['An Independent Alias']), \
             patch.object(c, 'build_search_queries', return_value=['Focus on the Family', 'Family', 'An Independent Alias']):
            plan = c.pa_name_search_plan(self.org)
        self.assertEqual(plan[:2], [self.org.organization_name, 'An Independent Alias'])
        self.assertLessEqual(len(plan), 10)

    def test_full_name_complete_response_selects_identity_not_first_row(self):
        other = dict(self.exact, EIN='20-0960855', EntityName='FAMILY POLICY ALLIANCE', PersonId=102)
        r, fetch = self.run_search([{'Table':[other,self.exact], 'Table1':[{'RESULTCOUNT':2}]}])
        self.assertEqual(r.status, 'Delinquent')
        self.assertEqual(r.matched_registry_identifier, '101')
        self.assertEqual(fetch.call_count, 1)

    def test_completed_empty_shorter_query_covers_later_literal_extension_only(self):
        r, fetch = self.run_search([{'Table':[], 'Table1':[{'RESULTCOUNT':0}]}]*2,
                                  ['Focus on the Family','Focus on the Family Inc','Different Alias'])
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(r.status, 'Not Registered')
        self.assertEqual(r.queries_attempted, ['Focus on the Family','Different Alias'])

    def test_truncated_response_never_covers_remaining_queries(self):
        r, fetch = self.run_search([{'Table':[self.exact], 'Table1':[{'RESULTCOUNT':2}]},
                                   {'Table':[self.exact], 'Table1':[{'RESULTCOUNT':1}]}],
                                  ['Family','Focus on the Family'])
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(r.status, 'Delinquent')

    def test_truncated_http_200_is_incomplete_not_network_or_negative(self):
        r, _ = self.run_search([{'Table':[self.exact], 'Table1':[{'RESULTCOUNT':1408}]}], ['Family'])
        self.assertEqual(c.public_status(r), 'Unable to Confirm')
        self.assertEqual(r.reason_code, 'PA_NAME_RESPONSE_INCOMPLETE')
        self.assertIn('truncated', r.source_note.lower())
        self.assertNotIn('network failure', r.source_note)
        self.assertFalse(r.success)

    def test_malformed_http_200_is_not_network_or_negative(self):
        for value in [b'<html>not JSON</html>', {'Table':[],'Table1':{'RESULTCOUNT':0}},
                      {'Table':[],'Table1':[{'RESULTCOUNT':'bad'}]}, {'Table':None}]:
            r, _ = self.run_search([value], ['Full Name'])
            self.assertEqual(c.public_status(r), 'Unable to Confirm')
            self.assertEqual(r.reason_code, 'PA_NAME_RESPONSE_INCOMPLETE')

    def test_real_transport_failure_still_source_unavailable_and_retryable(self):
        for failure in [urllib.error.URLError('timed out'), urllib.error.HTTPError('https://www.charities.pa.gov/',500,'error',{},None)]:
            r, fetch = self.run_search([failure])
            self.assertEqual(r.status, 'Site Not Reachable')
            self.assertEqual(r.reason_code, 'PA_INCOMPLETE_SEARCH')
            self.assertEqual(fetch.call_count, 1)

    def test_trial_retries_only_failed_query_without_restarting_completed_searches(self):
        empty = {'Table':[], 'Table1':[{'RESULTCOUNT':0}]}
        with patch.object(c, 'trial_identity', return_value={'origin':'isolated'}):
            r, fetch = self.run_search([empty, TimeoutError('source read timed out'), empty],
                                      ['Full Legal Name', 'Distinct Alias'])
        self.assertEqual(r.status, 'Not Registered')
        self.assertEqual([json.loads(call.kwargs['data'])['EntityName'] for call in fetch.call_args_list],
                         ['Full Legal Name', 'Distinct Alias', 'Distinct Alias'])
        self.assertEqual(len({call.args[1] for call in fetch.call_args_list}), 1)
        self.assertEqual(r._pa_api_attempts[-1]['transport_retries'], 1)
        self.assertTrue(r._pa_api_attempts[-1]['complete'])

    def test_trial_repeated_timeout_is_never_a_completed_negative(self):
        with patch.object(c, 'trial_identity', return_value={'origin':'isolated'}):
            r, fetch = self.run_search([TimeoutError('first'), TimeoutError('second')], ['Full Name'])
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(r.status, 'Site Not Reachable')
        self.assertFalse(r.success)

    def test_trial_http_rejection_is_not_retried(self):
        with patch.object(c, 'trial_identity', return_value={'origin':'isolated'}):
            r, fetch = self.run_search([urllib.error.HTTPError('https://www.charities.pa.gov/',403,'blocked',{},None)], ['Full Name'])
        self.assertEqual(fetch.call_count, 1)
        self.assertFalse(r.success)

    def test_deterministic_response_limit_does_not_repeat_entire_lookup(self):
        outcome = dict(status='Unable to Confirm', success=False, reason_code='PA_NAME_RESPONSE_INCOMPLETE')
        with patch.object(c,'run_state_lookup',return_value=outcome) as call:
            c.run_single_state_lookup_reliably(self.org.organization_name,self.org.ein,'PA')
        self.assertEqual(call.call_count, 1)

    def test_no_remaining_budget_is_not_completed_negative_or_network_failure(self):
        with patch.object(c.time,'monotonic',return_value=100) as timer:
            timer.side_effect=[100,121,121,121]
            r, request = self.run_search([])
        self.assertEqual(c.public_status(r), 'Unable to Confirm')
        self.assertEqual(request.call_count,0)

if __name__=='__main__': unittest.main(verbosity=2)
