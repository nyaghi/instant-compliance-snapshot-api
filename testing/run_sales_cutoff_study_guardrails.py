"""The cutoff study cannot change ordinary Sales or protected environments."""
import time
import unittest
import ast
import subprocess
from pathlib import Path
from unittest.mock import patch

import registry_snapshot_server as cc
from deployment.lab_identity import trial_sales_cutoff
from deployment import durable_queue
from testing.run_final_four_continuation_guardrails import ContinuationControls


class CutoffStudyControls(ContinuationControls):
    def test_signed_trial_handler_delta_is_only_the_connector_budget(self):
        root=Path(__file__).resolve().parents[1]
        baseline=subprocess.check_output(['git','show','df3910f49aff3b3e688479f5bf223d44d93a6d00:registry_snapshot_server.py'],cwd=root).decode('utf-8')
        current=(root/'registry_snapshot_server.py').read_text(encoding='utf-8')
        before,after=ast.parse(baseline),ast.parse(current)
        handler=next(n for n in after.body if isinstance(n,ast.FunctionDef) and n.name=='final_four_connector_request')
        start=next(n for n in handler.body if isinstance(n,ast.If) and ast.unparse(n.test)=='action == \'start\'')
        imported=next(n for n in start.body if isinstance(n,ast.ImportFrom) and n.module=='deployment.lab_identity')
        self.assertEqual([a.name for a in imported.names],['trial_sales_cutoff'])
        index=start.body.index(imported)
        self.assertIsInstance(start.body[index+1],ast.Try)
        self.assertEqual(ast.unparse(start.body[index+1].body[0]),'cutoff = trial_sales_cutoff(payload, identity)')
        self.assertEqual(ast.unparse(start.body[index+1].handlers[0].body[0]),"return (400, {'error': str(exc)})")
        del start.body[index:index+2]
        expires=next(n for n in ast.walk(start) if isinstance(n,ast.IfExp) and isinstance(n.body,ast.Name) and n.body.id=='cutoff')
        self.assertEqual(ast.unparse(expires.test),"mode == 'sales'")
        expires.body=ast.Constant(value=60)
        original=next(n for n in before.body if isinstance(n,ast.FunctionDef) and n.name=='final_four_connector_request')
        self.assertEqual(ast.dump(original),ast.dump(handler))

    def test_defaults_remain_sixty_everywhere(self):
        for identity in (None, {'origin':self.origin}):
            self.assertEqual(trial_sales_cutoff({'mode':'sales'},identity),60)

    def test_override_is_bounded_and_only_disposable_sales(self):
        for value in (None,True,'90',0,61,89,91,300):
            with self.assertRaises(ValueError):
                trial_sales_cutoff({'mode':'sales','sales_cutoff_seconds':value},{'origin':self.origin})
        for change in ({'mode':'standard'},{'kind':'discovery'}):
            with self.assertRaises(ValueError):
                trial_sales_cutoff({'mode':'sales','sales_cutoff_seconds':90,**change},{'origin':self.origin})
        with self.assertRaises(ValueError):
            trial_sales_cutoff({'mode':'sales','sales_cutoff_seconds':90},None)

    def test_queue_keeps_default_fingerprint_and_records_ninety_explicitly(self):
        payload={'organization_name':'Fixture Charity','ein':'123456789','states':['MA'],'mode':'sales'}
        with patch.object(durable_queue,'trial_identity',return_value={'origin':self.origin}):
            plain=durable_queue.normalize_submission(payload,['MA'])
            sixty=durable_queue.normalize_submission({**payload,'sales_cutoff_seconds':60},['MA'])
            ninety=durable_queue.normalize_submission({**payload,'sales_cutoff_seconds':90},['MA'])
            self.assertEqual(plain,sixty)
            self.assertNotIn('sales_cutoff_seconds',plain)
            self.assertEqual(ninety['sales_cutoff_seconds'],90)
        with patch.object(durable_queue,'trial_identity',return_value=None):
            with self.assertRaises(ValueError):
                durable_queue.normalize_submission({**payload,'sales_cutoff_seconds':90},['MA'])

    def test_connector_ninety_keeps_signed_deadline_through_continuation(self):
        with patch.object(cc.time,'time',return_value=1000):
            code,response=self.start(mode='sales',sales_cutoff_seconds=90)
            self.assertEqual(code,200)
            record=cc.ny_connector_unpack(response['check_token'],self.auth['email'],self.auth['device_id'])
            self.assertEqual(record['expires'],1090)
        with patch.object(cc.time,'time',return_value=1061):
            code,second=self.advance(response)
            self.assertEqual(code,200)
            self.assertEqual(second['lookup_remaining_ms'],29000)
        with patch.object(cc.time,'time',return_value=1091):
            self.assertEqual(self.advance(second)[0],410)

    def test_bad_study_input_does_not_start_a_connector_search(self):
        for value in (True,300,'90'):
            self.assertEqual(self.start(mode='sales',sales_cutoff_seconds=value)[0],400)
        self.assertEqual(self.start(mode='standard',sales_cutoff_seconds=90)[0],400)

    def test_seventy_and_eighty_are_explicit_isolated_studies(self):
        for seconds in (70,80):
            self.assertEqual(trial_sales_cutoff({'mode':'sales','sales_cutoff_seconds':seconds},{'origin':self.origin}),seconds)
            with patch.object(cc.time,'time',return_value=1000):
                code,response=self.start(mode='sales',sales_cutoff_seconds=seconds)
                self.assertEqual(code,200)
                record=cc.ny_connector_unpack(response['check_token'],self.auth['email'],self.auth['device_id'])
                self.assertEqual(record['expires'],1000+seconds)


if __name__=='__main__':
    unittest.main()
