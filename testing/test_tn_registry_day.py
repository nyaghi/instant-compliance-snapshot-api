from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch

import registry_snapshot_server as cc


class TennesseeRegistryDay(TestCase):
    def test_expiration_uses_nashville_midnight_and_preserves_reported_standing(self):
        fields = {"Name": "Example Charity", "CO Number": "CO123", "Status": "Active",
                  "Registration Date": "11/01/2020", "Expiration Date": "11/27/2026", "Address": ""}
        for hour, raw, expected in [(4, "Active", "Upcoming Filing"), (6, "Active", "Delinquent"),
                                    (4, "Revoked", "Revoked"), (6, "Exempt", "Exempt")]:
            moment = datetime(2026, 11, 28, hour, tzinfo=timezone.utc)
            with self.subTest(hour=hour, raw=raw), patch.object(cc, "datetime", wraps=datetime) as clock:
                clock.now.side_effect = lambda zone: moment.astimezone(zone)
                status = cc.tn_charity_detail_evidence(fields | {"Status": raw}, "CO123", {"name": fields["Name"]})
                self.assertEqual(status["status"], expected)
