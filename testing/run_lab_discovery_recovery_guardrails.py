"""Bounded transport recovery cannot broaden identity or change source deadlines."""
import json
import ast
import subprocess
from pathlib import Path
import ssl
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c


class RecoveryControls(unittest.TestCase):
    def setUp(self):
        self.trace = []
        self.token = c.IDENTITY_REQUEST_TRACE.set(self.trace)
        self.addCleanup(c.IDENTITY_REQUEST_TRACE.reset, self.token)
        c.IDENTITY_SOURCE_CACHE.clear()

    def fetch(self):
        return c.identity_discovery_fetch('https://example.test/search', 30, stage='test')

    def test_timeout_recovers_once_with_original_deadline_and_records_first_failure(self):
        with patch.object(c, 'identity_fetch', side_effect=[TimeoutError('secret'), b'[]']) as f, \
             patch.object(c.time, 'monotonic', return_value=10), patch.object(c.time, 'sleep'):
            self.assertEqual(self.fetch(), b'[]')
        self.assertEqual(f.call_count, 2)
        self.assertTrue(all(call.args[1] == 30 for call in f.call_args_list))
        self.assertEqual(self.trace[0]['failure_kind'], 'timeout')
        self.assertTrue(self.trace[1]['completed'])
        self.assertNotIn('secret', json.dumps(self.trace))

    def test_second_failure_ends_recovery(self):
        with patch.object(c, 'identity_fetch', side_effect=TimeoutError()) as f, \
             patch.object(c.time, 'monotonic', return_value=10), patch.object(c.time, 'sleep'), self.assertRaises(TimeoutError):
            self.fetch()
        self.assertEqual(f.call_count, 2)

    def test_no_retry_without_remaining_time(self):
        with patch.object(c, 'identity_fetch', side_effect=TimeoutError()) as f, \
             patch.object(c.time, 'monotonic', return_value=29), patch.object(c.time, 'sleep') as wait, self.assertRaises(TimeoutError):
            self.fetch()
        self.assertEqual(f.call_count, 1); wait.assert_not_called()

    def test_tls_invalid_response_and_forbidden_are_not_retried(self):
        for exc in [ssl.SSLError('secret'), URLError(ssl.SSLError('secret')), ValueError('bad response'),
                    HTTPError('https://secret.test', 403, 'secret', {}, None)]:
            with self.subTest(exc=type(exc).__name__), patch.object(c, 'identity_fetch', side_effect=exc) as f, \
                 patch.object(c.time, 'monotonic', return_value=10), self.assertRaises(type(exc)):
                self.fetch()
            self.assertEqual(f.call_count, 1)

    def test_backoff_does_not_violate_retry_after(self):
        for value in ['10', 'Fri, 25 Sep 2026 17:00:00 GMT', 'nan', '-1']:
            exc = HTTPError('https://example.test', 429, '', {'Retry-After':value}, None)
            with patch.object(c, 'identity_fetch', side_effect=exc) as f, \
                 patch.object(c.time, 'monotonic', return_value=10), patch.object(c.time, 'sleep') as wait, self.assertRaises(HTTPError):
                self.fetch()
            self.assertEqual(f.call_count, 1);wait.assert_not_called()

    def test_eligible_http_recovery_is_recorded_and_paced(self):
        exc = HTTPError('https://example.test', 503, '', {'Retry-After':'1'}, None)
        with patch.object(c, 'identity_fetch', side_effect=[exc, b'[]']), \
             patch.object(c.time, 'monotonic', return_value=10), patch.object(c.time, 'sleep') as wait:
            self.fetch()
        wait.assert_called_once_with(1.0)
        self.assertEqual(self.trace[0]['http_status'], 503)

    def test_completed_empty_source_is_not_repeated(self):
        with patch.object(c, 'identity_fetch', return_value=b'[]') as f:
            result = c.identity_ca_names('123456789', time.monotonic()+20)
        self.assertTrue(result['complete']);self.assertEqual(result['names'],[]);f.assert_called_once()

    def test_recovered_california_wrong_ein_cannot_supply_a_name(self):
        body = json.dumps([{'fein':'999999999','entityName':'Wrong Chapter'}]).encode()
        with patch.object(c, 'identity_fetch', side_effect=[TimeoutError(),body]), patch.object(c.time,'sleep'):
            result = c.identity_ca_names('123456789',time.monotonic()+20)
        self.assertEqual(result['names'],[])

    def test_invalid_json_does_not_trigger_recovery(self):
        with patch.object(c, 'identity_fetch', return_value=b'<html>unavailable</html>') as f, self.assertRaises(ValueError):
            c.identity_ca_names('123456789',time.monotonic()+20)
        f.assert_called_once()

    def test_discovery_retains_failure_category_and_elapsed_time(self):
        def source(state, ein, deadline):
            if state == 'CA': raise HTTPError('https://secret.test', 503, 'secret', {}, None)
            return {'source':state,'complete':True,'names':[]}
        with patch.object(c,'IDENTITY_STATES',('CA',)), patch.object(c,'identity_source_result',side_effect=source):
            result=c.discover_organization_names('Example Charity','123456789')
        failure=next(s for s in result['sources'] if s['source']=='CA')
        self.assertEqual(failure['http_status'],503)
        self.assertIn('service_seconds',failure);self.assertTrue(result['partial'])
        self.assertNotIn('secret',json.dumps(result))


