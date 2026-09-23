"""Report-only controls: reconciliation, periods, calendar bounds and full evidence."""
import copy
import json
import sys
import unittest
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import charity_clarity_report as r
import registry_snapshot_server as cc
from pypdf import PdfReader

ASOF = datetime(2026, 9, 14, tzinfo=timezone.utc)
FIXTURE = json.loads((Path(__file__).parent / 'fixtures/report-cri-20260914.json').read_text())


def row(state='CO', status='Current', **extra):
    return dict(organization_name='Example Community Foundation', ein='01-2345678', state=state,
                status=status, checked_at_epoch=ASOF.timestamp(), comments='', **extra)


class IntelligenceTests(unittest.TestCase):
    def test_case_study_counts_reconcile(self):
        findings = r.report_findings(FIXTURE['results'])
        groups = dict(r.summary_groups(findings))
        self.assertEqual({k: len(v) for k, v in groups.items()}, {
            'Potentially overdue filings / lapses': 2, 'Closed / withdrawn / canceled': 2,
            'No registration found': 7, 'Upcoming filing': 7, 'Exempt': 4, 'Current': 8})
        self.assertEqual(sum(map(len, groups.values())), 30)
        insights = r.operational_insights(FIXTURE['results'])
        footprint = next(v for k, v in insights if 'footprint' in k)
        self.assertIn('23 states returned record-based results', footprint)
        self.assertIn('21 other records and 2 closed records', footprint)

    def test_every_known_status_partitioned_exactly_once(self):
        statuses = sorted(r.LOW | r.MODERATE | r.HIGH | r.INCOMPLETE)
        rows = [row(state, status) for state, status in zip(sorted(cc.SUPPORTED_STATES), statuses)]
        groups = r.summary_groups(r.report_findings(rows))
        states = [s for _, group in groups for s in group]
        self.assertEqual(Counter(states), Counter(x['state'] for x in rows))

    def test_calendar_boundary_groups(self):
        days = [-1, 0, 30, 31, 60, 61, 90, 91, 180, 181]
        values = [row(computed_due_date=(ASOF + timedelta(days=d)).strftime('%Y-%m-%d')) for d in days]
        expected = ['Overdue', '0-30 days', '0-30 days', '31-60 days', '31-60 days', '61-90 days', '61-90 days', '91-180 days', '91-180 days', 'Beyond 180 days']
        self.assertEqual([f['bucket'] for f in r.report_findings(values)], expected)

    def test_no_clock_substitution_for_missing_timestamp(self):
        value = row(computed_due_date='2026-10-15'); value['checked_at_epoch'] = None
        f = r.report_findings([value])[0]
        self.assertIsNone(f['days']); self.assertEqual(f['bucket'], 'Date unconfirmed')
        self.assertEqual(f['deadline']['effective'], date(2026, 10, 15))

    def test_calendar_ineligible_statuses_not_assigned_renewals(self):
        for status in (r.LOW | r.MODERATE | r.HIGH | r.INCOMPLETE) - r.CALENDAR:
            f = r.report_findings([row(status=status, computed_due_date='2026-10-15')])[0]
            self.assertIsNone(f['bucket'], status)

    def test_case_study_calendar_and_real_deadline_cluster(self):
        findings = r.report_findings(FIXTURE['results'])
        self.assertEqual(Counter(f['bucket'] for f in findings), {
            None: 13, 'Beyond 180 days': 8, 'Overdue': 2, '61-90 days': 4, '91-180 days': 3})
        cluster = next(i for i in r.insight_records(findings) if 'deadline cluster' in i['title'])
        self.assertIn('NH, OR, SC, VA', cluster['observed'])
        self.assertIn('Nov 15, 2026', cluster['title'])
        for f in findings:
            if f['state'] in ['NH', 'OR', 'SC', 'VA']:
                self.assertEqual(f['days'], 62)

    def test_close_but_different_dates_not_a_cluster(self):
        rows = [row(state, computed_due_date='2026-10-' + day) for state, day in [('CA', '15'), ('CO', '16'), ('FL', '17')]]
        self.assertFalse(any('cluster' in title for title, _ in r.operational_insights(rows)))

    def test_base_and_effective_extension_preserved(self):
        for state in ['MA', 'NY']:
            value = next(x for x in FIXTURE['results'] if x['state'] == state)
            d = r.deadline_details(value)
            self.assertEqual(d['base'], date(2026, 11, 15))
            self.assertEqual(d['effective'], date(2027, 5, 15))
            self.assertEqual(d['extended'], date(2027, 5, 15))

    def test_date_type_distinguishes_expiration_from_filing(self):
        values = {x['state']: r.deadline_details(x)['kind'] for x in FIXTURE['results']}
        self.assertEqual(values['VA'], 'Registration expiration')
        self.assertEqual(values['NH'], 'Filing / renewal deadline')
        self.assertEqual(r.deadline_details(row(computed_due_date='2026-10-15'))['kind'], 'Date type unconfirmed')

    def test_tax_year_2024_is_not_misread_as_fiscal_2024(self):
        findings = {f['state']: f for f in r.report_findings(FIXTURE['results'])}
        for state in ['MA', 'MN', 'NM', 'NY', 'OR']:
            self.assertEqual(findings[state]['filed_period'], date(2025, 6, 30))
        for state in ['HI', 'KY']:
            self.assertIsNone(findings[state]['filed_period'])
            self.assertEqual(findings[state]['year_label'], '2024')
        self.assertFalse(any('different filed' in title for title, _ in r.operational_insights(FIXTURE['results'])))

    def test_only_aligned_explicit_periods_can_be_outliers(self):
        values = []
        for state, period in [('MN', '6/30/2025'), ('OR', '6/30/2025'), ('NY', '6/30/2024'), ('HI', '12/31/2024')]:
            value = row(state); value['comments'] = 'The state registry shows the latest filed fiscal year ended ' + period + '.'
            values.append(value)
        insight = next(i for i in r.insight_records(r.report_findings(values)) if 'different filed' in i['title'])
        self.assertIn('NY shows Jun 30, 2024', insight['observed'])
        self.assertNotIn('HI', insight['observed'])
        self.assertIn('does not establish a missing filing', insight['unknown'])

    def test_next_period_submission_dates_and_ambiguous_periods_not_used(self):
        for comment in ['The next filing for the period ending 6/30/2025 is due 11/15/2025.',
                        'Submitted on 6/30/2025. Fiscal year end 6/30.',
                        'The latest filed fiscal year ended 6/30/2025. The latest filed fiscal year ended 6/30/2024.']:
            value = row(); value['comments'] = comment
            self.assertIsNone(r.filed_period(value))

    def test_incomplete_period_evidence_cannot_support_comparison(self):
        value = row(status='Needs Review', raw_status_text='Filed FYE: 6/30/2025')
        self.assertIsNone(r.report_findings([value])[0]['filed_period'])

    def test_incomplete_dates_never_become_not_registered(self):
        for status in r.INCOMPLETE:
            value = row(status=status, computed_due_date='2026-10-15')
            f = r.report_findings([value])[0]
            self.assertEqual(f['label'], status)
            self.assertIsNone(f['bucket'])

    def test_pending_remains_pending_and_no_record_obligation_unknown(self):
        self.assertEqual(r.report_findings([row(status='Pending')])[0]['label'], 'Pending')
        f = r.report_findings([row(status='Not Registered')])[0]
        self.assertEqual(f['label'], 'No registration found')
        self.assertEqual(f['obligation'], 'Unknown')
        self.assertEqual(f['status'], 'Not Registered')

    def test_closure_does_not_prescribe_automatic_reinstatement(self):
        value = row(status='Closed / Withdrawn / Canceled')
        action = r.action_items([value])[0]
        self.assertIn('Do not assume reinstatement is necessary', action[2])
        for phrase in ['closure date and reason', 'intentional', 'replacement', 'activity']:
            self.assertIn(phrase, r.verification_needed(value))

    def test_targeted_exemption_review_does_not_invent_category(self):
        insight = next(i for i in r.insight_records(r.report_findings(FIXTURE['results'])) if 'exemptions' in i['title'])
        self.assertIn('KS, LA, MI, ND, NJ, OH, OK first', insight['action'])
        self.assertNotIn('religious exemption', json.dumps(insight).lower())
        self.assertIn('name is not evidence of eligibility', insight['unknown'])

    def test_every_insight_has_observation_limit_and_action(self):
        for insight in r.insight_records(r.report_findings(FIXTURE['results'])):
            self.assertEqual(set(insight), {'title', 'observed', 'significance', 'unknown', 'action'})
            self.assertTrue(all(insight.values()))

    def test_pdf_preserves_all_case_study_qualifications_and_links(self):
        original = copy.deepcopy(FIXTURE)
        pdf = PdfReader(BytesIO(r.generate_report(FIXTURE, cc.SUPPORTED_STATES)))
        text = ' '.join(' '.join(p.extract_text() for p in pdf.pages).split())
        for phrase in ['Extension eligibility is inferred, not separately confirmed by the state.',
                       'An extension was not confirmed; an approved extension may change the due date.',
                       'no registration record could be reliably matched', 'State source date: 9/7/2026',
                       f'Report template {r.REPORT_VERSION}', 'Snapshot version(s): 2026.09.14.2-staging']:
            self.assertIn(phrase, text)
        for value in FIXTURE['results']:
            self.assertIn(' '.join(value['comments'].split()), text)
        links = {str(a.get_object()['/A']['/URI']) for p in pdf.pages for a in p.get('/Annots', []) if '/URI' in a.get_object().get('/A', {})}
        self.assertEqual(links, {x['source_url'] for x in FIXTURE['results'] if x['source_url']})
        for index, page in enumerate(pdf.pages, 1):
            self.assertIn(f'{index} / {len(pdf.pages)}', page.extract_text())
        self.assertLessEqual(len(pdf.pages), 18)
        self.assertEqual(FIXTURE, original)

    def test_maximum_length_evidence_splits_without_losing_final_qualification(self):
        value = row(raw_status_text='Evidence ' * 1000 + 'RAW_END', source_note='Context ' * 1000 + 'NOTE_END')
        value['comments'] = 'Filing detail ' * 700 + 'EXTENSION_ELIGIBILITY_UNCONFIRMED_END'
        pdf = PdfReader(BytesIO(r.generate_report({'results': [value]}, cc.SUPPORTED_STATES)))
        text = ' '.join(p.extract_text() for p in pdf.pages)
        for marker in ['RAW_END', 'NOTE_END', 'EXTENSION_ELIGIBILITY_UNCONFIRMED_END']:
            self.assertIn(marker, text)

    def test_current_with_past_date_is_flagged_without_reclassification(self):
        value = row(computed_due_date='2026-01-15')
        self.assertTrue(any('discrepancy' in t for t, _ in r.operational_insights([value])))
        self.assertEqual(value['status'], 'Current')


if __name__ == '__main__':
    unittest.main(verbosity=2)
