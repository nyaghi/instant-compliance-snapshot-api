import json
from pathlib import Path
import unittest
from unittest.mock import patch
from deployment import tn_extension_access as access, tn_extensions_demo as demo
from testing.test_tn_extensions_demo import ACCOUNT, OTHER, NOW, Accounts, Handler

ORIGIN = 'https://staging.example'
START = dict(action='begin-check', ein='141442493', name='MARIST UNIVERSITY')


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.alerts = Accounts()
        self.addCleanup(self.alerts.c.db.close)

    def request(self, *, signed=ACCOUNT, email=ACCOUNT, cookie='', now=NOW,
                key='test-unlock', origin=ORIGIN, body=None):
        handler = Handler(START if body is None else body, account=signed, origin=origin)
        handler.headers.update({'X-CC-Aurora-Account':email,'Authorization':'Bearer '+key,'Cookie':cookie})
        with patch.object(demo.time,'time',return_value=now):
            return demo.handle(self.alerts,handler,origin=ORIGIN,verify_unlock=lambda e,k:k=='test-unlock')

    def bootstrap(self):
        code, _, headers = self.request()
        self.assertEqual(code,200)
        grant=headers['Set-Cookie']
        for attr in ('HttpOnly','Secure','SameSite=Strict','Path=/'):
            self.assertIn(attr,grant)
        return grant.split(';')[0]

    def test_after_seven_days_click_resumes_same_owner(self):
        grant=self.bootstrap()
        now=NOW+8*86400
        status=dict(action='status',ein=START['ein'])
        self.assertEqual(self.request(signed=None,cookie=grant,now=now,body=status)[0],403)
        self.assertEqual(self.request(signed=None,cookie=grant,now=now)[0],200)
        self.assertEqual(self.request(signed=None,cookie=grant,now=now+1,body=status)[0],200)
        owners=self.alerts.c.execute('SELECT DISTINCT account FROM cc_tn_extension_demo_checks').fetchall()
        self.assertEqual([r['account'] for r in owners],[ACCOUNT])

    def test_expired_wrong_or_missing_proof_cannot_resume(self):
        grant=self.bootstrap()
        for extra in [dict(cookie=''), dict(cookie=grant+'X'),dict(email=OTHER),
                      dict(now=NOW+access.REMEMBER_SECONDS),dict(key='wrong'),dict(origin='https://other.example')]:
            params=dict(signed=None,cookie=grant,now=NOW+8*86400)
            params.update(extra)
            with self.subTest(extra=list(extra)):
                self.assertEqual(self.request(**params)[0],403)

    def test_account_switch_replaces_browser_identity(self):
        first=self.bootstrap()
        self.assertEqual(self.request(signed=OTHER,cookie=first,email=ACCOUNT)[0],403)
        code,_,headers=self.request(signed=OTHER,cookie=first,email=OTHER)
        self.assertEqual(code,200)
        second=headers['Set-Cookie'].split(';')[0]
        self.assertNotEqual(first,second)
        self.assertEqual(self.request(signed=None,cookie=first)[0],403)
        self.assertEqual(self.request(signed=None,cookie=second,email=OTHER)[0],200)

    def test_document_download_is_account_scoped_and_requires_recent_access(self):
        grant=self.bootstrap()
        def document(now):
            h=Handler(account=None,path=demo.PREFIX+'/documents/'+'a'*32)
            h.headers['Cookie']=grant
            with patch.object(demo.time,'time',return_value=now):
                return demo.handle(self.alerts,h,origin=ORIGIN)[0]
        # Authenticated, but a nonexistent or foreign document stays unavailable.
        self.assertEqual(document(NOW+2),404)
        self.assertEqual(document(NOW+access.ACTIVE_SECONDS+1),403)

    def test_browser_grant_cannot_authenticate_alerts(self):
        from deployment.alerts import Alerts
        grant=self.bootstrap()
        h=Handler(account=None);h.headers['Cookie']=grant
        self.assertIsNone(Alerts.account(None,None,h))

    def test_seventy_recent_main_results_reused_after_account_cookie_expires(self):
        from deployment.tn_extension_refresh import issue_public_proof
        from testing.test_tn_extension_refresh import result
        from testing.test_tn_extension_reuse import MASTER,KEY,VERSION
        roster=json.loads((Path(__file__).parent/'fixtures/gate53/LOCAL-70.json').read_text())
        self.assertEqual(len({r['ein'] for r in roster}),70)
        grant=self.bootstrap()
        now=NOW+8*86400
        for i,org in enumerate(roster):
            with self.subTest(ein=org['ein']):
                handler=Handler(account=None)
                handler.headers['Cookie']=grant
                source=result(org['ein'],org['name'],'CO'+str(70000+i))
                token=issue_public_proof(MASTER,handler,source,now)
                self.assertTrue(token)
                h=Handler(dict(action='begin-check',ein=org['ein'],name=org['name'],source_token=token),account=None)
                h.headers.update({'Cookie':grant,'Authorization':'Bearer TEST','X-CC-Aurora-Account':ACCOUNT})
                with patch.object(demo.time,'time',return_value=now+1):
                    code,data,_=demo.handle(self.alerts,h,origin=ORIGIN,source_key=KEY,source_version=VERSION,verify_unlock=lambda e,k:e==ACCOUNT and k=='TEST')
                self.assertEqual(code,200)
                self.assertTrue(data['reuse_public'])
