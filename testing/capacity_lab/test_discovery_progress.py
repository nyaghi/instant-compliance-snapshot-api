"""Collector completion evidence cannot change names or release unfinished work."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from deployment.queue_engine import DiscoveryProgress, execute
from deployment.queue_worker import Supervisor


class ProgressTests(unittest.TestCase):
    def job(self):
        return {'id':'job','token':'token','state':'@discovery','version':'test',
                'resources':['CO','MI','WA','IRS'],
                'payload':{'organization_name':'Fixture','ein':'123456789'}}

    def test_fast_source_released_only_after_return_slow_source_stays_held(self):
        entered, finish = threading.Event(), threading.Event()
        with tempfile.TemporaryDirectory() as folder:
            progress=DiscoveryProgress(Path(folder)/'result.json',self.job())
            def source(state,*args):
                if state=='MI': entered.set(); self.assertTrue(finish.wait(5))
                return {'source':state,'names':[state+' verified name']}
            master=SimpleNamespace(APP_VERSION='test',identity_source_result=source)
            def discover(name,ein):
                with ThreadPoolExecutor(2) as workers:
                    slow=workers.submit(master.identity_source_result,'MI',ein,999)
                    fast=workers.submit(master.identity_source_result,'CO',ein,999)
                    a=fast.result(); self.assertTrue(entered.wait(5))
                    self.assertEqual(json.loads(progress.path.read_text())['completed'],['CO'])
                    finish.set()
                    return [a,slow.result()]
            master.discover_organization_names=discover
            self.assertEqual(execute(master,self.job(),progress),[
                {'source':'CO','names':['CO verified name']},{'source':'MI','names':['MI verified name']}])
            self.assertIs(master.identity_source_result,source)
            self.assertEqual(json.loads(progress.path.read_text())['completed'],['CO','MI'])

    def test_irs_unknown_sources_and_missing_output_do_not_release(self):
        with tempfile.TemporaryDirectory() as folder:
            progress=DiscoveryProgress(Path(folder)/'result.json',self.job())
            progress('IRS'); progress('XX')
            self.assertFalse(progress.path.exists())
            progress('WA'); progress('IRS')
            self.assertEqual(json.loads(progress.path.read_text()),{'id':'job','token':'token','completed':['WA']})
        progress('MI')  # Removed directory cannot make a lookup fail.

    def test_collector_errors_preserved_and_observer_errors_are_nonfatal(self):
        def source(*args): raise ValueError('Original source error')
        master=SimpleNamespace(APP_VERSION='test',identity_source_result=source)
        master.discover_organization_names=lambda *args:master.identity_source_result('CO')
        observer=Mock(side_effect=OSError('optional observation failed'))
        with self.assertRaisesRegex(ValueError,'Original source error'):execute(master,self.job(),observer)
        self.assertIs(master.identity_source_result,source)
        observer.assert_called_once_with('CO')

    def test_supervisor_fences_evidence_and_retries_failed_update(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'result.json';path=output.with_suffix('.sources.json')
            supervisor=object.__new__(Supervisor);supervisor.id='worker';supervisor.queue=Mock()
            run={'job':self.job(),'output':output}
            for bad in ({'id':'other','token':'token','completed':['CO']},
                        {'id':'job','token':'stale','completed':['CO']},
                        {'id':'job','token':'token','completed':'CO'}):
                path.write_text(json.dumps(bad));supervisor.collect_discovery_progress(run)
            supervisor.queue.release_discovery_sources.assert_not_called()
            path.write_text(json.dumps({'id':'job','token':'token','completed':['CO']}))
            supervisor.queue.release_discovery_sources.side_effect=[OSError('DB unavailable'),True]
            supervisor.collect_discovery_progress(run);self.assertNotIn('released_sources',run)
            supervisor.collect_discovery_progress(run);supervisor.collect_discovery_progress(run)
            self.assertEqual(supervisor.queue.release_discovery_sources.call_count,2)
            self.assertEqual(run['released_sources'],['CO'])
            run['stop_reason']='CANCELED';path.write_text(json.dumps({'id':'job','token':'token','completed':['MI']}))
            supervisor.collect_discovery_progress(run)
            self.assertEqual(supervisor.queue.release_discovery_sources.call_count,2)


if __name__=='__main__':unittest.main(verbosity=2)
