"""Isolated fixture reproduction using the shipped extension. No live state traffic."""
import json
import sys
import time
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlparse

WORK = Path(__file__).resolve().parents[1]
ROOT = WORK.parents[1]
OUT = ROOT / 'outputs/ny-interruption-repair-20260917'
OUT.mkdir(parents=True, exist_ok=True)
CONTROL = '--control' in sys.argv
RECOVERY = '--expect-recovery' in sys.argv
COUNT = int(next((a.split('=')[1] for a in sys.argv if a.startswith('--sessions=')), '6'))
ACTIVE = '--active' in sys.argv
sys.path.insert(0, str(WORK / 'testing'))
from run_ny_connector_browser import FORM, c
from run_ny_queue_browser import QueueIntegration


class InterruptionReproduction(QueueIntegration):
    @classmethod
    def setUpClass(cls):
        # Test-only navigation shim survives worker termination. It delays only
        # tab creation, so all NY traffic reaches the fixture route before load.
        cls.extension_temp = tempfile.TemporaryDirectory(prefix='cc-ny-restart-fixture-')
        cls.addClassCleanup(cls.extension_temp.cleanup)
        cls.extension_path = Path(cls.extension_temp.name)
        for f in (WORK/'browser-connector').iterdir():
            if f.is_file(): shutil.copy2(f,cls.extension_path/f.name)
        worker = cls.extension_path/'worker.js'
        shim = '''const fixtureCreate=chrome.tabs.create.bind(chrome.tabs);chrome.tabs.create=async options=>{const tab=await fixtureCreate({...options,url:'about:blank'});await new Promise(r=>setTimeout(r,500));await chrome.tabs.update(tab.id,{url:options.url});return tab;};\n'''
        worker.write_text(shim+worker.read_text(encoding='utf-8'),encoding='utf-8')
        super().setUpClass()
        cls.restarted = []
        cls.context.on('serviceworker', lambda worker: cls.restarted.append(worker))
    @classmethod
    def route(cls, route):
        # Stall only the third owned fixture page, allowing two completed cases
        # and four outstanding requests when Chrome's worker is terminated.
        if not CONTROL and not getattr(cls, 'stopped', False) and urlparse(route.request.url).hostname == 'charities-search.ag.ny.gov' and len(cls.trace) >= 2:
            route.fulfill(content_type='text/html', body=FORM.replace("verify.onclick=async()=>{", "verify.onclick=async()=>{await new Promise(r=>setTimeout(r,3000));"))
        else:
            super().route(route)

    def test_six_sessions_two_complete_four_disconnect(self):
        cls = type(self)
        self.reset_repair(True)
        cls.accepted = True; cls.mode = 'positive'; cls.trace = []; cls.failure = ''
        cls.verifies = 0; cls.state_calls = []; cls.searches = 0
        cls.verification_responses = []; cls.search_responses = []; cls.advance_delay = 0
        requested = [{'ein': str(910000000 + i), 'orgName': f'Concurrent Control {i + 1}', 'orgID': f'91-00-{i + 1:02}'} for i in range(COUNT)]
        cls.distinct_rows = {r['ein']: r for r in requested}
        session = Mock(); session.__enter__ = Mock(return_value=session); session.__exit__ = Mock(return_value=False)
        def detail(url, **kwargs):
            row = next(r for r in requested if r['orgID'] == kwargs['params']['orgID'])
            response = Mock(); response.json.return_value = {'success': True, 'statusCode': 200, 'data': {**row, 'regType': 'NFP', 'regStatute': '7A', 'documents': {'Annual Filing for Charitable Organizations': [{'fiscalYearEnd': '12/31/2025'}]}}}
            return response
        session.get.side_effect = detail
        pages = []
        with patch.object(c.curl_requests, 'Session', return_value=session), patch.object(c, 'public_profile_for_ein', return_value={}):
            for index, row in enumerate(requested):
                page = self.context.new_page(); page.goto(c.NY_CONNECTOR_ORIGIN + '/interruption-control')
                page.evaluate("""args => {window.result=null; window.progress=[];
                  CCNYConnector.lookup({...args,onProgress:m=>progress.push(m)}).then(r=>result=r).catch(e=>result={error:e.message});} """, {'organization_name': row['orgName'], 'ein': row['ein'], 'email': 'browser-test@compliance-express.com', 'admin_passcode': c.ADMIN_PASSCODE, 'device_id': f'interruption-{index}'})
                pages.append(page)
            if CONTROL:
                for page in pages:
                    page.wait_for_function('result!==null', timeout=60000)
                results = [page.evaluate('({result,progress})') for page in pages]
                self.assertEqual([r['result']['status'] for r in results], ['Current'] * 6)
                self.assertEqual([r['result']['ein'].replace('-', '') for r in results], [r['ein'] for r in requested])
                self.assertEqual([r['result']['matched_registry_identifier'] for r in results], [r['ein'] for r in requested])
                self.assertEqual(len(self.trace), 6)
                report = {'passed': True, 'fixture_only': True, 'live_state_requests': 0, 'concurrent_sessions': 6, 'distinct_identity_checks': 6, 'results': results}
                (OUT / 'six-session-no-disconnect-control.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
                print(json.dumps({k: v for k, v in report.items() if k != 'results'}), flush=True)
                for page in pages:
                    page.close()
                return
            pages[1].wait_for_function('result!==null', timeout=20000)
            pages[5].wait_for_function("progress.some(m=>m.includes('position'))", timeout=10000)
            if ACTIVE:
                until = time.monotonic() + 15
                while not self.worker.evaluate('!!active?.pending && active?.tab!==null'):
                    assert time.monotonic() < until, 'Active search did not start'
                    pages[0].wait_for_timeout(100)
                pages[0].wait_for_timeout(800)
            before = self.worker.evaluate('({active:!!active,pending:!!active?.pending,waiting:queue.length,repairPhase:repair.phase||"idle"})')
            # Operates solely on the disposable fixture profile created above.
            cdp = self.context.new_cdp_session(pages[0]); versions = []
            cdp.on('ServiceWorker.workerVersionUpdated', lambda event: versions.extend(event['versions']))
            cdp.send('ServiceWorker.enable'); pages[0].wait_for_timeout(100)
            version = next(v for v in reversed(versions) if v.get('scriptURL') == self.worker.url and v.get('runningStatus') == 'running')
            cls.stopped = RECOVERY
            print('Stopping disposable fixture worker',flush=True)
            cdp.send('ServiceWorker.stopWorker', {'versionId': version['versionId']})
            print('Stopped; waiting for restored worker',flush=True)
            cdp.detach()
            for page in pages:
                page.wait_for_function('result!==null', timeout=90000 if RECOVERY else 20000)
            results = [page.evaluate('({result,progress})') for page in pages]
            (OUT / 'recovery-attempt-debug.json').write_text(json.dumps({'results':results,'errors':self.observations,'trace':self.trace},indent=2),encoding='utf-8')
            self.assertEqual([r['result']['status'] for r in results], ['Current'] * COUNT if RECOVERY else ['Current'] * 2 + ['Unable to Confirm'] * (COUNT-2))
            if RECOVERY:
                self.assertEqual([r['result']['ein'].replace('-', '') for r in results], [r['ein'] for r in requested])
                self.assertEqual(len(self.trace), COUNT)
                self.assertEqual(cls.searches, COUNT)
                self.assertEqual(cls.verifies, COUNT)
            else:
                self.assertTrue(all(r['result']['status_reason'] == 'NY_CONNECTOR_INTERRUPTED' for r in results[2:]))
                self.assertEqual(len(self.trace), 2)
            report = {'reproduced': True, 'recovery_enabled': RECOVERY, 'fixture_only': True, 'live_state_requests': 0, 'connector_version': json.loads((WORK / 'browser-connector/manifest.json').read_text())['version'], 'before_disconnect': before, 'completed_before_disconnect': 2, 'failed_after_disconnect': 0 if RECOVERY else 4, 'results': results, 'limitation': 'Deliberate worker termination exercises the failure mechanism. It does not establish why the user browser disconnected.'}
            report.update(concurrent_sessions=COUNT,searches=cls.searches,verifies=cls.verifies)
            (OUT / (f'{COUNT}-session-recovered-active-{ACTIVE}.json' if RECOVERY else 'six-session-disconnect-reproduction.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps({k: v for k, v in report.items() if k != 'results'}), flush=True)
        for page in pages:
            page.close()


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([InterruptionReproduction('test_six_sessions_two_complete_four_disconnect')]))
    sys.exit(not result.wasSuccessful())
