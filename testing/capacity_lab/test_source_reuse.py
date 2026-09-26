"""Parsed public source reuse must not reuse status or bypass freshness."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import registry_snapshot_server as c

class SourceReuseTests(unittest.TestCase):
    def setUp(self):
        c.nh_records_from_snapshot_bytes.cache_clear()

    def payload(self, name='Example Relief', count=1000):
        # Parse is stubbed here to isolate byte-keying/reconciliation; real source
        # equivalence is tested separately below.
        return json.dumps({'source_sha256':'pdf-one','source_record_count':count,
            'updated_label':'September 20, 2026','records':[[name]]*count}).encode()

    def test_same_bytes_parse_once_changed_bytes_reparse(self):
        with patch.object(c,'nh_record_from_cells',side_effect=lambda row: {'registry_name':row[0]}) as parser:
            first = c.nh_records_from_snapshot_bytes(self.payload(), 'pdf-one')
            self.assertIs(first,c.nh_records_from_snapshot_bytes(self.payload(),'pdf-one'))
            self.assertEqual(parser.call_count,1000)
            changed=c.nh_records_from_snapshot_bytes(self.payload('Replacement'), 'pdf-one')
            self.assertEqual(parser.call_count,2000)
            self.assertEqual(changed[0][0]['registry_name'],'Replacement')
            with self.assertRaises(ValueError):
                c.nh_records_from_snapshot_bytes(self.payload(),'different-pdf')

    def test_bad_count_or_label_never_cached_as_valid(self):
        for change in ({'source_record_count':999},{'updated_label':''}):
            value=json.loads(self.payload());value.update(change)
            with patch.object(c,'nh_record_from_cells',return_value={}), self.assertRaises(ValueError):
                c.nh_records_from_snapshot_bytes(json.dumps(value).encode(),'pdf-one')
        self.assertEqual(c.nh_records_from_snapshot_bytes.cache_info().currsize,0)

    def test_verified_snapshot_refresh_does_not_return_legacy_global(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);pdf=root/'source.pdf';snap=root/'records.json';pdf.write_bytes(b'one')
            def write(name):
                p=json.loads(self.payload(name));p['source_sha256']=hashlib.sha256(pdf.read_bytes()).hexdigest()
                snap.write_text(json.dumps(p))
            write('First')
            with patch.object(c,'weekly_asset',side_effect=lambda state,path: snap if path.endswith('.json') else pdf), \
                 patch.object(c,'nh_record_from_cells',side_effect=lambda row: {'registry_name':row[0]}), \
                 patch.object(c,'NH_LIVE_PDF_RECORDS',[{'registry_name':'old global'}]), \
                 patch.object(c,'NH_LIVE_PDF_LOADED_AT',c.time.time()):
                self.assertEqual(c.nh_live_pdf_records()[0][0]['registry_name'],'First')
                write('Second')
                self.assertEqual(c.nh_live_pdf_records()[0][0]['registry_name'],'Second')
                pdf.write_bytes(b'changed')
                with self.assertRaises(ValueError):c.nh_live_pdf_records()

    def test_expired_manifest_cannot_use_warmed_records(self):
        c.nh_records_from_snapshot_bytes(self.payload(count=0),'pdf-one')
        with patch.object(c,'weekly_asset',return_value=None), \
             patch.object(c,'NH_LIVE_PDF_RECORDS',[{}]*1000), \
             patch.object(c,'NH_LIVE_PDF_LOADED_AT',c.time.time()), \
             patch.object(c,'nh_download_live_pdf_records',side_effect=RuntimeError('source unavailable')):
            result=c.search_nh_live_pdf(c.checker.Organization('No Record Control','000000001'))
            self.assertFalse(result.success);self.assertEqual(result.status,'Site Not Reachable')

    def test_real_snapshot_is_identical_to_original_parser(self):
        p=c.weekly_asset('NH','downloadable-data/NH-records.json')
        self.assertIsNotNone(p)
        payload=json.loads(p.read_bytes())
        expected=[c.nh_record_from_cells(row) for row in payload['records']]
        actual,label=c.nh_download_live_pdf_records()
        self.assertEqual(actual,expected)
        self.assertIn(payload['updated_label'],label)

    def test_la_valid_source_does_not_launch_browser(self):
        for status in ('Current','Not Registered'):
            result=c.checker.StateResult('Control','000000001','LA',status,'');result.success=True
            with patch.object(c,'weekly_asset',return_value=Path('verified')), \
                 patch.object(c,'search_la_downloaded_export',return_value=result) as search, \
                 patch.object(c,'response_data_for_lookup',side_effect=lambda r,*a:r), \
                 patch.object(c.checker,'sync_playwright',side_effect=AssertionError('Unneeded browser')):
                self.assertIs(c.run_state_lookup('Control','000000001','LA'),result)
                self.assertIsNone(search.call_args.args[0])

    def test_la_missing_file_does_not_download_without_browser(self):
        with patch.object(c,'weekly_asset',return_value=None), \
             patch.object(c,'la_download_registered_charities_export',side_effect=AssertionError('No browser')):
            result=c.search_la_downloaded_export(None,c.checker.Organization('Control','000000001'))
        self.assertFalse(result.success);self.assertNotEqual(result.status,'Not Registered')

    def test_va_direct_result_and_failure_preserved_without_browser(self):
        for status in ('Current','Not Registered','Site Not Reachable'):
            result=c.checker.StateResult('Control','000000001','VA',status,'')
            result.raw_status_text=status;result.success=status!='Site Not Reachable'
            with patch.object(c,'search_va_direct',return_value=result), \
                 patch.object(c,'response_data_for_lookup',side_effect=lambda r,*a:r), \
                 patch.object(c.checker,'sync_playwright',side_effect=AssertionError('Unused browser')):
                self.assertIs(c.run_state_lookup('Control','000000001','VA'),result)
        with patch.object(c,'search_va_direct',side_effect=RuntimeError('HTTP unavailable')), \
             patch.object(c,'response_data_for_lookup',side_effect=lambda r,*a:r):
            result=c.run_state_lookup('Control','000000001','VA')
        self.assertFalse(result.success);self.assertEqual(result.status,'Site Not Reachable')
        self.assertEqual(result.error,'HTTP unavailable')

    def test_matching_status_and_other_states_unchanged(self):
        from testing.capacity_lab.parsing_scope import restore_parsing_optimization
        root=Path(__file__).resolve().parents[2]
        old=ast.parse(subprocess.check_output(['git','show','433927e:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        new=ast.parse((root/'registry_snapshot_server.py').read_text(encoding='utf-8'))
        restore_parsing_optimization(new)
        self.assertEqual(ast.dump(old),ast.dump(new))

if __name__=='__main__':unittest.main()
