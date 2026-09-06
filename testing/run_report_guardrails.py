"""Report fidelity, uncertainty, pagination and master-endpoint boundaries."""
import copy
import json
import sys
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import charity_clarity_report as report
import registry_snapshot_server as cc
from pypdf import PdfReader


def row(state="CO", status="Current"):
    return dict(organization_name="Example Community Foundation", ein="01-2345678", state=state, status=status, comments="Official registry returned this status.", raw_status_text="", source_note="", source_url="https://example.org/registry", checked_at_epoch=1788692400, app_version=cc.APP_VERSION)


class ReportTests(unittest.TestCase):
    def pdf(self, rows):
        content = report.generate_report({"results": rows}, cc.SUPPORTED_STATES)
        reader = PdfReader(BytesIO(content))
        return reader, "\n".join(p.extract_text() for p in reader.pages)

    def test_incomplete_never_produces_overall_low(self):
        self.assertEqual(report.risk_summary([row(), row("OK", "Site Not Reachable")])[0], "Not assessed")

    def test_high_with_incomplete_is_provisional(self):
        label = report.risk_summary([row("CO", "Delinquent"), row("OK", "Site Not Reachable")])[0]
        self.assertEqual(label, "High (3 of 3) - provisional")

    def test_no_record_does_not_assert_violation(self):
        _, text = self.pdf([row("LA", "Not Registered")])
        self.assertIn("Moderate (2 of 3)", text)
        self.assertIn("applicable registration or exemption requirements", text)

    def test_current_and_exempt_low(self):
        self.assertEqual(report.risk_summary([row(), row("VA", "Exempt")])[0], "Low (1 of 3)")

    def test_preserves_snapshot_and_exact_date(self):
        source = row("OK", "Upcoming Filing")
        source["comments"] = "Certificate expires 10/17/2026."
        original = copy.deepcopy(source)
        _, text = self.pdf([source])
        self.assertIn("10/17/2026", text)
        self.assertEqual(source, original)

    def test_small_report_has_three_pages(self):
        reader, text = self.pdf([row()])
        self.assertEqual(len(reader.pages), 3)
        self.assertIn("1 states checked", text)

    def test_all_30_states_fit_five_pages_with_adverse_and_incomplete(self):
        statuses = sorted(report.HIGH | report.MODERATE | report.INCOMPLETE | report.LOW)
        rows = [row(s, statuses[i % len(statuses)]) for i, s in enumerate(sorted(cc.SUPPORTED_STATES))]
        for r in rows:
            r["comments"] = ("Long detailed evidence with registry dates and organization identity. " * 20)
            r["matched_registry_identifier"] = "Registry certificate 12345678901234567890"
        reader, text = self.pdf(rows)
        self.assertEqual(len(reader.pages), 5)
        self.assertIn("30 states checked", text)
        for r in rows:
            self.assertIn(r["state"], text)

    def test_la_or_freshness_uses_original_snapshot_not_clock(self):
        rows = [row("LA"), row("OR")]
        for r in rows:
            r["comments"] += f" Data freshness note: Scheduled {r['state']} dataset last downloaded: 2026-08-30T10:00:00+00:00. State source date: not stated by source. Downloads may lag registry changes."
        _, text = self.pdf(rows)
        self.assertIn("LA: scheduled download Aug 30, 2026 10:00 UTC", text)
        self.assertIn("OR: scheduled download Aug 30, 2026 10:00 UTC", text)
        self.assertIn("Confirm time-sensitive decisions directly with the state", text)

    def test_missing_freshness_not_fabricated(self):
        _, text = self.pdf([row("OR")])
        self.assertIn("scheduled download not supplied in this snapshot", text)

    def test_ok_certificate_retrieval_time_survives_excerpt_shortening(self):
        statuses = sorted(report.HIGH | report.MODERATE | report.INCOMPLETE | report.LOW)
        rows = [row(s, statuses[i % len(statuses)]) for i, s in enumerate(sorted(cc.SUPPORTED_STATES))]
        ok = next(r for r in rows if r["state"] == "OK")
        ok["comments"] = "Long registry evidence. " * 30 + "Certificate freshness note: reused the verified certificate retrieved 2026-09-06 12:34:56 UTC (less than 24 hours old)."
        reader, text = self.pdf(rows)
        self.assertEqual(len(reader.pages), 5)
        self.assertIn("OK certificate: verified copy retrieved 2026-09-06 12:34:56 UTC", text)

    def test_duplicate_state_rejected(self):
        with self.assertRaises(ValueError): self.pdf([row(), row()])

    def test_mixed_entities_rejected(self):
        other = row("NY"); other["ein"] = "98-7654320"
        with self.assertRaises(ValueError): self.pdf([row(), other])

    def test_unknown_status_and_unsupported_state_rejected(self):
        for r in (row("ZZ"), row("CO", "Clearly safe")):
            with self.assertRaises(ValueError): self.pdf([r])

    def test_markup_is_literal_and_unsafe_link_not_embedded(self):
        source = row(); source["organization_name"] = 'Example <b>literal</b> & Foundation'
        source["source_url"] = "file:///etc/passwd"
        _, text = self.pdf([source])
        self.assertIn("<b>literal</b>", text)
        self.assertIn("Source link unavailable", text)
        self.assertEqual(report.safe_source("https://user:pass@example.org"), ("", "Source link unavailable"))

    def test_empty_and_oversized_input_rejected(self):
        for rows in ([], [row()] * 31):
            with self.assertRaises(ValueError): self.pdf(rows)

    def test_long_fields_rejected(self):
        source = row(); source["comments"] = "a" * 10001
        with self.assertRaises(ValueError): self.pdf([source])

    def test_long_registry_alias_list_does_not_block_report(self):
        source = row("WA", "Unknown")
        source["matched_registry_name"] = "Example national charity and regional aliases " * 30
        reader, text = self.pdf([source])
        self.assertEqual(len(reader.pages), 3)
        self.assertIn("Not assessed", text)

    def test_endpoint_auth_and_no_registry_work(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), cc.RegistrySnapshotHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        url = f"http://127.0.0.1:{server.server_address[1]}/api/report"
        try:
            with patch.object(cc, "run_state_lookups_parallel", side_effect=AssertionError("Reports must not run lookups")):
                payload = dict(results=[row()], email="staging-smoke@" + cc.EXEMPT_EMAIL_DOMAIN, admin_passcode=cc.ADMIN_PASSCODE)
                request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(response.headers["Content-Type"], "application/pdf")
                    self.assertTrue(response.read().startswith(b"%PDF"))
                payload["admin_passcode"] = "wrong"
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(url, data=json.dumps(payload).encode()))
                self.assertEqual(error.exception.code, 403)
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__":
    unittest.main(verbosity=2)
