import time
import unittest
from datetime import date
from unittest.mock import Mock, patch

import registry_snapshot_server as master
from deployment.state_snapshots import CaptureRun, DEADLINE, me_detail_name_bound


class GateRepairs(unittest.TestCase):
    def test_ok_slow_preparation_preserves_final_post_allowance(self):
        page = Mock(url="https://www.sos.ok.gov/corp/charityDetail.aspx?id=4312076366")
        page.get_by_role.return_value.get_attribute.return_value = (
            "__doPostBack('ctl00$DefaultContent$grdFilingList$ctl03$lnkAction','')"
        )
        page.locator.return_value.first.evaluate.return_value = {"__VIEWSTATE": "fixture"}
        response = page.request.post.return_value
        response.ok = True
        response.body.return_value = b"%PDF-certificate"
        for state_deadline, expected in [(120, 4900), (110, 3900)]:
            with self.subTest(state_deadline=state_deadline):
                token = DEADLINE.set(state_deadline)
                try:
                    with patch.object(master.time, "monotonic", side_effect=[100, 105, 105.1]), patch.object(
                        master, "ok_certificate_expiration", return_value=(date(2027, 8, 18), "verified")
                    ):
                        result = master.ok_fetch_registration_certificate(
                            page, "78036050002 Renewal Registration August 18, 2026 10", "Example Foundation"
                        )
                    due, _ = result
                    self.assertEqual(due, date(2027, 8, 18))
                    self.assertAlmostEqual(page.request.post.call_args.kwargs["timeout"], expected, delta=1)
                finally:
                    DEADLINE.reset(token)

    def test_ok_main_snapshot_retains_bound_identity_with_unconfirmed_certificate(self):
        name = "American Civil Liberties Union Foundation Inc."
        org = master.checker.Organization(name, "13-6213516")
        identifier = "4312076366"
        url = master.OK_DETAIL_URL + identifier
        raw = "78036050002 Renewal Registration August 18, 2026 10"
        result = master.checker.StateResult(
            name, org.ein, "OK", "Needs Review", url, raw_status_text=raw,
            matched_registry_name=name, matched_registry_identifier=identifier, success=False,
        )
        result.reason_code = "OK_SELECTED_CERTIFICATE_UNCONFIRMED"
        data = master.response_data_for_lookup(result, raw, org, name, org.ein, "OK", time.perf_counter())
        self.assertEqual(data["status"], "Unable to Confirm")
        self.assertEqual(data["matched_registry_identifier"], identifier)
        for body, expected in [(f"Filing Number {identifier}\nEntity Name {name}", 1), ("Different entity", 0)]:
            run = CaptureRun(name, org.ein, "OK")
            run.document(url, b"original-pixels", "image", body)
            self.assertEqual(run.finish(data)["evidence_metrics"]["bound_original_assets"], expected)

    def test_maine_only_matching_primary_section_binds_when_history_exists(self):
        text = ("CHARITABLE SOLICITATIONS\nTHE PEW CHARITABLE TRUSTS\n"
                "CHARITABLE ORGANIZATION\nLicense Number: CO6093\nStatus: Active\n"
                "Expiration Date: 11/30/2026\n"
                "CHARITABLE ORGANIZATION\nLicense Number: CO4783\nStatus: Failed to Renew")
        name = "PEW CHARITABLE TRUSTS, THE"
        self.assertTrue(me_detail_name_bound(name, text, "CO6093"))
        self.assertFalse(me_detail_name_bound(name, text, "CO4783"))
        self.assertFalse(me_detail_name_bound(name, text.replace("CO4783", "CO6093"), "CO6093"))
        self.assertFalse(me_detail_name_bound(name, text + "\nLicense Number: CO9999", "CO6093"))
        self.assertFalse(me_detail_name_bound("Other Organization", text, "CO6093"))

    def test_tennessee_distinguishes_foundation_from_same_office_union(self):
        name = "American Civil Liberties Union Foundation Inc."
        org = master.checker.Organization(name, "13-6213516")
        union = {"name": "AMERICAN CIVIL LIBERTIES UNION, INC.", "identifier": "CO3795", "ein": ""}
        self.assertEqual(master.licensed_charity_identity(org, union, "TN", time.monotonic() + 5), "possible")
        with patch.object(master, "score_candidate", return_value={"score": 100, "decision": "accepted"}):
            union["ein"] = org.ein
            self.assertEqual(master.licensed_charity_identity(org, union, "TN", time.monotonic() + 5), "accepted")

    def test_mississippi_full_cna_legal_name_is_only_probe(self):
        self.assertEqual(master.ms_name_search_plan("CNA Corporation"), ["CNA Corporation"])
        self.assertEqual(master.ms_name_search_plan("CNA"), [])


if __name__ == "__main__":
    unittest.main()
