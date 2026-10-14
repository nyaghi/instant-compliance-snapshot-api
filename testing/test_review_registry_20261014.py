"""Public confirmation, institutional identity and reported source-shape controls.

All inputs are saved-source or synthetic fixtures. No live registry requests.
"""
import copy
import json
import os
import sys
import time
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock, patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c


class ReviewRegistryControls(unittest.TestCase):
    def setUp(self):
        self.token = c.REVIEWED_NAME_CONTEXT.set({})
        self.addCleanup(c.REVIEWED_NAME_CONTEXT.reset, self.token)
        for p in (patch.object(c.urllib.request, 'urlopen', side_effect=AssertionError('Unexpected live I/O')),
                  patch.object(c, 'log_event'), patch.object(c, 'APP_VERSION', 'test-staging'),
                  patch.object(c, 'NY_CONNECTOR_SIGNING_KEY', 'test-only-key-' * 8)):
            p.start(); self.addCleanup(p.stop)

    def test_reported_and_independent_clinic_hospital_are_not_automatic_matches(self):
        for name, other in [('LAHEY CLINIC, INC.', 'Lahey Clinic Hospital Inc.'),
                            ('River Clinic, Inc.', 'River Clinic Hospital Inc.')]:
            with self.subTest(name=name):
                score = c.score_candidate(name, '042704683', {'name': other})
                self.assertEqual(score['decision'], 'possible')
                self.assertEqual(c.ar_candidate_identity({'name': other}, name,
                    c.organization_match_target_variants(name, '042704683'), '042704683'), 'unconfirmed_scope')
                row = dict(name=other, identifier='EC-123', ein='', location='Burlington, MA')
                with patch.object(c, 'reconciled_registry_address', return_value={'decision': 'corroborated'}), \
                     patch.object(c, 'licensed_charity_foreign_ein', return_value={}):
                    self.assertEqual(c.licensed_charity_identity(c.checker.Organization(name, '042704683'),
                        row, 'AL', time.monotonic() + 5), 'possible')

    def test_matching_ein_alias_and_punctuation_keep_existing_positive_paths(self):
        name, other = 'LAHEY CLINIC, INC.', 'Lahey Clinic Hospital Inc.'
        self.assertEqual(c.score_candidate(name, '042704683', {'name': other, 'ein': '042704683'})['decision'], 'accepted')
        self.assertEqual(c.score_candidate(name, '042704683', {'name': other, 'ein': '042704686'})['decision'], 'rejected')
        self.assertEqual(c.score_candidate(name, '042704683', {'name': 'Lahey Clinic Inc'})['decision'], 'accepted')
        token = c.REVIEWED_NAME_CONTEXT.set({'042704683': (other,)})
        try:
            self.assertEqual(c.score_candidate(name, '042704683', {'name': other})['decision'], 'accepted')
        finally:
            c.REVIEWED_NAME_CONTEXT.reset(token)

    def test_institutional_foundation_is_not_promoted_when_hospital_is_reviewable(self):
        for name, ein in [('LAHEY CLINIC, INC.','042704683'),('River Clinic, Inc.','123456789')]:
            foundation=name.split(',')[0]+' Foundation'
            self.assertEqual(c.score_candidate(name,ein,{'name':foundation})['reason'],'REVIEW_INSTITUTIONAL_ENTITY')
            self.assertFalse(c.registry_name_is_safe_against_targets(foundation,
                c.organization_match_target_variants(name,ein),name,ein))
        self.assertFalse(c.institutional_entity_extension_requires_review('River Relief','River Relief Foundation','123456789'))
        rows=[{'ID':str(i),'RECORD_NUM':str(i),'TITLE':[name],'STATUS':'Active'} for i,name in
              enumerate(['River Clinic Foundation','River Clinic Hospital'],1)]
        detail={'DRAWER_DETAIL_LIST':[{'LABEL':'Status','VALUE':'Active'}]}
        result,_=self.nd(rows,[detail,detail])
        self.assertFalse(result.success)
        self.assertEqual({r['name'] for r in result._cc_identity_review['records']},
                         {'River Clinic Foundation','River Clinic Hospital'})

    def test_bare_inconclusive_is_not_a_negative_or_an_identity_prompt(self):
        result = c.confirmation_result_for_public(dict(status='Needs Review', success=False,
            comments='CharityClarity reports Needs Review.'))
        self.assertEqual(result['status'], 'Unable to Confirm')
        self.assertFalse(result['success']); self.assertFalse(result['confirmation_required'])
        self.assertNotIn('Needs Review', result['comments'])

    def test_settled_batch_transport_preserves_controls_and_other_state_result(self):
        from deployment import staging_workflows as workflow
        record = dict(ein='123456789', name='River Clinic', states=['AR', 'AL'], mode='standard')
        context = dict(records=[dict(name='River Clinic Hospital', identifier='1', ein='', location='',
            raw_status='Suspended', status='Suspended', url='https://registry.example/1',
            expiration='', initial='', _identity_outcome='possible')], search_complete=True)
        def job(state, status):
            return dict(phase='done', state=state, result=dict(ein='12-3456789', organization_name='River Clinic',
                app_version='fixture-worker', state=state, status=status, success=status=='Current', comments='Source evidence.'))
        pending, current = job('AR','Needs Review'), job('AL','Current')
        pending['result']['_worker_identity_review'] = context
        with patch.dict(os.environ, {'CE_STAGING_WORKFLOW_VERSION': 'fixture-worker'}):
            a = workflow.public_result(c, pending, record)
            b = workflow.public_result(c, current, record)
        self.assertEqual(a['status'], 'Unable to Confirm'); self.assertTrue(a['confirmation_required'])
        self.assertEqual(a['identity_review']['candidates'][0]['name'], 'River Clinic Hospital')
        self.assertEqual(b['status'], 'Current'); self.assertFalse(b['confirmation_required'])
        self.assertNotIn('_worker_identity_review', a)
        self.assertEqual(pending['result']['status'], 'Needs Review')  # durable source evidence retained

    def signed(self, complete=True):
        data = dict(organization_name='River Clinic', ein='12-3456789', state='AR',
                    status='Needs Review', success=False, comments='Confirm the retrieved identity.')
        c.attach_identity_review(data, {'records': [dict(name='River Clinic Hospital', identifier='fixture',
            ein='', url='https://registry.example/record', raw_status='Current', status='Current',
            expiration=None, initial=None, _identity_outcome='possible')], 'search_complete': complete})
        return c.confirmation_result_for_public(data)

    def decide(self, data, action):
        return c.resolve_identity_review({'token': data['identity_review']['token'], 'ein': data['ein'],
            'state': data['state'], 'candidate_id': data['identity_review']['candidates'][0]['id'],
            'action': action}, 'qa@example.test', 'fixture-device')

    def test_accept_reject_undo_and_incomplete_search_remain_source_bound(self):
        first = self.signed()
        self.assertTrue(first['confirmation_required'])
        accepted = self.decide(first, 'accept')
        self.assertEqual(accepted['status'], 'Current')
        self.assertEqual(self.decide(accepted, 'clear')['status'], 'Unable to Confirm')
        self.assertEqual(self.decide(first, 'reject')['status'], 'Not Registered')
        self.assertEqual(self.decide(self.signed(False), 'reject')['status'], 'Unable to Confirm')

    def test_address_display_reuses_only_same_ein_organization_evidence(self):
        record = dict(ein='123456789', address_role='organization', street='1 Main St', city='Boston',
                      state='MA', postal_code='02110', source_url='https://registry.example/record')
        sources = [{'source': 'CA', 'organization_records': [record, {**record, 'ein': '987654321'},
                    {**record, 'street': 'Agent office', 'address_role': 'registered_agent'}]},
                   {'source': 'IRS', 'filer_address': {**record, 'historical': True}}]
        addresses = c.discovered_organization_addresses('123456789', sources)
        self.assertEqual(len(addresses), 1)
        self.assertEqual(addresses[0]['street'], '1 Main St')
        self.assertEqual(len(addresses[0]['evidence']), 2)
        self.assertFalse(addresses[0]['historical'])
        self.assertEqual(addresses[0]['evidence'][0]['checked_date'], '')
        dated = c.discovered_organization_addresses('123456789', [{'source': 'CA',
            'retrieved_at': '2026-10-12T10:00:00Z', 'organization_records': [record]}])
        self.assertEqual(dated[0]['evidence'][0]['checked_date'], '2026-10-12')

    def test_kentucky_saved_duplicate_records_have_actionable_signed_choices(self):
        rows = [('13553', 'MS Gift Cures, Inc.', '2024', ''),
                ('14131', 'Morgan Stanley Global Impact Funding Trust, Inc. | DBA: MS Gift Cures, Inc.', '2024', '')]
        with patch.object(c, 'load_ky_snapshot_records', return_value=rows), \
             patch.object(c, 'downloadable_data_info', return_value={}):
            result = c.search_ky_strict_snapshot(c.checker.Organization('MS GIFT CURES, INC.', '833051191'))
        self.assertEqual({r['identifier'] for r in result._cc_identity_review['records']}, {'13553', '14131'})
        self.assertTrue(result._cc_identity_review['exclusive'])
        data = dict(organization_name='MS GIFT CURES, INC.', ein='83-3051191', state='KY',
                    status='Needs Review', success=False, comments=result.source_note)
        c.attach_identity_review(data, result._cc_identity_review)
        self.assertTrue(c.confirmation_result_for_public(data)['confirmation_required'])
        for identifier, name, _, _ in rows:
            token = c.USER_IDENTITY_CONTEXT.set({'state': 'KY', 'ein': '833051191',
                'accepted': {'identifier': identifier, 'name': name}})
            try:
                with patch.object(c, 'load_ky_snapshot_records', return_value=[(i,n,'',t) for i,n,y,t in rows]), \
                     patch.object(c, 'downloadable_data_info', return_value={}):
                    selected = c.search_ky_strict_snapshot(c.checker.Organization('MS GIFT CURES, INC.', '833051191'))
                self.assertEqual(selected.matched_registry_identifier, identifier)
                self.assertEqual(selected.matched_registry_name, name)
            finally:
                c.USER_IDENTITY_CONTEXT.reset(token)

    def nd(self, rows, details):
        page = MagicMock()
        responses = [{'rows': {str(i): r for i,r in enumerate(rows)}, 'template': []}, *details]
        def pending(*args, **kwargs):
            value = responses.pop(0)
            if isinstance(value, Exception): raise value
            context = MagicMock()
            context.__enter__.return_value = SimpleNamespace(value=SimpleNamespace(status=200, json=lambda: value))
            return context
        page.expect_response.side_effect = pending
        with patch.object(c, 'nd_search_queries', return_value=['River Clinic']):
            result = c.search_nd_completed(page, c.checker.Organization('River Clinic', '123456789'))
        return result, page

    def test_nd_specific_ambiguous_rows_get_verified_choices_and_partial_failure_stays_partial(self):
        row = lambda i: {'ID': str(i), 'RECORD_NUM': str(i), 'TITLE': ['River Clinic Hospital'], 'STATUS': 'Active'}
        detail = lambda status: {'DRAWER_DETAIL_LIST': [{'LABEL': 'Status', 'VALUE': status}]}
        result, page = self.nd([row(1),row(2)], [detail('Suspended'), detail('Revoked')])
        context = result._cc_identity_review
        self.assertTrue(context['search_complete']); self.assertEqual(page.expect_response.call_count, 3)
        self.assertEqual([r['status'] for r in context['records']], ['Suspended','Revoked'])
        data = dict(organization_name='River Clinic', ein='12-3456789', state='ND',
                    status='Needs Review', success=False, comments=result.source_note)
        c.attach_identity_review(data, context)
        self.assertEqual(self.decide(data, 'accept')['status'], 'Unable to Confirm')  # second choice still pending
        first = self.decide(data, 'reject')
        second = first['identity_review']['candidates'][1]['id']
        accepted = c.resolve_identity_review(dict(token=first['identity_review']['token'], ein=data['ein'], state='ND',
            candidate_id=second, action='accept'), 'qa@example.test', 'fixture-device')
        self.assertEqual(accepted['status'], 'Revoked')
        partial, _ = self.nd([row(1),row(2)], [detail('Suspended'), TimeoutError('fixture deadline')])
        self.assertFalse(partial._cc_identity_review['search_complete'])

    def nc(self, kind, status, identifier='', expiration=''):
        return c.nc_charity_record_evidence({'CSL Legal Name': 'Example Hospital', 'CSL Type': kind,
            'Status': status, 'License': identifier, 'Expiration Date': expiration,
            'profile_url': 'https://www.sosnc.gov/online_services/search/charities_profile/12345'})

    def test_numberless_charitable_organization_is_pending_not_parser_failure(self):
        row = self.nc('Charitable Organization', 'In-Process')
        self.assertEqual(row['status'], 'Pending'); self.assertTrue(row['unissued_application'])

    def test_ms_possible_record_gets_source_bound_controls_after_completed_search(self):
        name = 'Lahey Clinic Hospital, Inc.'
        def evidence(query):
            if query['operation'] == 'search':
                return dict(state='MS', query=query, complete=True, verification_pending=False, total=1,
                            rows=[dict(name=name, identifier='100035186', raw_status='Expired')])
            return dict(query=query, complete=True, source_url=c.MS_BROWSER_SOURCE,
                        fields={'Name': name, 'Registered Name': name, 'Filing Number': '100035186',
                                'Filing Status': 'Expired', 'Expiration Date': '1/1/2020'})
        with patch.object(c, 'ms_name_search_plan', return_value=['Lahey Clinic']):
            result = c.ms_browser_lookup(c.checker.Organization('LAHEY CLINIC, INC.', '042704683'), evidence)
        context = result._cc_identity_review
        self.assertTrue(context['search_complete'])
        self.assertEqual(context['records'][0]['identifier'], '100035186')
        data = dict(organization_name='LAHEY CLINIC, INC.', ein='04-2704683', state='MS',
                    status='Needs Review', success=False, comments=result.source_note)
        c.attach_identity_review(data, context)
        data = c.confirmation_result_for_public(data)
        self.assertEqual(self.decide(data, 'accept')['status'], 'Delinquent')
        self.assertEqual(self.decide(data, 'reject')['status'], 'Not Registered')

    def test_ms_review_detail_is_read_before_later_search_replaces_its_grid(self):
        current_rows = []
        calls = []
        row = dict(name='River Clinic Hospital', identifier='100001234', raw_status='Expired')
        def evidence(query):
            nonlocal current_rows
            calls.append(dict(query))
            if query['operation'] == 'search':
                current_rows = [row] if query['name'] == 'River Clinic' else []
                return dict(state='MS', query=query, complete=True, verification_pending=False,
                            rows=current_rows, total=len(current_rows))
            self.assertIn(row, current_rows, 'The public grid no longer contains this filing number')
            return dict(query=query, complete=True, source_url=c.MS_BROWSER_SOURCE,
                        fields={'Name': row['name'], 'Registered Name': row['name'],
                                'Filing Number': row['identifier'], 'Filing Status': 'Expired',
                                'Expiration Date': '1/1/2020'})
        with patch.object(c, 'ms_name_search_plan', return_value=['River Clinic', 'River Clinic Inc']):
            result = c.ms_browser_lookup(c.checker.Organization('River Clinic, Inc.', '123456789'), evidence)
        self.assertEqual([q['operation'] for q in calls], ['search', 'detail', 'search'])
        self.assertTrue(result._cc_identity_review['search_complete'])
        self.assertEqual(result._cc_identity_review['records'][0]['identifier'], row['identifier'])
        self.assertEqual([q['query']['operation'] for q in result.queries_attempted],
                         ['search', 'detail', 'search'])

    def test_ms_later_incomplete_search_cannot_become_a_completed_negative(self):
        row = dict(name='River Clinic Hospital', identifier='100001234', raw_status='Expired')
        def evidence(query):
            if query['operation'] == 'search':
                return dict(state='MS', query=query, complete=query['name'] == 'River Clinic',
                            verification_pending=False, rows=[row], total=1)
            return dict(query=query, complete=True, source_url=c.MS_BROWSER_SOURCE,
                        fields={'Name': row['name'], 'Registered Name': row['name'],
                                'Filing Number': row['identifier'], 'Filing Status': 'Expired',
                                'Expiration Date': '1/1/2020'})
        with patch.object(c, 'ms_name_search_plan', return_value=['River Clinic', 'River Clinic Inc']):
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                c.ms_browser_lookup(c.checker.Organization('River Clinic, Inc.', '123456789'), evidence)

    def test_ms_review_detail_bound_and_identity_validation_are_preserved(self):
        details = []
        def evidence(query):
            if query['operation'] == 'search':
                return dict(state='MS', query=query, complete=True, verification_pending=False, total=11,
                            rows=[dict(name='River Clinic Hospital', identifier=str(100001234+i),
                                       raw_status='Expired') for i in range(11)])
            details.append(query['identifier'])
            return dict(query=query, complete=True, source_url=c.MS_BROWSER_SOURCE,
                        fields={'Name': 'River Clinic Hospital', 'Registered Name': 'River Clinic Hospital',
                                'Filing Number': query['identifier'], 'Filing Status': 'Expired',
                                'Expiration Date': '1/1/2020'})
        with patch.object(c, 'ms_name_search_plan', return_value=['River Clinic']):
            result = c.ms_browser_lookup(c.checker.Organization('River Clinic, Inc.', '123456789'), evidence)
        self.assertEqual(len(details), 10)
        self.assertEqual(len(result._cc_identity_review['records']), 10)
        self.assertFalse(result._cc_identity_review['search_complete'])

    def test_denied_application_is_not_pending_or_an_issued_license(self):
        row = self.nc('In-Process', 'Denied')
        self.assertTrue(row['non_charity_scope'])
        self.assertNotEqual(row['status'], 'Pending')
        self.assertEqual(row['raw_status'], 'Denied')
        # A denied renewal of an already issued, dated SL record stays delinquent.
        self.assertEqual(self.nc('Charitable Organization', 'Denied', 'SL001234', '1/1/2024')['status'], 'Delinquent')

    def test_incomplete_unknown_card_cannot_become_negative(self):
        for kind, status in [('Charitable Organization', 'Current Active'), ('Unknown', 'In-Process')]:
            with self.assertRaises(ValueError): self.nc(kind, status)

    def test_hawaii_rate_limit_and_pdf_identity_failures_are_not_retried(self):
        source = '<a rel="/charity/attachments/irs/833051191/2024/return.pdf">IRSForm_990</a>'
        with patch.object(c, 'identity_fetch', side_effect=HTTPError('https://state.example', 429, 'limited', {}, None)) as fetch:
            with self.assertRaises(c.FilingPeriodReadIncomplete):
                c.hi_attachment_period(source, '833051191', 2024, time.monotonic() + 20)
        self.assertEqual(fetch.call_count, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
