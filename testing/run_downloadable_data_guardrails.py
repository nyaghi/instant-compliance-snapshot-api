"""Freshness and source integrity regression for deployed weekly assets."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc

class WeeklyDataTests(unittest.TestCase):
    def test_la_and_or_comments_always_include_result_freshness(self):
        for state in ("LA", "OR"):
            for status in ("Current", "Not Registered", "Site Not Reachable"):
                result = cc.checker.StateResult("Example", "98-7654320", state, status, "https://example.org")
                comment = cc.comments_for_result(result, "", status)
                self.assertIn("Data freshness note:", comment)
                self.assertIn(f"Scheduled {state} dataset last downloaded:", comment)
                self.assertIn("confirm time-sensitive decisions directly with the state", comment)

    def test_all_five_deployed_assets_verified(self):
        for state in ("KS", "KY", "LA", "NH", "OR"):
            self.assertTrue(cc.downloadable_data_info(state)["usable"], state)

    def test_stale_data_rejected(self):
        with patch.object(cc.time, "time", return_value=cc.time.time() + 9 * 86400):
            for state in ("KS", "KY", "LA", "NH", "OR"):
                self.assertFalse(cc.downloadable_data_info(state)["usable"], state)
            org = cc.checker.Organization(organization_name="Example", ein="000000000")
            result = cc._search_snapshot_or_embedded_state_once(org, "KS")
            self.assertNotEqual(cc.public_status(result), "Not Registered")
            self.assertIsNone(cc.or_snapshot_row_for_ein("860481941"))

    def test_oregon_fiscal_dates_remain_parseable(self):
        import csv
        with (cc.BASE_DIR / "Charity_OR.txt").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle, delimiter="\t"))[1:]
        self.assertGreater(len(rows), 10000)
        for row in rows:
            for value in row[14:16]:
                if value:
                    self.assertIsNotNone(cc.parse_ce_date(value), value)

    def test_corrupt_checksum_rejected(self):
        manifest = json.loads(cc.DOWNLOADABLE_MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest["states"]["KS"]["assets"][0]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with patch.object(cc, "DOWNLOADABLE_MANIFEST_PATH", path):
                self.assertFalse(cc.downloadable_data_info("KS")["usable"])

    def test_ky_does_not_use_undated_embedded_fallback(self):
        with patch.object(cc, "weekly_asset", return_value=None), patch.object(cc, "load_ky_live_pdf_records", return_value=[]):
            with self.assertRaises(RuntimeError):
                cc.load_ky_snapshot_records()

    def test_empty_nh_source_cannot_be_negative(self):
        with patch.object(cc, "NH_LIVE_PDF_RECORDS", None), patch.object(cc, "nh_download_live_pdf_records", return_value=([], "")):
            with self.assertRaises(RuntimeError):
                cc.nh_live_pdf_records()

    def test_empty_la_export_cannot_be_negative(self):
        org = cc.checker.Organization(organization_name="Example", ein="000000000")
        with patch.object(cc, "la_registered_charities_rows_from_xlsx", return_value=[]):
            result = cc.search_la_downloaded_export(None, org)
            self.assertFalse(result.success)
            self.assertNotEqual(cc.public_status(result), "Not Registered")

    def test_fresh_la_uses_deployed_export_without_download(self):
        org = cc.checker.Organization(organization_name="Make-A-Wish Foundation of America", ein="860481941")
        with patch.object(cc, "la_download_registered_charities_export", side_effect=AssertionError("Unnecessary live download")):
            self.assertTrue(cc.search_la_downloaded_export(None, org).success)

    def test_fresh_nh_and_ky_use_deployed_files(self):
        cc.NH_LIVE_PDF_RECORDS = None
        with patch.object(cc.urllib.request, "urlopen", side_effect=AssertionError("Unnecessary live download")):
            self.assertGreater(len(cc.nh_live_pdf_records()[0]), 1000)
            self.assertGreater(len(cc.load_ky_snapshot_records()), 1000)

if __name__ == "__main__":
    unittest.main(verbosity=2)
