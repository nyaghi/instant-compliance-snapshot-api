"""Real local synthetic Chromium lease/isolation tests. No registry network."""
import json
import os
from pathlib import Path
import tempfile
import signal
import subprocess
import sys
import time
import unittest
import uuid
from unittest.mock import MagicMock,patch

from deployment.browser_pool import BrowserPool,leased_browser
from playwright.sync_api import sync_playwright

VERSION='fixture-performance-lab'


def forked_pool_fixture(job,output,log,ready,supervisor,env):
    """Real warmed child and owned browser, without registry network."""
    from deployment.queue_engine import prepare_forked_child
    warmed=prepare_forked_child(log,ready,env)
    with sync_playwright() as p:
        browser=warmed.master.launch_lookup_browser(p,headless=True)
        context=browser.new_context()
        before=context.cookies()
        context.add_cookies([{'url':'https://example.test','name':'org','value':job['ein']}])
        page=context.new_page();page.set_content('<b>'+job['ein']+'</b>')
        Path(output).write_text(json.dumps({'pooled':getattr(warmed.master.launch_lookup_browser,'lab_reused',False),
            'cookies_before':before,'identity':page.locator('b').inner_text(),'pid':os.getpid()}))
        if job.get('hang'):time.sleep(120)
        browser.close()


class BrowserLeaseTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)

    def test_unsupported_flags_never_use_shared_browser(self):
        p=MagicMock()
        self.assertIsNone(leased_browser(p,{'headless':True,'args':['--custom-required']}))
        self.assertIsNone(leased_browser(p,{'headless':False}))
        p.chromium.connect.assert_not_called()

    def test_no_pool_configuration_preserves_private_launch(self):
        with patch.dict(os.environ,{},clear=True):self.assertIsNone(leased_browser(MagicMock(),{'headless':True}))

    def test_remote_endpoint_and_old_version_are_rejected_without_connecting(self):
        root=self.root/'cc-lab-browser-fixture';root.mkdir()
        config=root/'config.json';owner=root/'owner.json'
        owner.write_text(json.dumps({'version':VERSION,'token':str(uuid.uuid4()),'job_id':'fixture'}))
        for endpoint,version in [('ws://example.com/browser',VERSION),('ws://127.0.0.1:99/browser','old-performance-lab')]:
            config.write_text(json.dumps({'version':version,'entries':[{'index':0,'endpoint':endpoint}]}))
            p=MagicMock()
            with patch.dict(os.environ,{'CE_APP_VERSION':VERSION,'CE_LAB_BROWSER_POOL_CONFIG':str(config),'CE_LAB_BROWSER_POOL_OWNER':str(owner)}):
                self.assertIsNone(leased_browser(p,{'headless':True}))
            p.chromium.connect.assert_not_called();self.assertFalse((root/'0.lease').exists())

    def test_real_exclusive_leases_cookie_isolation_and_verified_reuse(self):
        pool=BrowserPool(self.root/'cc-lab-browser-real',2,VERSION,local_test=True)
        self.addCleanup(pool.close)
        envs=[pool.owner(self.root/f'owner-{n}.json',str(uuid.uuid4()),str(n)) for n in range(3)]
        with sync_playwright() as p:
            browsers=[]
            for n,env in enumerate(envs[:2]):
                with patch.dict(os.environ,dict(env,CE_APP_VERSION=VERSION)):
                    browser=leased_browser(p,{'headless':True});self.assertIsNotNone(browser)
                context=browser.new_context();self.assertEqual(context.cookies(),[])
                context.add_cookies([{'url':'https://example.test','name':'identity','value':str(n)}])
                page=context.new_page();page.set_content(f'<b>Organization {n}</b>')
                browsers.append((browser,context,page))
            with patch.dict(os.environ,dict(envs[2],CE_APP_VERSION=VERSION)):
                self.assertIsNone(leased_browser(p,{'headless':True}))
            first=browsers[0];first[0].close()
            pool.release(envs[0]['CE_LAB_BROWSER_POOL_OWNER'])
            self.assertEqual(browsers[1][2].locator('b').inner_text(),'Organization 1')
            with patch.dict(os.environ,dict(envs[2],CE_APP_VERSION=VERSION)):
                fresh=leased_browser(p,{'headless':True});self.assertIsNotNone(fresh)
            context=fresh.new_context();self.assertEqual(context.cookies(),[])
            page=context.new_page();page.set_content('<b>New organization</b>')
            self.assertEqual(page.locator('b').inner_text(),'New organization')
            fresh.close();pool.release(envs[2]['CE_LAB_BROWSER_POOL_OWNER'])
            browsers[1][0].close();pool.release(envs[1]['CE_LAB_BROWSER_POOL_OWNER'])
        self.assertFalse(list(pool.root.glob('*.lease')))

    def test_failed_connection_keeps_lease_until_supervisor_cleanup(self):
        root=self.root/'cc-lab-browser-failure';root.mkdir()
        config=root/'config.json';owner=root/'owner.json'
        owner.write_text(json.dumps({'version':VERSION,'token':str(uuid.uuid4()),'job_id':'fixture'}))
        config.write_text(json.dumps({'version':VERSION,'entries':[{'index':0,'endpoint':'ws://127.0.0.1:9/browser'}]}))
        p=MagicMock();p.chromium.connect.side_effect=TimeoutError()
        with patch.dict(os.environ,{'CE_APP_VERSION':VERSION,'CE_LAB_BROWSER_POOL_CONFIG':str(config),'CE_LAB_BROWSER_POOL_OWNER':str(owner)}):
            self.assertIsNone(leased_browser(p,{'headless':True,'timeout':50}))
        self.assertTrue((root/'0.lease').exists());self.assertEqual(p.chromium.connect.call_args.kwargs['timeout'],50)

    def test_unconfirmed_cleanup_cannot_release_lease(self):
        root=self.root/'cc-lab-browser-cleanup';root.mkdir()
        owner=root/'owner.json';owner.write_text(json.dumps({'token':'fixture'}));os.link(owner,root/'0.lease')
        pool=object.__new__(BrowserPool);pool.root=root;pool.entries=[{'index':0}]
        with patch.object(pool,'command',return_value={'remaining':1}):
            with self.assertRaises(RuntimeError):pool.release(owner)
        self.assertTrue((root/'0.lease').exists())

    def test_disabled_browser_cannot_release_lease_until_termination_confirmed(self):
        root=self.root/'cc-lab-browser-disabled';root.mkdir()
        owner=root/'owner.json';owner.write_text(json.dumps({'token':'fixture'}));os.link(owner,root/'0.lease')
        pool=object.__new__(BrowserPool);pool.root=root;pool.entries=[{'index':0,'pid':123}]
        with patch.object(pool,'command',return_value={'remaining':0,'disabled':True}),patch.object(pool,'confirm_stopped',side_effect=RuntimeError('descendants alive')):
            with self.assertRaisesRegex(RuntimeError,'descendants alive'):pool.release(owner)
        self.assertTrue((root/'0.lease').exists())

    def test_killed_client_is_cleaned_without_interrupting_another_job(self):
        pool=BrowserPool(self.root/'cc-lab-browser-interrupted',2,VERSION,local_test=True)
        self.addCleanup(pool.close)
        first=pool.owner(self.root/'first.json',str(uuid.uuid4()),'first')
        second=pool.owner(self.root/'second.json',str(uuid.uuid4()),'second')
        code='''from playwright.sync_api import sync_playwright
from deployment.browser_pool import leased_browser
import time
with sync_playwright() as p:
 b=leased_browser(p,{'headless':True});c=b.new_context();q=c.new_page();q.set_content('<b>interrupt</b>')
 print('READY',flush=True);time.sleep(120)
'''
        env={**os.environ,**second,'CE_APP_VERSION':VERSION}
        with sync_playwright() as p:
            with patch.dict(os.environ,dict(first,CE_APP_VERSION=VERSION)):
                survivor=leased_browser(p,{'headless':True})
            c=survivor.new_context();q=c.new_page();q.set_content('<b>surviving</b>')
            child=subprocess.Popen([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[2],env=env,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=os.name!='nt',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            try:
                self.assertEqual(child.stdout.readline().strip(),'READY')
                if os.name=='nt':
                    result=subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],capture_output=True,timeout=10)
                    self.assertEqual(result.returncode,0)
                else:os.killpg(child.pid,signal.SIGKILL)
                child.wait(timeout=10)
                pool.release(second['CE_LAB_BROWSER_POOL_OWNER'])
                self.assertEqual(q.locator('b').inner_text(),'surviving')
                with patch.dict(os.environ,dict(second,CE_APP_VERSION=VERSION)):
                    fresh=leased_browser(p,{'headless':True});self.assertIsNotNone(fresh)
                context=fresh.new_context();self.assertEqual(context.cookies(),[])
                fresh.close();pool.release(second['CE_LAB_BROWSER_POOL_OWNER'])
            finally:
                if child.poll() is None:child.kill();child.wait(timeout=10)
                child.stdout.close();child.stderr.close()
                survivor.close();pool.release(first['CE_LAB_BROWSER_POOL_OWNER'])

    @unittest.skipUnless(sys.platform.startswith('linux'),'Actual Linux warmed-child integration in build')
    def test_warmed_children_reuse_browser_without_identity_and_cookie_leakage(self):
        from deployment.queue_worker import ForkProcessTree
        pool=BrowserPool(self.root/'cc-lab-browser-warm',1,VERSION)
        self.addCleanup(pool.close)
        for n,hang in enumerate((False,True,False)):
            folder=self.root/str(n);folder.mkdir();output=folder/'result.json'
            owner=pool.owner(folder/'owner.json',str(uuid.uuid4()),str(n))
            env={**os.environ,**owner,'CE_APP_VERSION':VERSION}
            tree=ForkProcessTree({'ein':str(n),'hang':hang},output,folder,env,target=forked_pool_fixture)
            try:
                end=time.monotonic()+15
                while not output.exists() and tree.poll() is None and time.monotonic()<end:time.sleep(.05)
                self.assertTrue(output.exists(),(folder/'task.log').read_text())
                result=json.loads(output.read_text())
                self.assertTrue(result['pooled']);self.assertEqual(result['cookies_before'],[])
                self.assertEqual(result['identity'],str(n))
            finally:
                tree.stop();pool.release(owner['CE_LAB_BROWSER_POOL_OWNER'])
            self.assertFalse(list(pool.root.glob('*.lease')))


if __name__=='__main__':unittest.main()
