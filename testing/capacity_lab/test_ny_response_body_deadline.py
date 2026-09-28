"""Real headless/localhost controls for headers arriving before the JSON body."""
import ast,json,subprocess,threading,time,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock
from playwright.sync_api import sync_playwright,TimeoutError as BrowserTimeout
import registry_snapshot_server as m


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        status=403 if self.path.startswith('/reject') else 200
        data=b'{"verified":true,"data":[{"ein":"123456789"}]}'
        self.send_response(status);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.flush()
        if self.path.startswith(('/slow','/reject')):time.sleep(1)
        try:self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass


class BodyDeadline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.play=sync_playwright().start();cls.browser=cls.play.chromium.launch(headless=True)
    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.play.stop();cls.server.shutdown();cls.server.server_close()
    def setUp(self):
        self.page=self.browser.new_page();self.page.goto(f'http://127.0.0.1:{self.server.server_port}/')
    def tearDown(self):self.page.close()
    def run_response(self,path,budget=0.25,submit=None):
        deadline=time.perf_counter()+budget
        def remaining():
            n=int((deadline-time.perf_counter())*1000)
            if n<=0:raise TimeoutError('fixture budget')
            return n
        return m.ny_complete_browser_response(self.page,lambda r:r.url.endswith(path),
            submit or (lambda:self.page.evaluate(f"void fetch({json.dumps(path)})")),remaining)
    def test_slow_body_cannot_outlive_request_budget(self):
        start=time.perf_counter()
        with self.assertRaises((TimeoutError,BrowserTimeout)):self.run_response('/slow')
        self.assertLess(time.perf_counter()-start,0.8)
    def test_fast_body_is_not_missed_before_headers_context_exits(self):
        for i in range(6):
            r=self.run_response('/fast?i='+str(i))
            self.assertEqual(m.NYBrowserResponse(r).json()['data'][0]['ein'],'123456789')
    def test_unrelated_finished_request_does_not_complete_slow_response(self):
        start=time.perf_counter()
        with self.assertRaises((TimeoutError,BrowserTimeout)):
            self.run_response('/slow?correlation',submit=lambda:self.page.evaluate("void fetch('/slow?correlation'); void fetch('/fast?unrelated')"))
        self.assertLess(time.perf_counter()-start,0.8)
    def test_explicit_http_rejection_does_not_wait_for_body(self):
        start=time.perf_counter();r=self.run_response('/reject');wrapped=m.NYBrowserResponse(r)
        self.assertEqual(r.status,403);self.assertEqual(wrapped.json(),{})
        with self.assertRaisesRegex(RuntimeError,'403'):wrapped.raise_for_status()
        self.assertLess(time.perf_counter()-start,0.5)
    def test_non_200_wrapper_never_reads_rejected_body(self):
        for status in (403,429,500):
            r=MagicMock();r.status=status;wrapped=m.NYBrowserResponse(r)
            r.json.assert_not_called()
            with self.assertRaises(RuntimeError):wrapped.raise_for_status()
    def test_timeout_does_not_poison_following_query(self):
        with self.assertRaises((TimeoutError,BrowserTimeout)):self.run_response('/slow?first')
        self.assertEqual(self.run_response('/fast?second').status,200)
    def test_entire_master_change_is_only_completed_response_transport(self):
        from testing.capacity_lab.ny_failed_scope import strip_ny_failed_wakeup
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','647fddb:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'))
        strip_ny_failed_wakeup(new)
        self.assertEqual(ast.dump(old),ast.dump(new))

if __name__=='__main__':unittest.main(verbosity=2)
