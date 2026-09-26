"""Linux build gate: actual forkserver isolation and process-tree termination.

Public registries are stubbed; normalization and the task lifetime are real.
Runs in a separate build process, never in the live supervisor.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]


def fixture(job,output,log,ready,supervisor,env):
    from deployment.queue_engine import prepare_forked_child,run_job
    warmed=prepare_forked_child(log,ready,env)
    master=warmed.master
    nh_rows,_=master.nh_download_live_pdf_records()
    nh_first=nh_rows[0]['registry_name']
    # A task mutation must never leak back into the fork template or next task.
    nh_rows[0]['registry_name']='CHILD-ONLY-MUTATION'
    ks=master.load_ks_weekly_checker()
    hits=ks.records_from_workbook_bytes.cache_info().hits
    ks.load_live_records()
    ks_reused=ks.records_from_workbook_bytes.cache_info().hits>hits
    def blocked(*args,**kwargs):raise AssertionError('No network in warm isolation controls')
    socket.getaddrinfo=blocked
    def registry(name,ein,state):
        prior=getattr(master,'_warm_test_previous_organization',None)
        master._warm_test_previous_organization=ein
        if job.get('hang'):
            child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
            Path(output+'.descendant').write_text(str(child.pid))
            time.sleep(60)
        return {'ein':ein,'state':state,'status':'Current','app_version':master.APP_VERSION,
            'matched_registry_name':name,'aliases':master.known_names_for_ein(ein),
            'registration_date':'2001-02-03','last_renewal_date':'2025-12-31',
            'source_first_name':nh_first,'ks_reused':ks_reused,'previous_organization':prior,'pid':os.getpid(),'private_group':os.getpgrp()==os.getpid(),
            'secret_keys_present':[k for k in ('CE_LAB_DATABASE_URL','CE_TEST_DATABASE_URL','RENDER_API_KEY') if k in os.environ],
            'context_before':dict(master.REVIEWED_NAME_CONTEXT.get())}
    with patch.object(master,'run_single_state_lookup_reliably',side_effect=registry):
        run_job(job,output,supervisor_pid=job.get('test_supervisor',supervisor),warmed=warmed)


def fail_before_ready(*args):
    raise RuntimeError('Intentional pre-readiness failure')


@unittest.skipUnless(sys.platform.startswith('linux'),'Linux forkserver controls run in the Render build')
class WarmEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config=json.loads((ROOT/'deployment/performance-lab-env.json').read_text())
        # Deterministic lab-only test environment; no actual credential needed.
        config.update(CE_LAB_DURABLE_QUEUE='0',CE_LAB_ACCESS_KEY='offline-warm-control-'+'x'*40,
            RENDER_SERVICE_ID='srv-d8u0hsu7r5hc73aqfsg0')
        os.environ.update(config)
        cls.env=dict(os.environ)
        for key in ('CE_LAB_DATABASE_URL','CE_TEST_DATABASE_URL','RENDER_API_KEY'):
            cls.env.pop(key,None)
        cls.version=config['CE_APP_VERSION']

    def job(self,ein='123456789',aliases=None,**kwargs):
        return {'state':'CO','version':self.version,'run_seconds':15,
            '_deadline_monotonic':time.monotonic()+15,
            'payload':{'ein':ein,'organization_name':'Fixture '+ein,'alternate_names':aliases or []},**kwargs}

    def start(self,folder,job,entry=fixture):
        from deployment.queue_worker import ForkProcessTree
        output=Path(folder)/'result.json'
        tree=ForkProcessTree(job,output,folder,self.env,target=entry)
        self.addCleanup(tree.stop)
        return tree,output

    def result(self,folder,job):
        tree,output=self.start(folder,job)
        end=time.monotonic()+10
        while not output.exists() and tree.poll() is None and time.monotonic()<end:time.sleep(.02)
        self.assertTrue(output.exists(),(Path(folder)/'task.log').read_text())
        result=json.loads(output.read_text())
        tree.stop()
        return result

    def test_pristine_template_distinct_processes_and_preserved_result_fields(self):
        results=[]
        for ein,aliases in [('123456789',['Reviewed DBA']),('987654321',[])]:
            with tempfile.TemporaryDirectory() as folder:results.append(self.result(folder,self.job(ein,aliases)))
        self.assertNotEqual(results[0]['pid'],results[1]['pid'])
        self.assertEqual(results[0]['lab_task_metrics']['template_pid'],results[1]['lab_task_metrics']['template_pid'])
        for r in results:
            self.assertTrue(r['lab_task_metrics']['engine_preloaded']);self.assertTrue(r['private_group'])
            self.assertNotEqual(r['source_first_name'],'CHILD-ONLY-MUTATION');self.assertTrue(r['ks_reused'])
            self.assertIsNone(r['previous_organization']);self.assertEqual(r['secret_keys_present'],[])
            self.assertEqual(r['registration_date'],'2001-02-03');self.assertEqual(r['last_renewal_date'],'2025-12-31')
            self.assertEqual(list(r['context_before']),[r['ein'].replace('-','')])
        self.assertEqual(results[0]['aliases'],['Reviewed DBA']);self.assertEqual(results[1]['aliases'],[])

    def test_cancellation_kills_browser_descendants_before_release(self):
        from deployment.queue_worker import process_running,group_running
        with tempfile.TemporaryDirectory() as folder:
            tree,output=self.start(folder,self.job(hang=True))
            descendant=Path(str(output)+'.descendant');end=time.monotonic()+8
            while not descendant.exists() and time.monotonic()<end:time.sleep(.02)
            self.assertTrue(descendant.exists());pid=int(descendant.read_text())
            self.assertTrue(process_running(pid));tree.stop()
            self.assertFalse(process_running(pid));self.assertFalse(group_running(tree.pid))
            self.assertFalse(output.exists())

    def test_absolute_budget_includes_startup(self):
        from deployment.queue_worker import group_running
        with tempfile.TemporaryDirectory() as folder:
            tree,output=self.start(folder,self.job(hang=True,_deadline_monotonic=time.monotonic()+1))
            end=time.monotonic()+5
            while tree.poll() is None and time.monotonic()<end:time.sleep(.05)
            self.assertIsNotNone(tree.poll());tree.stop()
            self.assertFalse(group_running(tree.pid));self.assertFalse(output.exists())

    def test_lost_supervisor_terminates_child(self):
        with tempfile.TemporaryDirectory() as folder:
            tree,output=self.start(folder,self.job(hang=True,test_supervisor=99999999))
            end=time.monotonic()+4
            while tree.poll() is None and time.monotonic()<end:time.sleep(.05)
            self.assertIsNotNone(tree.poll());self.assertFalse(output.exists())
            tree.stop()

    def test_bad_version_and_unsupported_state_cannot_write_result(self):
        for change in ({'version':'wrong'},{'state':'XX'}):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                tree,output=self.start(folder,self.job(**change));end=time.monotonic()+5
                while tree.poll() is None and time.monotonic()<end:time.sleep(.02)
                self.assertIsNotNone(tree.poll());self.assertFalse(output.exists());tree.stop()

    def test_failed_start_does_not_poison_next_job(self):
        from deployment.queue_worker import ForkProcessTree
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises((EOFError,RuntimeError)):
                ForkProcessTree(self.job(),Path(folder)/'result.json',folder,self.env,target=fail_before_ready)
            self.assertEqual(self.result(folder,self.job())['status'],'Current')


if __name__=='__main__':unittest.main(verbosity=2)
