"""Real local HTTP form responses; no live registry requests."""
import ast,threading,time,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch,MagicMock
import registry_snapshot_server as m
from deployment.co_budget import STOP

class Handler(BaseHTTPRequestHandler):
 delay=0;body='No results found. Try removing or changing your search terms.'
 def log_message(self,*args):pass
 def send(self,text):
  raw=('<html><body>'+text+'</body></html>').encode();self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(raw)));self.end_headers()
  try:self.wfile.write(raw)
  except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
 def do_GET(self):self.send('<form method="POST"><label><input type="radio" name="orgType" checked>Charitable organization</label><input id="advancedSearchForm:orgName" name="search" type="text"><button>Search</button></form>')
 def do_POST(self):
  self.rfile.read(int(self.headers.get('Content-Length','0')));time.sleep(self.delay);self.send(self.body)

class ColoradoNavigation(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
  cls.runtime=m.checker.sync_playwright().start();cls.browser=cls.runtime.chromium.launch(headless=True)
 @classmethod
 def tearDownClass(cls):cls.browser.close();cls.runtime.stop();cls.server.shutdown();cls.server.server_close()
 def execute(self,body,delay=0,budget=60,baseline=False,name='Example Charity',ein='123456789'):
  Handler.body=body;Handler.delay=delay
  source=Path('Charity_Checker_Script for 13_states.py').read_text(encoding='utf8');tree=ast.parse(source);fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='search_co');src=ast.get_source_segment(source,fn)
  src=src.replace('https://www.coloradosos.gov/ccsa/pages/search/','http://127.0.0.1:'+str(self.server.server_port)+'/')
  if baseline:src=src.replace('with page.expect_navigation(wait_until="domcontentloaded", timeout=co_timeout(25000)):\n            page.keyboard.press("Enter")','page.keyboard.press("Enter")\n        safe_wait_for_network_idle(page, timeout=co_timeout(25000))')
  scope=dict(m.checker.__dict__);exec(src,scope);ctx=self.browser.new_context();page=ctx.new_page();token=STOP.set(time.monotonic()+budget);start=time.monotonic()
  try:return scope['search_co'](page,m.checker.Organization(name,ein)),time.monotonic()-start
  finally:STOP.reset(token);ctx.close()
 def test_observed_transition_baseline_fails_candidate_completes(self):
  body='No results found. Try removing or changing your search terms.'
  old,_=self.execute(body,8,baseline=True);new,elapsed=self.execute(body,8)
  self.assertFalse(old.success);self.assertTrue(new.success);self.assertEqual(m.public_status(new),'Not Registered');self.assertLess(elapsed,12)
 def test_delayed_positive_retains_suspension(self):
  r,_=self.execute('Name: Example Charity\nStatus: Expired - may not solicit',8)
  self.assertTrue(r.success);self.assertEqual(r.status,'Suspended')
 def test_deadline_timeout_never_becomes_negative(self):
  r,elapsed=self.execute('No results found',3,budget=2)
  self.assertFalse(r.success);self.assertNotEqual(m.public_status(r),'Not Registered');self.assertLess(elapsed,4)
 def test_name_and_ein_controls_keep_source_statuses_and_query_scope(self):
  for name in ['RAND','IREX','PATH','Sundance','Teach for All','Jackie Robinson Foundation','Book Trust','World Learning']:
   for ein in ['', '123456789']:
    with self.subTest(name=name,ein=ein),patch.object(m.checker,'fast_sleep'):
     r,_=self.execute('Name: '+name+'\nStatus: Current',name=name,ein=ein)
     self.assertTrue(r.success);self.assertEqual(r.status,'Current')
     self.assertEqual(r.source_url.endswith('advanced.xhtml'),not ein and len(name.split())==1)

if __name__=='__main__':unittest.main()
