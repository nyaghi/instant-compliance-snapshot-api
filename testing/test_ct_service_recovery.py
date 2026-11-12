import unittest
from unittest.mock import patch

import registry_snapshot_server as app


ROW = """<tr><td><b class="forge-typography--headline6">UNITED SERVICES ORGANIZATIONS INC</b>
<b>Credential</b><p>CHR.0002140</p><b>Credential Description</b><p>PUBLIC CHARITY</p>
<b>Status</b><p>ACTIVE</p></td></tr>"""
DETAIL = ("Name and Address UNITED SERVICES ORGANIZATIONS INC Address 2111 WILSON BLVD STE 1200 ARLINGTON, VA 22201-3052 "
          "Registration CHR.0002140 Expiration Date 11/30/2026 Status ACTIVE")


class ServiceRecovery(unittest.TestCase):
    def check(self, detail, address, first_timeout=False):
        organization = app.checker.Organization("United Service Organizations Inc.", "13-1610451")
        queries = []

        def search(session, fields, headers, name, timeout):
            queries.append((name, timeout))
            if len(queries) == 1 and first_timeout:
                raise TimeoutError("first spelling timed out")
            return "Showing 1 result" + ROW if name == "United Services Organizations" else "Showing 0 results"

        with (patch.object(app, "trial_identity", return_value={"origin": "fixture"}),
              patch.object(app, "known_names_for_ein", return_value=["USO", "United Service Organization Inc"]),
              patch.object(app, "ct_direct_prepare_session", return_value=(None, {}, {})),
              patch.object(app, "ct_direct_post_query", side_effect=search),
              patch.object(app, "ct_direct_detail_text", return_value=detail),
              patch.object(app, "identity_source_result", return_value={"organization_records": [address]})):
            result = app.search_ct_direct(organization)
        self.assertEqual([name for name, _ in queries[:2]],
                         ["United Service Organizations", "United Services Organizations"])
        self.assertLessEqual(queries[0][1], 8)
        return result

    def test_plural_exact_address_survives_original_timeout(self):
        office = {"address_role": "organization", "ein": "131610451", "street": "2111 Wilson Blvd Ste 1200",
                  "city": "Arlington", "state": "VA", "postal_code": "22201",
                  "names": ["United Service Organizations Incorporated"]}
        result = self.check(DETAIL, office, first_timeout=True)
        self.assertTrue(result.success)
        self.assertEqual(result.matched_registry_identifier, "CHR.0002140")
        for variant in ({**office, "street": "2111 Wilson Blvd Ste 1400"}, {**office, "address_role": "agent"}):
            self.assertFalse(self.check(DETAIL, variant).success)
        conflict = self.check(DETAIL + " EIN: 12-3456789", office)
        self.assertNotEqual(conflict.matched_registry_identifier, "CHR.0002140")

    def test_explicit_ein_binds_when_the_address_is_unavailable(self):
        self.assertTrue(self.check(DETAIL + " EIN: 13-1610451", {}).success)
