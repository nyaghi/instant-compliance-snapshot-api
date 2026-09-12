"""Prevent a generic possessive token from becoming identity evidence."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class GenericPossessive(unittest.TestCase):
    def setUp(self):
        self.aliases=patch.object(c,'known_names_for_ein',return_value=[]);self.aliases.start();self.addCleanup(self.aliases.stop)

    def test_apostrophe_spellings_do_not_confirm_unrelated_organizations(self):
        for possessive in ['Children’s',"Children's",'Childrens']:
            expected=f'First Responders {possessive} Foundation'
            candidate="Children's Hospital Foundation"
            with self.subTest(possessive=possessive):
                self.assertFalse(c.registry_name_is_safe_for_org(candidate,expected,'05-0536854'))
                self.assertFalse(c.registry_name_is_safe_against_targets(candidate,c.organization_match_target_variants(expected),expected))
                self.assertEqual(c.score_candidate(expected,'05-0536854',{'name':candidate})['decision'],'rejected')

    def test_complete_punctuation_equivalent_names_still_match(self):
        for expected,candidate in [
            ("Children’s Hospital Foundation","Children's Hospital Foundation"),
            ("First Responders Children’s Foundation","First Responders Childrens Foundation"),
            ("Children’s Miracle Network","Children's Miracle Network"),
            ("American Farrier’s Association Foundation Inc.","American Farrier's Association Foundation, Inc."),
            ('Aeon','Aeon (dba Aeon Homes)')]:
            with self.subTest(expected=expected):self.assertTrue(c.registry_name_is_safe_for_org(candidate,expected))

    def test_exact_ein_precedence_and_conflicting_ein_rejection(self):
        expected='First Responders Children’s Foundation';candidate="Children's Hospital Foundation"
        self.assertEqual(c.score_candidate(expected,'05-0536854',{'name':candidate,'ein':'05-0536854'})['decision'],'accepted')
        self.assertEqual(c.score_candidate(expected,'05-0536854',{'name':expected,'ein':'12-3456789'})['reason'],'REJECT_DIFFERENT_EIN')

    def test_nh_does_not_use_unrelated_childrens_record(self):
        record={'registry_id':'12184','registry_name':"Children's Hospital Foundation",'status_code':'G','due_date':c.date(2026,11,14),'due_raw':'11/14/2026','body':''}
        with patch.object(c,'nh_live_pdf_records',return_value=([record],'fixture')):
            result=c.search_nh_live_pdf(c.checker.Organization('First Responders Children’s Foundation','05-0536854'))
            self.assertEqual(result.status,c.checker.STATUS_NOT_REGISTERED);self.assertEqual(result.matched_registry_name,'')

    def test_nh_exact_name_retains_its_status(self):
        record={'registry_id':'12184','registry_name':"Children's Hospital Foundation",'status_code':'G','due_date':c.date(2026,11,14),'due_raw':'11/14/2026','body':''}
        with patch.object(c,'nh_live_pdf_records',return_value=([record],'fixture')):
            result=c.search_nh_live_pdf(c.checker.Organization('Children’s Hospital Foundation',''))
            self.assertEqual(result.status,c.status_from_calendar_date(record['due_date']));self.assertEqual(result.matched_registry_identifier,'12184')

if __name__=='__main__':unittest.main(verbosity=2)
