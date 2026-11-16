from datetime import datetime
from unittest import TestCase
from zoneinfo import ZoneInfo
from deployment.alerts_browser import overnight, claim, enable, SCHEMA
from testing import test_alerts_pilot as fixtures
from testing.test_alerts_pilot import ACCOUNT, OTHER

class OvernightTests(TestCase):
    def test_boundaries_and_dst(self):
        for day in ('2026-03-08', '2026-11-01', '2026-11-16'):
            for zone in ('America/New_York', 'America/Los_Angeles', 'Europe/London'):
                for clock, allowed in [('21:59:59', False), ('22:00:00', True), ('00:00:00', True), ('04:59:59', True), ('05:00:00', False), ('12:00:00', False)]:
                    with self.subTest(day=day, zone=zone, clock=clock):
                        stamp=datetime.fromisoformat(day+'T'+clock).replace(tzinfo=ZoneInfo(zone)).timestamp()
                        self.assertEqual(overnight(stamp, zone), allowed)
    def test_invalid_zone_does_not_start(self):
        self.assertFalse(overnight(0, 'Not/AZone'))

class OvernightClaimTests(TestCase):
    setUp=fixtures.AlertsTests.setUp
    def test_daytime_claim_does_not_queue_or_modify_baseline(self):
        self.c.db.executescript(SCHEMA)
        self.a.clock=datetime(2026,11,16,16,tzinfo=ZoneInfo('America/New_York')).timestamp()
        profile=enable(self.a,self.c,ACCOUNT)['profile']
        result=claim(self.a,self.c,ACCOUNT,profile)
        self.assertTrue(result['scheduled'])
        self.assertEqual(self.q.submissions, [])
        self.assertEqual(self.c.execute('SELECT count(*) AS n FROM cc_alert_browser_runs').fetchone()['n'],0)
        with self.assertRaises(ValueError):claim(self.a,self.c,OTHER,profile)
        self.a.clock=datetime(2026,11,16,22,tzinfo=ZoneInfo('America/New_York')).timestamp()
        self.assertIn('lease',claim(self.a,self.c,ACCOUNT,profile))
