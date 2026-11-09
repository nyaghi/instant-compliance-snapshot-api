from copy import deepcopy
from datetime import date
import time
import unittest
from unittest.mock import Mock, patch

import registry_snapshot_server as c
from deployment.state_snapshots import matching_reference


class OvernightRegistryRepairs(unittest.TestCase):
    def test_ms_blank_duplicate_exemption_and_original_grid_link(self):
        name = "Society for Neuroscience"
        identifier = "100026597"
        row = dict(name=name, identifier=identifier, raw_status="Current - Exempted")
        search = dict(state="MS", operation="search", name=name)
        record = dict(state="MS", organization_name=name, ein="520895843", issued=time.time(),
                      pending=dict(query_id="detail", query=dict(state="MS", operation="detail", identifier=identifier)),
                      completed=[dict(query=search, evidence=dict(rows=[row, dict(row)], total=2))])
        failure = dict(query_id="detail", reason="NY_CONNECTOR_MS_DETAIL_UNAVAILABLE")
        result = c.ms_duplicate_exempt_detail_fallback(record, failure)
        self.assertEqual(result["status"], "Exempt")
        self.assertIn("The detail page is not available.", result["comments"])
        grid = dict(ein="520895843", state="MS", identifier=identifier, record_name=name, operation="search")
        self.assertIs(matching_reference(result, [grid]), grid)
        self.assertIsNone(matching_reference({**result, "status_reason": ""}, [grid]))
        for key, value in [("name", "Different Organization"), ("identifier", "100026598"),
                           ("raw_status", "Current - Registered")]:
            changed = deepcopy(record)
            changed["completed"][0]["evidence"]["rows"][1][key] = value
            self.assertIsNone(c.ms_duplicate_exempt_detail_fallback(changed, failure))
        for update in [dict(query_id="stale"), dict(reason="NY_CONNECTOR_INCOMPLETE")]:
            self.assertIsNone(c.ms_duplicate_exempt_detail_fallback(record, {**failure, **update}))

    def test_ok_dated_exemption_notice_compares_expired_records(self):
        name = "SOCIETY FOR NEUROSCIENCE"
        older, newer = "4312394147", "4312435886"
        org = c.checker.Organization(name, "520895843")
        org.ok_equivalent_records = [(name, newer), (name, older)]
        page, module = Mock(), c.state_batch_modules(["OK"])[c.load_state_batch_bundle().STATE_TO_MODULE["OK"]]
        histories = {
            newer: "23499660001 Notice of Registration Exemption January 8, 2014 20",
            older: "21234790002 Application for Registration February 25, 2013 68",
        }

        def goto(url, **kwargs):
            page.url = url
            filing = histories[url.rsplit("=", 1)[-1]]
            page.locator.return_value.nth.return_value.inner_text.return_value = filing
            return Mock(status=200)

        page.goto.side_effect = goto
        page.locator.return_value.count.return_value = 1
        with (patch.object(c, "trial_identity", return_value=True),
              patch.object(module, "body_text", return_value=f"Entity Name\n{name}\nStatus\nExpired\nFiling History\n")):
            self.assertEqual(c.ok_open_latest_equivalent_detail(page, org, module, (None, None, name, older)),
                             (name, newer))
            proof = next(row for row in org.ok_compared_records if row["identifier"] == newer)
            self.assertEqual(proof["latest_identity_event_date"], "2014-01-08")
            self.assertIsNone(proof["latest_registration_filed"])
            histories[newer] = "23499660001 Notice of Registration Exemption Unknown 20"
            with self.assertRaisesRegex(TimeoutError, "recency is incomplete"):
                c.ok_open_latest_equivalent_detail(page, org, module, (None, None, name, older))

    def test_sc_queries_complete_suffix_free_primary_before_historical_alias(self):
        name = "Crohn's & Colitis Foundation Inc."
        primary = "Crohn's & Colitis Foundation"
        queried = []
        session = Mock()
        session.get.return_value.text = "<form></form>"

        def post(_url, data, **kwargs):
            response = Mock()
            if "ctl00$MainContent$Hidden_CharityID" in data:
                response.text = (
                    '<span id="MainContent_lbl_CharityName">Crohn\'s &amp; Colitis Foundation, Inc.</span>'
                    '<span id="MainContent_lblCharityID">P4209</span> Status Registered Due Date 5/15/2027'
                )
            else:
                query = data["ctl00$MainContent$txt_CharitySearchName"]
                queried.append(query)
                response.text = (
                    '<a href="javascript:CharityInfo(4209)">Crohn\'s &amp; Colitis Foundation, Inc.</a>'
                    if query == primary else "No Results Found"
                )
            return response

        session.post.side_effect = post
        with (patch.object(c, "curl_requests", Mock(Session=Mock(return_value=session))),
              patch.object(c, "build_search_queries", return_value=[name, "CROHNS & COLITIS FOUNDATION OF AMERICA, INC."])):
            result = c.sc_official_detail_lookup(c.checker.Organization(name, "136193105"))
        self.assertEqual(queried, [primary])
        self.assertTrue(result.success)
        self.assertEqual(result.matched_registry_identifier, "P4209")


if __name__ == "__main__":
    unittest.main()
