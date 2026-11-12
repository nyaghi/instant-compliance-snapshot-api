import json
import time
import unittest
from datetime import date
from unittest.mock import Mock, patch
from PIL import Image, ImageDraw
from deployment.casey_state_repairs import ms_personal_foundation_probe
from deployment import state_snapshots as snapshots
from testing import run_final_four_continuation_guardrails as guardrails
import registry_snapshot_server as a
import base64
import io
import tempfile
from pathlib import Path


NAME = 'Annie E. Casey Foundation'
EIN = '521951681'
INDEXED = 'Annie E. Casey Foundation, Inc. , The'
STREET = '701 St. Paul St.'


class Focused(unittest.TestCase):
    def test_al_signed_source_row_and_exact_office(self):
        t = guardrails.ContinuationControls('test_all_four_complete_through_signed_master_replay')
        t.setUp()
        self.addCleanup(t.doCleanups)
        t.orgs['AL'] = a.checker.Organization(NAME, EIN)
        for street, confirmed in [(STREET, True), ('711 St. Paul St.', False)]:
            row = [INDEXED, '', 'Active', 'Private Foundation', '', '', street, 'Baltimore', 'MD', '21202-2311', '']
            visible = 'Business Lookup Search Records: 1 to 1 of 1 ' + ' '.join(row)
            image = Image.new('RGB', (400, 120), 'white')
            ImageDraw.Draw(image).text((5, 10), visible, fill='black')
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            org = {'ein': EIN, 'street': '701 ST. PAUL STREET', 'city': 'BALTIMORE',
                   'state': 'MD', 'postal_code': '21202', 'address_role': 'organization',
                   'names': ['ANNIE E CASEY FOUNDATION INC']}
            with (tempfile.TemporaryDirectory() as tmp,
                patch.object(snapshots, 'STORE', snapshots.SQLiteStore(Path(tmp) / 'source.db')),
                patch.object(a, 'licensed_charity_names', return_value=([NAME], [])),
                patch.object(a, 'identity_source_result', return_value={'organization_records': [org]})
            ):
                _, x = t.start('AL')
                query = x['query']
                e = dict(state='AL', query=query, complete=True, verification_pending=False,
                         headers=guardrails.AL_HEADERS, rows=[row], total=1)
                ss = dict(query=query, source_url='https://ago.igovsolution.net/online/Lookups/Business.aspx',
                          captured_at=time.time(), public_text=visible, image=base64.b64encode(buffer.getvalue()).decode())
                _, x = t.advance(x, evidence=e, state_snapshot=ss)
                self.assertEqual(x['phase'], 'complete', x)
                r = x['result']
                self.assertEqual(r['status'], 'Current' if confirmed else 'Unable to Confirm', r)
                self.assertFalse(r['matched_registry_identifier'])
                self.assertEqual(r['evidence_capture'], 'saved' if confirmed else 'candidate_only')
                self.assertTrue(r['evidence_url'])
                if confirmed:
                    self.assertIn('Current refers to the private foundation listing', r['comments'])
                    self.assertIn('no charitable solicitation license number', r['comments'])

    def test_ma_discloses_foreign_filing_and_does_not_infer_from_unreadable_activity_record(self):
        state = "Not Doing Business in Mass"
        account = "027225"
        url = "https://masscharities.my.site.com/FilingSearch/sfc/servlet.shepherd/document/download/0695e000007joPsAAI"
        completed = {"record": {"ago_account": account, "ein": EIN, "registry_status": state},
                     "filings": {account: a.ma_public_document_collection(
                        [{"filingYear": "2020", "nameforURL": "FY2020 PC - Form PC/Annual RPT.tiff", "url": url}])},
                     "registration_documents": {account: a.ma_public_document_collection([])}}
        page = Mock()
        page.get_by_role.return_value.all_inner_texts.return_value = []
        page.locator.return_value.inner_text.return_value = f"AG Account Number {account}"
        page.context.request.get.return_value.ok = True
        scan = io.BytesIO()
        Image.new("RGB", (40, 40), "white").save(scan, format="TIFF")
        page.context.request.get.return_value.body.return_value = scan.getvalue()
        ocr = Mock(return_value=([[[[0, 0]] * 4, "FederallD #:04-3381819", .99]], None))
        import sys
        from types import SimpleNamespace
        with (patch.dict(sys.modules, {"rapidocr_onnxruntime": SimpleNamespace(RapidOCR=lambda **kw: ocr)}),
            patch.object(a, "_MA_LEGACY_OCR", ocr)
        ):
            result = a.checker.StateResult(NAME, EIN, "MA", "Current", "")
            evidence = a.ma_read_latest_form_pc(page, result, f"AG Account Number {account}", completed)
            a.annotate_ma_visible_form_pc_due(result, evidence)
            self.assertEqual(result.status_reason, "MA_FORM_PC_ATTACHMENT_IDENTITY_CONFLICT")
            self.assertIn("different EIN", a.comments_for_result(result, "", "Unable to Confirm"))
        with patch.object(a, "ma_read_legacy_form_pc", side_effect=lambda *args, read_progress: (
                read_progress.update(attempted=True, complete=False) or {})):
            evidence = a.ma_read_latest_form_pc(page, result, f"AG Account Number {account}", completed)
            self.assertEqual(evidence, {"registry_status": state, "ago_account": account})

    def test_ms_completed_search_rejects_unrelated_records(self):
        def evidence(query):
            self.assertEqual(query['name'], 'Casey')
            rows = [dict(name='Casey Elementary PTA', identifier='100024135', raw_status='Current - Exempted'),
                    dict(name='Jackson Public School District', identifier='100008268', raw_status='Current - Exempted')]
            return dict(state='MS', query=query, complete=True, verification_pending=False, total=2, rows=rows)
        with patch.object(a, 'trial_identity', return_value={'origin': 'fixture'}):
            result = a.ms_browser_lookup(a.checker.Organization(NAME, EIN), evidence, ['CASEY, ANNIE E. FOUNDATION INC'])
        self.assertEqual(result.status, 'Not Registered')
        self.assertEqual(len(result.queries_attempted), 1)
        self.assertFalse(ms_personal_foundation_probe(NAME, [NAME, 'Verified Different DBA']))
        self.assertFalse(ms_personal_foundation_probe('United Service Organizations', ['United Service Organizations']))

    def test_ms_incomplete_short_query_cannot_prove_absence(self):
        def evidence(query):
            return dict(state='MS', query=query, complete=False, verification_pending=False, total=0, rows=[])
        with patch.object(a, 'trial_identity', return_value={'origin': 'fixture'}), self.assertRaises(ValueError):
            a.ms_browser_lookup(a.checker.Organization(NAME, EIN), evidence)
