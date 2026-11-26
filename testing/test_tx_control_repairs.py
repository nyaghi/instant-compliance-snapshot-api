import time
import unittest
from unittest.mock import patch

import registry_snapshot_server as app
from deployment import durable_queue


class ControlRepairs(unittest.TestCase):
    def test_nevada_completed_non_soliciting_business_only(self):
        org = app.checker.Organization("American National Red Cross", "53-0196605")
        identifier = "NV20111167160"
        category = "NT7 Business License Other"
        row = {"name": org.organization_name, "identifier": identifier, "entity_type": category}
        url = ("https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?"
               "screen=Manage-Business&id=d1b62c76-d5af-4ff3-b07d-038b7fa8d854")

        for solicits, expected in [("No", "Not Registered"), ("Yes", "Unable to Confirm"), ("", "Unable to Confirm")]:
            def source(query):
                if query["operation"] == "search":
                    return dict(state="NV", query=query, complete=True, verification_pending=False,
                                total=1, rows=[dict(row)])
                return dict(query=query, complete=True, source_url=url, fields={
                    "NV Business ID": identifier, "Entity Name": org.organization_name,
                    "Entity Type": category, "Entity Status": "Expired",
                    "Solicits Charitable Contribution?": solicits,
                    "Annual Renewal Due Date/Expiration Date": "03/31/2014", "FEIN": "-",
                })

            with (patch.object(app, "trial_identity", return_value=True),
                  patch.object(app, "licensed_charity_names", return_value=([org.organization_name], []))):
                result = app.final_four_browser_lookup(org, "NV", source)
            self.assertEqual(result.status, expected)
            self.assertEqual(result._nv_scope_detail, (identifier, org.organization_name))
            self.assertFalse(result.matched_registry_identifier)
            self.assertIn(identifier, result.source_note)
            if solicits == "No":
                self.assertTrue(result.success)
                self.assertIn("separate charitable registration or exemption",
                              app.comments_for_result(result, "", expected))

    def test_tennessee_detail_office_disagreement_keeps_identity_for_confirmation(self):
        org = app.checker.Organization("University of Miami", "59-0624458")
        row = dict(name=org.organization_name, identifier="CO27245", city="MIAMI", region="FL", aliases=[])
        fields = {"Name": org.organization_name, "CO Number": row["identifier"], "Status": "Active",
                  "Registration Date": "08/23/2016", "Expiration Date": "",
                  "Address": "1808 ASTON AVENUE, SUITE 230 CARLSBAD CA 92008",
                  "financial_count": 0, "financial_periods": []}
        detail = app.tn_charity_detail_evidence(fields, row["identifier"], row)
        filer = {"ein": "590624458", "state": "FL", "city": "Miami"}
        with (patch.object(app, "trial_identity", return_value=True),
              patch.object(app, "identity_source_result", return_value={"filer_address": filer}) as irs,
              patch.dict(app.PUBLIC_PROFILE_CACHE, {}, clear=True)):
            result = app.licensed_charity_result(org, "TN", [detail], time.monotonic() + 6, detail["url"])
        self.assertEqual(result.status, "Needs Review")
        self.assertEqual(result._cc_identity_review["records"][0]["identifier"], "CO27245")
        self.assertIn("CARLSBAD CA 92008", result.source_note)
        self.assertIn("Miami, FL", result.source_note)
        irs.assert_called_once()

    def test_wisconsin_retry_is_fenced_to_one_reaped_worker_failure(self):
        job = dict(state="WI", mode="standard", attempt=1, stop_reason=None, deadline=140,
                   source_version="2026.09.29.2-performance-lab")
        with patch.object(durable_queue, "performance_origin_enabled", return_value=True):
            good = durable_queue.wisconsin_worker_retry(job, None, "WORKER_TASK_FAILED", 100, "old-worker")
            self.assertEqual(good["failed_worker"], "old-worker")
            for changes in [{"state": "MI"}, {"mode": "sales"}, {"attempt": 2}, {"stop_reason": "canceled"},
                            {"deadline": 129}, {"source_version": "production"}]:
                self.assertIsNone(durable_queue.wisconsin_worker_retry(
                    {**job, **changes}, None, "WORKER_TASK_FAILED", 100, "old-worker"))
            self.assertIsNone(durable_queue.wisconsin_worker_retry(
                job, None, "QUEUE_CONNECTION_LOST", 100, "old-worker"))
