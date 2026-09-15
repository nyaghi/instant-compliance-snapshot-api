"""Reported acronym failures, identity boundaries, KS selection, OR live evidence."""
import sys, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from datetime import date
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

NAME = 'End Violence Against Women International'
MIDDLE = 'End Violence Against Women (EVAW) International'
TRAILING = NAME + ' (EVAWI)'
EIN = '753095110'

class AcronymTests(unittest.TestCase):
    def test_verified_acronyms_at_each_decision_gate(self):
        for candidate in [MIDDLE, TRAILING, MIDDLE.upper(), NAME+' [EVAWI]', MIDDLE+', Inc.']:
            for first, second in [(NAME,candidate),(candidate,NAME)]:
                with self.subTest(first=first, second=second):
                    self.assertTrue(c.redundant_bracket_acronym_match(first,second))
                    self.assertTrue(c.registry_name_is_safe_for_org(second,first))
                    self.assertGreaterEqual(c.target_name_score(second,[first]),950)
                    self.assertEqual(c.score_candidate(first,EIN,{'name':second})['decision'],'accepted')

    def test_exact_ein_wins_and_conflicting_ein_rejects(self):
        self.assertEqual(c.score_candidate(NAME,EIN,{'name':MIDDLE,'ein':'75-3095110'})['reason'],'MATCH_EIN_EXACT')
        self.assertEqual(c.score_candidate(NAME,EIN,{'name':MIDDLE,'ein':'999999999'})['reason'],'REJECT_DIFFERENT_EIN')

    def test_nonredundant_and_substantive_words_stay(self):
        candidates=[MIDDLE+' Foundation',MIDDLE+' - Ohio',NAME+' (Chapter)',
                    NAME+' (OTHER)',NAME+' (evawi)',NAME+' (NYC)',
                    'End Violence Against Women (Ohio) International',
                    'End Violence Against Women (EVAW) National',
                    'End Violence Against Women International Action (EVAWIA)']
        for candidate in candidates:
            self.assertFalse(c.redundant_bracket_acronym_match(NAME,candidate),candidate)

    def test_previous_false_matches_cannot_use_new_equivalence(self):
        pairs=[('Air Force Academy Foundation','Air Force Academy Athletic Corporation'),
               ('Autism Research Institute','Organization for Autism Research'),
               ('Beth Israel Deaconess Hospital - Milton','Beth Israel Deaconess Hospital - Needham'),
               ('Call to Action','A Call to Action'),
               ('Children’s Health Care Foundation','Children’s Healthcare of Atlanta')]
        for a,b in pairs:self.assertFalse(c.redundant_bracket_acronym_match(a,b))

    def test_ordinary_exact_names_keep_original_priority(self):
        self.assertFalse(c.redundant_bracket_acronym_match(NAME,NAME))
        self.assertEqual(c.target_name_score(NAME,[NAME]),1000)
        self.assertGreater(c.target_name_score(NAME,[NAME]),c.target_name_score(MIDDLE,[NAME]))
        self.assertFalse(c.redundant_bracket_acronym_match('A B (AB)','A B'))

    def ks(self,records):
        m=c.load_ks_weekly_checker()
        with (patch.object(m,'load_live_records',return_value=(records,'https://example.test/ks.xlsx','https://example.test/ks')),
              patch.object(m,'make_snapshot_image',return_value=''),patch.object(c,'weekly_asset',return_value=Path('verified'))):
            return c._search_snapshot_or_embedded_state_once(c.checker.Organization(NAME,EIN),'KS')

    def row(self,identifier='25-007849',status='REGISTERED',ein='',name=TRAILING):
        return SimpleNamespace(contact_number=identifier,name=name,status=status,ein=ein,
                               expire_date=date(2026,6,30),city='',state='',zip_code='')

    def test_kansas_missing_ein_verified_acronym_recovers(self):
        r=self.ks([self.row()]);self.assertEqual(c.public_status(r),'Delinquent')
        self.assertEqual(r.matched_registry_identifier,'25-007849')

    def test_kansas_conflicting_ein_never_recovers_by_acronym(self):
        r=self.ks([self.row(ein='999999999')]);self.assertEqual(c.public_status(r),'Not Registered')

    def test_kansas_equivalent_active_row_preferred_in_both_orders(self):
        records=[self.row('old','CLOSED'),self.row('active')]
        for order in [records,list(reversed(records))]:
            self.assertEqual(self.ks(order).matched_registry_identifier,'active')

    def test_kansas_substantive_suffix_never_recovers(self):
        self.assertEqual(c.public_status(self.ks([self.row(name=TRAILING+' Foundation')])),'Not Registered')

    def test_kansas_changed_identifier_is_not_a_negative(self):
        m=c.load_ks_weekly_checker()
        original=m.find_best_match
        calls=[]
        def changing(records,name):
            calls.append(name)
            return None if len(calls)==1 else self.row(identifier='different')
        with patch.object(m,'find_best_match',side_effect=changing):
            self.assertEqual(c.public_status(self.ks([self.row()])),'Unable to Confirm')

    def oregon(self,ein=EIN,reports='Reports'):
        m=c.state_extension_module('OR');page=Mock()
        page.locator.return_value.is_visible.return_value=True
        page.locator.return_value.inner_text.return_value=reports
        external=SimpleNamespace(organization_name=NAME,ein=EIN,state='OR',status='Delinquent',source_url='https://justice.oregon.gov/Charities/Charity/details?charityID=80938',
            raw_status_text='Status: Registered | Latest Report: N/A | Fiscal Year End: N/A',
            source_note='Oregon detail page loaded, but no annual report period was visible.',
            success=True,error='',matched_registry_name=MIDDLE)
        body=f'{MIDDLE}\nMailing Address:\n1 Main Street\nFederal EIN: {ein}\nReports'
        with patch.object(m,'search_or',return_value=external),patch.object(c,'registry_page_body',return_value=body),patch.object(c,'build_search_queries',return_value=[NAME]):
            return c.search_bundled_extension_state(page,c.checker.Organization(NAME,EIN),'OR')

    def test_oregon_live_empty_reports_comment_and_freshness(self):
        r=self.oregon();self.assertEqual(c.public_status(r),'Delinquent')
        text=c.comments_for_result(r,'','Delinquent')
        self.assertIn('live registry',text);self.assertIn('infers Delinquent',text)
        self.assertNotIn('Scheduled OR dataset',text);self.assertNotIn('no explicit state delinquency supporting',text)

    def test_oregon_conflicting_detail_ein_rejected_despite_strong_name(self):
        self.assertEqual(c.public_status(self.oregon(ein='999999999')),'Not Registered')

    def test_oregon_nonempty_reports_does_not_claim_empty(self):
        r=self.oregon(reports='Reports\n2025 Annual Report')
        self.assertNotEqual(getattr(r,'status_reason',''),'OR_LIVE_EMPTY_REPORTS_INFERRED_DELINQUENT')

if __name__=='__main__': unittest.main()
