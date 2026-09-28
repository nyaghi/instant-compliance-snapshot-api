"""Fixed diagnostic labels cannot change requests, results or leak content."""
import ast
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from playwright.sync_api import sync_playwright
from deployment.queue_engine import FloridaTrace, observe_browser_transport
from deployment.queue_worker import log_browser_failure, log_failure_trace


class FailureLabels(unittest.TestCase):
    def test_fl_same_result_and_no_content(self):
        for status in ['Not Registered', 'Site Not Reachable', 'private-secret']:
            page = Mock(); result = SimpleNamespace(status=status, text='secret')
            original = Mock(return_value=result); org = object(); trace = FloridaTrace()
            self.assertIs(trace.wrap(original)(page, org), result)
            original.assert_called_once_with(page, org)
            self.assertEqual(trace.events[-1]['result_status'], status if status != 'private-secret' else 'other')
            self.assertNotIn('secret', json.dumps(trace.events))

    def test_real_ny_failed_request_keeps_fixed_code_only(self):
        with tempfile.TemporaryDirectory() as folder, sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                context.route('**/*', lambda r: r.abort('connectionreset'))
                with observe_browser_transport(SimpleNamespace(APP_VERSION='x-performance-lab'), 'NY',
                        Path(folder)/'result.trace.json') as trace:
                    page = context.new_page()
                    with self.assertRaises(Exception):
                        page.goto('https://charities-search-api.ag.ny.gov/api/FileNet/RegistryDetail?orgID=secret')
                failed = [r for r in trace.events if r['event']=='browser_failed']
                self.assertEqual(len(failed), 1)
                self.assertEqual(failed[0]['failure'], 'net::ERR_CONNECTION_RESET')
                self.assertNotIn('secret', json.dumps(trace.events))
            finally:
                browser.close()

    def test_deadline_logs_keep_only_allowed_labels(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'result.json'
            for state,suffix,logger in [('FL','.trace.json',log_failure_trace),('NY','.browser.json',log_browser_failure)]:
                rows=[{'event':'browser_failed','route':'details','failure':'net::ERR_FAILED',
                       'result_status':'Not Registered','body':'secret','headers':'secret'},
                      {'event':'browser_failed','failure':'private secret','result_status':'private secret'}]
                output.with_suffix(suffix).write_text(json.dumps(rows))
                with patch('builtins.print') as emit:
                    logger({'job':{'state':state,'id':'fixture'},'output':output}, 'TASK_TIME_LIMIT')
                printed=emit.call_args.args[0]
                self.assertNotIn('secret',printed)
                self.assertIn('net::ERR_FAILED',printed)
                if state=='FL': self.assertIn('Not Registered',printed)

    def test_no_execution_change_outside_passive_observers(self):
        root=Path(__file__).resolve().parents[2]
        from testing.capacity_lab.failure_label_scope import assert_diagnostics_only
        for file in ['deployment/queue_engine.py','deployment/queue_worker.py']:
            assert_diagnostics_only(root,'2afbb10',file)
        for file in ['registry_snapshot_server.py','deployment/durable_queue.py','deployment/queue_schema.sql',
                     'deployment/lab_capacity.py','deployment/performance_lab.py']:
            subprocess.run(['git','diff','--exit-code','2afbb10','--',file],cwd=root,check=True,stdout=subprocess.DEVNULL)


if __name__=='__main__': unittest.main(verbosity=2)
