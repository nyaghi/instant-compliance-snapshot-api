"""Real KY alias candidate replay and safe early-elimination boundary."""
import json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
F=json.loads((Path(__file__).parent/'fixtures/ky-reviewed-alias-candidates.json').read_text(encoding='utf-8'))

class KentuckyReviewedCandidateTests(unittest.TestCase):
    def setUp(self):
        self.token=c.REVIEWED_NAME_CONTEXT.set({c.canonical_ein_digits(F['ein']):tuple(F['alternate_names'])})
        self.org=c.checker.Organization(F['organization'],F['ein'])
        # Filing dates are tested separately. Empty labels isolate identity selection.
        self.rows=[(rid,name,'',text) for rid,name,year,text in F['records']]
    def tearDown(self):c.REVIEWED_NAME_CONTEXT.reset(self.token)
    def test_official_reviewed_alias_survives_rejected_generic_candidate(self):
        with patch.object(c,'load_ky_snapshot_records',return_value=self.rows):
            result=c.search_snapshot_or_embedded_state(self.org,'KY')
        self.assertEqual(result.matched_registry_identifier,'4223')
        self.assertEqual(result.matched_registry_name,'NLEAFCF DBA FIRST RESPONDERS')
        self.assertEqual(c.public_status(result),'Current')
    def test_verified_registration_with_unreadable_period_applies_disclosed_rule(self):
        org = c.checker.Organization("Example Health Foundation", "123456789")
        rows = [("123", "EXAMPLE HEALTH FOUNDATION", "2025", "")]
        for observed_ein in ("123456789", "987654321"):
            with self.subTest(ein=observed_ein), patch.object(c, "load_ky_snapshot_records", return_value=rows), patch.object(
                    c, "ky_filed_period_evidence", return_value={
                        "ein": observed_ein, "period_unconfirmed": True,
                        "period_read_failure": "The filing could not be read."
                    }):
                result = c.search_ky_strict_snapshot(org)
                self.assertEqual(result.matched_registry_identifier, "123")
                self.assertEqual(c.true_status_from_body(result, ""), "Delinquent" if observed_ein == org.ein else "Unable to Confirm")
                if observed_ein == org.ein:
                    self.assertIn("No overdue date was established", c.comments_for_result(result, "", "Delinquent"))

    def test_generated_children_fragment_cannot_win_the_inner_selector(self):
        with patch.object(c,'load_ky_snapshot_records',return_value=[r for r in self.rows if r[0]=='9894']):
            result=c.search_ky_strict_snapshot(self.org)
        self.assertEqual(c.public_status(result),'Not Registered')
        self.assertFalse(getattr(result,'matched_registry_identifier',''))
    def test_memorial_fund_and_unrelated_first_responder_entities_are_rejected(self):
        with patch.object(c,'load_ky_snapshot_records',return_value=[r for r in self.rows if r[0] in {'721','17945','18395'}]):
            result=c.search_snapshot_or_embedded_state(self.org,'KY')
        self.assertEqual(c.public_status(result),'Not Registered')
    def test_subthreshold_candidate_does_not_run_expensive_ranking(self):
        with patch.object(c,'load_ky_snapshot_records',return_value=[('1','NLEAFCF','','')]),patch.object(c,'ky_strict_name_score',return_value=699),patch.object(c,'target_name_score',side_effect=AssertionError('A score below the existing 700 acceptance floor cannot win')):
            result=c.search_ky_strict_snapshot(self.org)
        self.assertEqual(c.public_status(result),'Not Registered')
    def test_same_confirmed_alias_on_two_ids_remains_ambiguous(self):
        rows=[('4223','NLEAFCF DBA FIRST RESPONDERS','',''),('99999','NLEAFCF DBA FIRST RESPONDERS','','')]
        with patch.object(c,'load_ky_snapshot_records',return_value=rows):
            result=c.search_snapshot_or_embedded_state(self.org,'KY')
        self.assertEqual(c.public_status(result),'Needs Review')
    def test_dba_marker_does_not_validate_an_unrelated_name(self):
        with patch.object(c,'load_ky_snapshot_records',return_value=[('99999','UNRELATED GROUP DBA FIRST RESPONDERS CENTER FOR EXCELLENCE','','')]):
            result=c.search_snapshot_or_embedded_state(self.org,'KY')
        self.assertEqual(c.public_status(result),'Not Registered')

if __name__=='__main__':unittest.main(verbosity=2)