class WashingtonProvenanceControls(unittest.TestCase):
    def test_classification_body_unchanged_from_live_baseline(self):
        root=Path(__file__).resolve().parents[1]
        before=ast.parse(subprocess.check_output(['git','show','36a8c466d814b9090fa811ba4f894484264a96c4:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        after=ast.parse((root/'registry_snapshot_server.py').read_text(encoding='utf-8'))
        old=next(n for n in before.body if isinstance(n,ast.FunctionDef) and n.name=='wa_apply_detail_master')
        new=next(n for n in after.body if isinstance(n,ast.FunctionDef) and n.name=='wa_apply_detail_master')
        new.body=[n for n in new.body if not (isinstance(n,ast.Assign) and all(isinstance(t,ast.Attribute)
            and isinstance(t.value,ast.Name) and t.value.id=='result'
            and t.attr in {'verified_registry_ein','identity_anchor','reason_code'} for t in n.targets))]
        self.assertEqual(ast.dump(old),ast.dump(new))

    def result(self, body):
        result=SimpleNamespace(ein='123456789', organization_name='Example Charity',state='WA',
            matched_registry_name='Example Charity (Former Name)', source_url='https://example.test',error='')
        c.wa_apply_detail_master(result,body)
        return result

    def test_detail_ein_survives_alias_changes_and_external_conversion(self):
        org=c.checker.Organization('Example Charity','123456789')
        body='FEIN Number:\n123456789\nStatus:\nActive\nRenewal Date:\n12/31/2027'
        for aliases in [(),('Unrelated Former Name',)]:
            token=c.REVIEWED_NAME_CONTEXT.set({'123456789':aliases})
            try:
                raw=self.result(body);result=c.copy_external_result(org,'WA',raw)
                trace=c.debug_trace_for_result(result,org,'WA',c.public_status(result))
                self.assertEqual(result.verified_registry_ein,'123456789')
                self.assertEqual(result.identity_anchor,'EIN')
                self.assertEqual(trace['accepted_candidate']['reason'],'MATCH_EIN_EXACT')
                self.assertEqual(trace['status_reason_code'],'MATCH_EIN_EXACT')
            finally:c.REVIEWED_NAME_CONTEXT.reset(token)

    def test_missing_or_different_ein_clears_prior_provenance(self):
        for ein in ['', '987654321']:
            r=SimpleNamespace(ein='123456789',verified_registry_ein='123456789',identity_anchor='EIN',reason_code='MATCH_EIN_EXACT')
            c.wa_apply_detail_master(r,f'FEIN Number:\n{ein}\nStatus:\nActive\nRenewal Date:\n12/31/2027')
            self.assertEqual(r.status,'Unable to Confirm');self.assertFalse(r.success)
            self.assertEqual(r.verified_registry_ein,'');self.assertNotEqual(r.identity_anchor,'EIN')


if __name__=='__main__':unittest.main(verbosity=2)
