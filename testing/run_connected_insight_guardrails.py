"""Connected assessment/report controls; fixtures are explicitly fictional."""
import copy
import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import charity_clarity_report as report
import registry_snapshot_server as cc
from pypdf import PdfReader

FIXTURE = Path(__file__).parent / 'fixtures/connected-hospital/report-payload.json'


class ConnectedInsightTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.rows = report.validate_results(self.payload, set(cc.SUPPORTED_STATES))
        self.assessment = report.validate_head_start(self.payload['head_start'])

    def finding(self, state, status=None, requirement=None, **flags):
        rows = copy.deepcopy(self.rows)
        if status is not None:
            for r in rows:
                if r['state'] == state:
                    r['status'] = status
        h = copy.deepcopy(self.assessment)
        for r in h['requirements']:
            if r['code'] == state:
                if requirement is not None:
                    r['status'] = requirement
                r.update(flags)
        return next(r for r in report.reconcile_head_start(rows, h) if r['state'] == state)

    def test_supported_hawaii_with_current_registration_is_opportunity_not_approved(self):
        f = self.finding('HI')
        self.assertEqual(f['finding'], 'Exemption opportunity')
        self.assertIn('approval', f['action'])
        self.assertIn('Keep existing obligations current', f['action'])

    def test_separate_wa_trust_duty_remains_registration_gap(self):
        f = self.finding('WA')
        self.assertEqual(f['head_start']['status'], 'required')
        self.assertEqual(f['finding'], 'Registration gap indicated')
        self.assertEqual(f['priority'], 1)
        self.assertIn('recent submission', f['action'])

    def test_incomplete_search_is_never_a_negative_or_registration_gap(self):
        for status in report.INCOMPLETE:
            f = self.finding('WA', status)
            self.assertEqual(f['finding'], 'Registration status unresolved')
            self.assertNotIn('complete registration', f['action'])

    def test_unchecked_required_state_never_becomes_unregistered(self):
        rows = [r for r in self.rows if r['state'] != 'WA']
        f = next(f for f in report.reconcile_head_start(rows, self.assessment) if f['state'] == 'WA')
        self.assertEqual(f['aurora_status'], 'Not checked')
        self.assertEqual(f['finding'], 'Registration status not checked')

    def test_supported_claim_without_record_requires_procedure_review_not_gap(self):
        self.assertEqual(self.finding('CT')['finding'], 'Exemption filing or approval to confirm')

    def test_optional_confirmation_not_replaced_by_required_approval(self):
        f = self.finding('CA')
        self.assertEqual(f['finding'], 'Exemption opportunity')
        self.assertIn('available', f['action'])
        self.assertNotIn('obtain the Attorney General', f['action'])

    def test_outside_state_record_prompts_context_not_withdrawal(self):
        f = self.finding('RI')
        self.assertEqual(f['finding'], 'Review registration context')
        self.assertNotIn('withdraw', f['action'].lower())

    def test_outside_state_without_record_does_not_create_a_filing_task(self):
        f = self.finding('RI', 'Not Registered')
        self.assertEqual(f['priority'], 4)
        self.assertNotIn('registration gap', f['finding'].lower())

    def test_adverse_registration_cannot_be_cleared_by_possible_exemption(self):
        f = self.finding('HI', 'Delinquent')
        self.assertEqual(f['finding'], 'Existing registration needs attention')
        self.assertEqual(f['priority'], 1)

    def test_recorded_exemption_with_required_trust_duty_needs_scope_review(self):
        f = self.finding('WA', 'Exempt')
        self.assertEqual(f['finding'], 'Requirement and recorded exemption differ')

    def test_missing_eligibility_does_not_support_an_approval_application(self):
        f = self.finding('HI', requirement='review', exemption_evidence=None, possible_exemption=True, approvalRequired=False)
        self.assertEqual(f['finding'], 'Exemption eligibility to confirm')
        self.assertIn('missing eligibility', f['action'])

    def test_discretionary_waiver_is_not_supported_eligibility(self):
        f = self.finding('HI', discretionaryRequest=True, exemption_evidence=None)
        self.assertEqual(f['finding'], 'Discretionary waiver opportunity')

    def test_identity_binding_and_all_51_states_are_required(self):
        with self.assertRaises(ValueError):
            report.validate_head_start(self.assessment, ('Different entity', self.assessment['ein']))
        with self.assertRaises(ValueError):
            report.validate_head_start(self.assessment, (self.assessment['organization_name'], '999999999'))
        h = copy.deepcopy(self.assessment); h['requirements'].pop()
        with self.assertRaises(ValueError):
            report.validate_head_start(h)
        h = copy.deepcopy(self.assessment); h['requirements'][1]['code'] = h['requirements'][0]['code']
        with self.assertRaises(ValueError):
            report.validate_head_start(h)

    def test_profile_cannot_be_non_501c3_or_missing_facts_declared_confirmed(self):
        h = copy.deepcopy(self.assessment); h['profile']['taxStatus'] = '501c4'
        with self.assertRaises(ValueError):
            report.validate_head_start(h)
        h = copy.deepcopy(self.assessment); h['requirements'][0].update(status='review', exemption_evidence='answers')
        with self.assertRaises(ValueError):
            report.validate_head_start(h)

    def test_reconciliation_is_immutable_and_priorities_are_sorted(self):
        before = copy.deepcopy((self.rows, self.assessment))
        joined = report.reconcile_head_start(self.rows, self.assessment)
        self.assertEqual(len(joined), 51)
        self.assertEqual([f['priority'] for f in joined], sorted(f['priority'] for f in joined))
        self.assertEqual((self.rows, self.assessment), before)

    def test_report_has_four_sections_preserves_evidence_and_sample_label(self):
        before = copy.deepcopy(self.payload)
        content = report.generate_report(self.payload, cc.SUPPORTED_STATES)
        pages = PdfReader(BytesIO(content)).pages
        body = ' '.join(' '.join((p.extract_text() or '').split()) for p in pages)
        titles = ['Executive summary', 'Key findings', 'Prioritized action items', 'Detailed state review']
        self.assertEqual([body.index(t) for t in titles], sorted(body.index(t) for t in titles))
        self.assertIn('Workload forecast', body)
        self.assertIn('Registration gap indicated', body)
        self.assertIn('Exemption opportunity', body)
        for row in self.rows:
            self.assertIn(row['comments'], body)
            self.assertIn(row['source_note'], body)
        for i,p in enumerate(pages,1):
            text = ' '.join((p.extract_text() or '').split())
            self.assertIn('Illustrative example', text)
            self.assertIn(f'{i} / {len(pages)}', text)
        self.assertEqual(self.payload, before)

    def test_executive_cards_count_real_findings_not_all_required_states(self):
        joined = report.reconcile_head_start(self.rows, self.assessment)
        metrics = {m['label']: m['states'] for m in report.executive_metrics(joined)}
        self.assertEqual(metrics['Registration gaps indicated'], ['WA'])
        self.assertEqual(set(metrics['Potential exemption opportunities']), {'HI','CA','CO','PA'})
        self.assertEqual(metrics['Potential withdrawal reviews'], ['RI'])
        self.assertEqual(metrics['Upcoming filings'], ['PA'])
        self.assertEqual(metrics['Delinquencies'], [])
        self.assertIn('NY', metrics['Unresolved status checks'])
        # An incomplete or exempt record never becomes a withdrawal recommendation.
        for status in ['Needs Review', 'Exempt', 'Pending', 'Closed / Withdrawn / Canceled']:
            altered = [self.finding('RI', status=status)]
            self.assertEqual(report.executive_metrics(altered)[2]['states'], [])
        self.assertEqual(report.executive_metrics([self.finding('HI', status='Delinquent')])[3]['states'], ['HI'])

    def test_unknown_requirement_is_not_a_withdrawal_opportunity(self):
        f=self.finding('HI', requirement='review', possible_exemption=False, exemption_evidence=None, approvalRequired=False)
        self.assertEqual(report.executive_metrics([f])[2]['states'], [])

    def test_pending_registration_cannot_be_presented_as_requirement_satisfied(self):
        f=self.finding('WA', status='Pending')
        self.assertEqual(f['finding'],'Registration pending')
        self.assertEqual(f['priority'],2)
        self.assertIn('not an approved current registration',f['why'])

    def test_compliance_matrix_is_exclusive_and_keeps_uncertain_evidence_out_of_clear_blocks(self):
        combined = report.reconcile_head_start(self.rows, self.assessment)
        blocks, unchecked = report.compliance_matrix(combined)
        all_states = [state for states in blocks.values() for state in states]
        self.assertEqual(len(all_states), len(self.rows))
        self.assertEqual(len(set(all_states)), len(all_states))
        self.assertEqual(unchecked, 51 - len(self.rows))
        for status, expected in [
            ('Current', 'On track / deadline approaching'),
            ('Upcoming Filing', 'On track / deadline approaching'),
            ('Not Registered', 'Action needed'),
            ('Unable to Confirm', 'Needs confirmation'),
            ('Exempt', 'Needs confirmation'),
        ]:
            blocks, _ = report.compliance_matrix([self.finding('WA', status=status)])
            self.assertEqual(blocks[expected], ['WA'])
        blocks, _ = report.compliance_matrix([self.finding('HI', status='Exempt')])
        self.assertEqual(blocks['No registration needed'], ['HI'])
        recorded = self.finding('HI', status='Exempt', exemption_evidence=None)
        self.assertEqual(recorded['finding'], 'Exemption recorded')
        self.assertNotIn('application', recorded['action'].lower())
        blocks, _ = report.compliance_matrix([recorded])
        self.assertEqual(blocks['No registration needed'], ['HI'])

    def test_explicit_failed_lookup_can_never_create_a_registration_gap(self):
        payload=copy.deepcopy(self.payload)
        row=next(r for r in payload['results'] if r['state']=='WA')
        row.update(success=False,error='Registry verification could not be completed.')
        rows=report.validate_results(payload,set(cc.SUPPORTED_STATES))
        normalized=next(r for r in rows if r['state']=='WA')
        self.assertEqual(normalized['status'],'Unable to Confirm')
        self.assertEqual(normalized['returned_status'],'Not Registered')
        joined=report.reconcile_head_start(rows,self.assessment)
        self.assertEqual(next(f for f in joined if f['state']=='WA')['finding'],'Registration status unresolved')
        self.assertEqual(report.executive_metrics(joined)[1]['states'],[])
        self.assertEqual(row['status'],'Not Registered','Source evidence must not be mutated')

    def test_profile_preserves_real_intake_numeric_strings_and_readable_types(self):
        profile={'type':'university','fiscalActual':'100000000','online':'no','onlineReach':'public'}
        self.assertEqual(report.profile_summary(profile),('College / university','$100,000,000','No online donation requests'))
        self.assertEqual(profile['fiscalActual'],'100000000')
        for value in [None,'',True,'unknown','NaN']:
            self.assertEqual(report.profile_summary({**profile,'fiscalActual':value})[1],'Not supplied')
        self.assertEqual(report.profile_summary({**profile,'fiscalActual':'250000.25'})[1],'$250,000.25')

    def test_handoff_endpoint_requires_existing_auth_owner_binding_and_immutable_snapshot(self):
        server = ThreadingHTTPServer(('127.0.0.1',0),cc.RegistrySnapshotHandler)
        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        url = f'http://127.0.0.1:{server.server_port}/api/head-start'
        def request(payload):
            return urllib.request.urlopen(urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}))
        auth = {'email':'connected-preview@'+cc.EXEMPT_EMAIL_DOMAIN,'admin_passcode':cc.ADMIN_PASSCODE}
        try:
            with tempfile.TemporaryDirectory() as directory, patch.object(cc,'ARTIFACTS_DIR',Path(directory)), patch.object(cc,'run_state_lookups_parallel',side_effect=AssertionError('Handoffs must not run registry searches')):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    request({'action':'save','head_start':self.assessment})
                self.assertEqual(error.exception.code,403)
                with request({**auth,'action':'save','head_start':self.assessment}) as response:
                    self.assertEqual(response.status,200)
                with request({**auth,'action':'load','assessment_id':self.assessment['assessment_id']}) as response:
                    self.assertEqual(json.load(response)['head_start']['ein'],self.assessment['ein'])
                with self.assertRaises(urllib.error.HTTPError) as error:
                    request({**auth,'email':'other-preview@'+cc.EXEMPT_EMAIL_DOMAIN,'action':'load','assessment_id':self.assessment['assessment_id']})
                self.assertEqual(error.exception.code,404)
                altered = copy.deepcopy(self.assessment); altered['profile']['fiscalActual']=1
                with self.assertRaises(urllib.error.HTTPError) as error:
                    request({**auth,'action':'save','head_start':altered})
                self.assertEqual(error.exception.code,400)
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__ == '__main__':
    unittest.main(verbosity=2)
