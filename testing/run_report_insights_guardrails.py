"""Report priority boundaries, conservative insights, and snapshot fidelity."""
import copy, sys, unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import charity_clarity_report as r
import registry_snapshot_server as c
from pypdf import PdfReader

ASOF=datetime(2026,9,14,tzinfo=timezone.utc)
def row(state='CO',status='Current',days=None):
    value=dict(organization_name='Example Community Foundation',ein='01-2345678',state=state,status=status,
               comments='Registry status recorded.',checked_at_epoch=ASOF.timestamp(),app_version=c.APP_VERSION,
               source_url='https://example.org/registry',raw_status_text='',source_note='')
    if days is not None:value['computed_due_date']=(ASOF+timedelta(days=days)).strftime('%m/%d/%Y')
    return value

class InsightsTests(unittest.TestCase):
    def test_60_day_boundary_inclusive_even_current(self):
        rows=[row('CO',days=61),row('CT',days=60),row('CA',days=0),row('FL',days=-1),row('MI',days=1)]
        urgent=next(states for title,states,_ in r.action_items(rows) if 'within 60' in title)
        self.assertEqual([s.split(':')[0] for s in urgent],['CA','MI','CT'])
        self.assertIn('today',urgent[0])

    def test_incomplete_and_exempt_are_not_assigned_a_renewal(self):
        for status in ['Exempt','Unable to Confirm','Not Registered','Pending','Closed / Withdrawn / Canceled']:
            self.assertFalse(any('within 60' in title for title,_,_ in r.action_items([row(status=status,days=10)])))

    def test_effective_extension_and_computed_date_precedence(self):
        value=row(status='Upcoming Filing')
        value['comments']="The next annual filing's base due date is 5/15/2026; Maryland's automatic extension runs through 10/15/2026."
        self.assertEqual(str(r.snapshot_due_date(value)),'2026-10-15')
        value['computed_due_date']='11/15/2026';self.assertEqual(str(r.snapshot_due_date(value)),'2026-11-15')
        del value['computed_due_date'];value['comments']='The base due date is 5/15/2026; extension qualification remains unclear.'
        self.assertIsNone(r.snapshot_due_date(value))

    def test_fiscal_year_and_download_dates_never_become_deadlines(self):
        value=row();value['comments']='Fiscal year ended 10/15/2026. Data freshness note: downloaded 10/15/2026.'
        self.assertIsNone(r.snapshot_due_date(value))
        value['comments']='Expiration date: 10/15/2026. Renewal date: 11/15/2026.'
        self.assertIsNone(r.snapshot_due_date(value))

    def test_existing_interpreted_comment_formats(self):
        for body in ['The state registry shows an expiration date of 10/15/2026.',
                     'Calculated registration expiration: 10/15/2026 (certificate unavailable; not certificate-confirmed).',
                     'The next filing for the period ending 12/31/2025 is due 10/15/2026.',
                     'Certificate expires 10/15/2026.',
                     'The state registry shows an expiration date (including any automatic extension shown) of 10/15/2026.']:
            value=row();value['comments']=body
            self.assertEqual(str(r.snapshot_due_date(value)),'2026-10-15',body)

    def test_national_threshold_uses_records_not_checked_count(self):
        states=sorted(c.SUPPORTED_STATES)
        for count,expected in [(15,False),(16,True)]:
            rows=[row(s,'Current' if i<count else 'Not Registered') for i,s in enumerate(states)]
            self.assertEqual(any('footprint' in title for title,_ in r.operational_insights(rows)),expected)
        rows=[row(s,'Unable to Confirm') for s in states]
        self.assertFalse(any('footprint' in title for title,_ in r.operational_insights(rows)))

    def test_exemption_is_only_an_opportunity_and_pending_is_actionable(self):
        insights=' '.join(detail for _,detail in r.operational_insights([row('CO','Exempt'),row('FL','Pending'),row('AR','Not Registered')]))
        self.assertIn('does not establish eligibility elsewhere',insights)
        self.assertIn('Contact the state',insights)
        self.assertIn('AR',insights)
        actions=r.action_items([row('WV','Closed / Withdrawn / Canceled'),row('CO','Suspended'),row('MI',days=10)])
        self.assertIn('suspended',actions[0][0]);self.assertEqual(actions[0][1],['CO'])
        self.assertEqual(next(states for title,states,_ in actions if 'closed' in title),['WV'])
        self.assertIn('within 60',actions[1][0])

    def test_pdf_insights_and_original_snapshot_preserved(self):
        values=[row(s,'Current' if i<18 else 'Exempt' if i==18 else 'Pending' if i==19 else 'Not Registered',days=30 if i<4 else None) for i,s in enumerate(sorted(c.SUPPORTED_STATES))]
        original=copy.deepcopy(values)
        reader=PdfReader(BytesIO(r.generate_report({'results':values},c.SUPPORTED_STATES)))
        text=' '.join(p.extract_text() for p in reader.pages)
        self.assertIn('Operational Insights',text);self.assertIn('Renewals due within 60 days',text)
        self.assertNotIn('Downloadable data freshness',text);self.assertEqual(values,original)
        self.assertIn('not legal or tax advice',text)
        for index,page in enumerate(reader.pages,1):self.assertIn(f'{index} / {len(reader.pages)}',page.extract_text())

if __name__=='__main__':unittest.main(verbosity=2)
