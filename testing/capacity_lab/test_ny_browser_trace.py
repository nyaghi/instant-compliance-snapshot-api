"""Passive browser timing cannot submit, parse, classify or expose secrets."""
import ast,json,subprocess,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from playwright.sync_api import BrowserContext,sync_playwright
from deployment.queue_engine import observe_browser_transport,browser_trace_route
from deployment.queue_worker import log_browser_failure
from testing.capacity_lab.ny_trace_scope import strip_browser_trace_engine,strip_browser_trace_worker

class BrowserTrace(unittest.TestCase):
    def test_exact_scope(self):
        root=Path(__file__).resolve().parents[2]
        for path,strip in [('deployment/queue_engine.py',strip_browser_trace_engine),('deployment/queue_worker.py',strip_browser_trace_worker)]:
            old=ast.parse(subprocess.check_output(['git','show','371e88e:'+path],cwd=root).decode('utf-8'))
            new=ast.parse((root/path).read_text(encoding='utf-8'));strip(new)
            self.assertEqual(ast.dump(old),ast.dump(new),path)

    def test_other_states_and_versions_untouched(self):
        original=BrowserContext.new_page
        for state,version in [('WA','x-performance-lab'),('NY','staging'),('NY','production')]:
            with observe_browser_transport(SimpleNamespace(APP_VERSION=version),state) as trace:
                self.assertIsNone(trace);self.assertIs(BrowserContext.new_page,original)

    def test_known_routes_only(self):
        for url in ['http://charities-search.ag.ny.gov/RegistrySearch','https://evil.test/api/FileNet/RegistrySearch','https://charities-search-api.ag.ny.gov/private','https://charities-search.ag.ny.gov/secret']:
            self.assertIsNone(browser_trace_route(url))

    def test_real_events_preserve_request_and_never_read_body(self):
        master=SimpleNamespace(APP_VERSION='x-performance-lab');original=BrowserContext.new_page
        with tempfile.TemporaryDirectory() as folder,sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                context=browser.new_context();seen=[]
                def route(r):seen.append(r.request.url);r.fulfill(status=200,content_type='text/html',body='<p>private response</p>')
                context.route('**/*',route)
                with observe_browser_transport(master,'NY',Path(folder)/'result.trace.json') as trace:
                    page=context.new_page();page.goto('https://charities-search.ag.ny.gov/RegistrySearch?token=private')
                    page.goto('https://charities-search-api.ag.ny.gov/api/FileNet/RegistryDetail?orgID=private')
                self.assertEqual(len(seen),2)
                self.assertIs(BrowserContext.new_page,original)
                self.assertTrue(any(e['event']=='browser_complete' for e in trace.events))
                self.assertEqual({e['route'] for e in trace.events},{'navigation','details'})
                self.assertNotIn('private',json.dumps(trace.events));self.assertNotIn('token',json.dumps(trace.events))
                rows=json.loads((Path(folder)/'result.browser.json').read_text());self.assertEqual(rows,trace.events)
                rows.append({'event':'browser_failed','route':'search','url':'secret','headers':'secret','body':'secret'})
                (Path(folder)/'result.browser.json').write_text(json.dumps(rows))
                with patch('builtins.print') as emit:log_browser_failure({'job':{'state':'NY','id':'fixture'},'output':Path(folder)/'result.json'},'WORKFLOW_DEADLINE')
                self.assertNotIn('secret',emit.call_args.args[0]);self.assertIn('browser_failed',emit.call_args.args[0])
            finally:browser.close()

    def test_exception_restores_factory(self):
        original=BrowserContext.new_page
        with self.assertRaises(ValueError):
            with observe_browser_transport(SimpleNamespace(APP_VERSION='x-performance-lab'),'NY'):raise ValueError('failure')
        self.assertIs(BrowserContext.new_page,original)

if __name__=='__main__':unittest.main(verbosity=2)
