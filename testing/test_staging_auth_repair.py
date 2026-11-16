"""Staging cookie-session denial must not invalidate HTTP Basic credentials."""
import threading,unittest
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from unittest.mock import patch
from playwright.sync_api import sync_playwright
from deployment import performance_lab as lab
from deployment.alerts import handle
from testing.test_alerts_pilot import Service,FakeQueue,Handler,ORIGIN
class AuthRepair(unittest.TestCase):
 def test_account_still_required_and_default_contract_preserved(self):
  a=Service(FakeQueue());self.addCleanup(a.c.db.close)
  for code in [401,403]:
   result=handle(a,Handler(),'/api/alerts/badge',origin=ORIGIN,session_required_status=code)
   self.assertEqual(result[0],code);self.assertEqual(result[1]['code'],'ALERTS_SESSION_REQUIRED');self.assertNotIn('unseen',result[1]);self.assertNotIn('WWW-Authenticate',result[2])
 def test_both_staging_routes_use_nonchallenging_denial(self):
  source=Path(lab.__file__).read_text();self.assertEqual(source.count('session_required_status=403'),2)
 def test_discovery_includes_existing_private_credential(self):
  source=Path('web-staging/organization-identity.js').read_text()
  with patch.object(lab,'trial_identity',return_value={'origin':ORIGIN}):
   rendered=lab.final_four_asset('organization-identity.js',source)
  self.assertIn('"Authorization": "Bearer " + config.admin_passcode',rendered)
  self.assertNotIn('"Authorization"',source)
 def test_real_chromium_401_evicts_basic_but_403_preserves_it(self):
  rows=[]
  class H(BaseHTTPRequestHandler):
   def log_message(self,*a):pass
   def do_GET(self):
    rows.append((self.path,bool(self.headers.get('Authorization'))))
    if self.path.startswith('/badge'):
     self.send_response(int(self.path[-3:]));self.end_headers();self.wfile.write(b'{}');return
    if not self.headers.get('Authorization'):
     self.send_response(401);self.send_header('WWW-Authenticate','Basic realm="fixture"');self.end_headers();return
    self.send_response(200);self.end_headers();self.wfile.write(b'<html>fixture</html>')
  s=ThreadingHTTPServer(('127.0.0.1',0),H);threading.Thread(target=s.serve_forever,daemon=True).start()
  try:
   with sync_playwright() as p:
    b=p.chromium.launch(headless=True)
    for code in [401,403]:
     rows.clear();c=b.new_context(http_credentials={'username':'lab','password':'fixture-only'});page=c.new_page();page.goto('http://127.0.0.1:'+str(s.server_port)+'/');page.evaluate('(code)=>fetch("/badge"+code).then(()=>fetch("/protected"))',code)
     self.assertEqual([auth for path,auth in rows if path=='/protected'],[False,True] if code==401 else [True]);c.close()
    b.close()
  finally:s.shutdown();s.server_close()
if __name__=='__main__':unittest.main()
