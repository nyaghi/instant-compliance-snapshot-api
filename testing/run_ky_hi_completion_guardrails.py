"""Partial-source and concurrent-reader controls for the KY/HI release."""
import concurrent.futures
import io
import json
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from reportlab.pdfgen import canvas
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

EIN = '237076117'
IDS = ['201313209349305154','201413209349305155','201513209349305156']
LATEST = '202613209349305157'

def index(ein=EIN):
    return ''.join(f'/organizations/{ein}/{oid}/full ' for oid in IDS).encode()

def header(ein=EIN, name='Friends of Sheba Medical Center, Inc.'):
    prefix = '/ReturnHeader[1]/Filer[1]/'
    return (f'<span id="{prefix}EIN[1]">{ein}</span>'
            f'<span id="{prefix}BusinessName[1]/BusinessNameLine1Txt[1]">{name}</span>').encode()

def period(ein='208084828', end='2025-09-30'):
    return {'ein':ein,'tax_year_label':2024,'period_begin':'2024-10-01','period_end':end,'source_url':'https://state/return.pdf'}

def page(ein='208084828'):
    return SimpleNamespace(content=lambda:f'<div id="irs_2024"></div><a rel="/charity/attachments/irs/{ein}/2024/return.pdf">Attachment_IRSForm_1</a>', url=f'https://charity.ehawaii.gov/charity/{ein}/details.html')

class HistoryControls(unittest.TestCase):
    def setUp(self):
        c.IRS_HISTORY_HEADER_CACHE.clear(); c.IRS_HISTORY_INDEX_CACHE.clear(); c.IDENTITY_SOURCE_CACHE.clear()
        self.token = c.REVIEWED_NAME_CONTEXT.set({})
    def tearDown(self):
        c.REVIEWED_NAME_CONTEXT.reset(self.token)
        c.IRS_HISTORY_HEADER_CACHE.clear(); c.IRS_HISTORY_INDEX_CACHE.clear(); c.IDENTITY_SOURCE_CACHE.clear()

    def test_discovery_keeps_third_header_after_old_six_second_limit(self):
        clock = [100.0]
        payload = {'organization':{'ein':EIN,'name':'American Friends of Sheba Medical Center','latest_object_id':LATEST}}
        def fetch(url, deadline, **kwargs):
            if '/api/' in url: return json.dumps(payload).encode()
            clock[0] += 2.2
            if clock[0] >= deadline: raise TimeoutError('source budget expired')
            return index() if '/organizations/' in url else header(name='Former Name' if IDS[-1] in url else 'Current Name')
        with patch.object(c.time,'monotonic',side_effect=lambda:clock[0]), patch.object(c,'identity_fetch',side_effect=fetch), patch.object(c,'irs_return_header',return_value={'names':[],'dba_disclosed':False}):
            found = c.identity_irs_names(EIN,160.0)
        self.assertTrue(found['historical_complete']); self.assertEqual(found['historical_returns_checked'],3)
        self.assertIn('Former Name',[n['name'] for n in found['names']])
        self.assertLess(clock[0],160)

    def test_failed_header_retries_without_refetching_successful_headers(self):
        calls = {}
        def fetch(url, deadline, **kwargs):
            calls[url] = calls.get(url,0)+1
            if '/organizations/' in url: return index()
            if IDS[-1] in url and calls[url] == 1: raise TimeoutError('temporary retrieval failure')
            return header()
        with patch.object(c,'identity_fetch',side_effect=fetch):
            found = c.identity_irs_historical_names(EIN,LATEST,time.monotonic()+10)
        self.assertTrue(found['historical_complete']); self.assertEqual(sorted(calls.values()),[1,1,1,2])
        with patch.object(c,'identity_fetch',side_effect=AssertionError('Verified headers should be reused')):
            again = c.identity_irs_historical_names(EIN,LATEST,time.monotonic()+10)
        self.assertEqual(found['names'],again['names'])

    def test_failed_sibling_cannot_erase_verified_former_name(self):
        def fetch(url,deadline,**kwargs):
            if '/organizations/' in url:return index()
            if IDS[-1] in url:raise TimeoutError('unavailable')
            return header()
        with patch.object(c,'identity_fetch',side_effect=fetch):
            first = c.identity_irs_historical_names(EIN,LATEST,time.monotonic()+10)
        with patch.object(c,'identity_fetch',side_effect=TimeoutError('unavailable')):
            second = c.identity_irs_historical_names(EIN,LATEST,time.monotonic()+10)
        self.assertFalse(second['historical_complete']);self.assertEqual(first['names'],second['names'])
        self.assertEqual(second['historical_returns_checked'],2)

    def test_wrong_ein_and_blocked_index_are_never_cached_as_completed(self):
        with patch.object(c,'identity_fetch',side_effect=lambda url,*a,**k:index() if '/organizations/' in url else header('999999999')):
            found=c.identity_irs_historical_names(EIN,LATEST,time.monotonic()+10)
        self.assertFalse(found['historical_complete']);self.assertEqual(found['names'],[])
        self.assertEqual(c.IRS_HISTORY_HEADER_CACHE,{})
        c.IRS_HISTORY_INDEX_CACHE.clear()
        with patch.object(c,'identity_fetch',return_value=b'<html>Verify you are human</html>'):
            with self.assertRaises(ValueError):c.identity_irs_historical_names(EIN,LATEST,time.monotonic()+10)
        self.assertEqual(c.IRS_HISTORY_INDEX_CACHE,{})

    def test_fifteen_histories_keep_names_bound_to_requested_eins(self):
        local=threading.local()
        def fetch(url,*args,**kwargs):
            return index(local.ein) if '/organizations/' in url else header(local.ein,'Former Name '+local.ein)
        def run(i):
            local.ein=f'12{i:07}'
            return local.ein,c.identity_irs_historical_names(local.ein,LATEST,time.monotonic()+10)
        with patch.object(c,'identity_fetch',side_effect=fetch),concurrent.futures.ThreadPoolExecutor(max_workers=15) as pool:
            for ein,found in pool.map(run,range(15)):
                self.assertTrue(found['historical_complete']);self.assertTrue(all(n['name'].endswith(ein) for n in found['names']))

    def initial_negative(self):
        r=c.checker.StateResult('American Friends of Sheba Medical Center',EIN,'KY','Not Registered','')
        c.IDENTITY_SOURCE_CACHE[c.identity_source_cache_key('IRS',EIN)]=(time.time()+60,{'historical_complete':False,'names':[]})
        return r

    def test_ky_incomplete_history_recovers_exact_verified_former_name(self):
        org=c.checker.Organization('American Friends of Sheba Medical Center',EIN)
        refreshed={'complete':True,'historical_complete':True,'names':[c.identity_candidate('Friends of Sheba Medical Center, Inc.','IRS via ProPublica','Historical Form 990 filer legal name','https://source',historical=True)]}
        with patch.object(c,'identity_irs_names',return_value=refreshed),patch.object(c,'load_ky_snapshot_records',return_value=[('15002','Friends of Sheba Medical Center, Inc.','','')]):
            found=c.ky_recover_incomplete_discovery(org,self.initial_negative())
        self.assertEqual(found.matched_registry_identifier,'15002');self.assertNotEqual(c.public_status(found),'Not Registered')
        self.assertEqual(c.known_names_for_ein(EIN),[])

    def test_ky_still_incomplete_history_does_not_become_negative(self):
        with patch.object(c,'identity_irs_names',side_effect=TimeoutError):
            found=c.ky_recover_incomplete_discovery(c.checker.Organization('Input',EIN),self.initial_negative())
        self.assertEqual(found.status,'Unable to Verify');self.assertEqual(found.status_reason,'KY_IDENTITY_DISCOVERY_INCOMPLETE')

    def test_completed_history_no_match_remains_negative(self):
        with patch.object(c,'identity_irs_names',return_value={'historical_complete':True,'complete':True,'names':[]}):
            found=c.ky_recover_incomplete_discovery(c.checker.Organization('Input',EIN),self.initial_negative())
        self.assertEqual(c.public_status(found),'Not Registered')

    def test_completed_discovery_and_positive_result_do_not_add_calls(self):
        org=c.checker.Organization('Input',EIN)
        with patch.object(c,'identity_irs_names',side_effect=AssertionError('unnecessary recovery')):
            positive=self.initial_negative();positive.status='Current'
            self.assertIs(c.ky_recover_incomplete_discovery(org,positive),positive)
            c.IDENTITY_SOURCE_CACHE.clear()
            negative=c.checker.StateResult('Input',EIN,'KY','Not Registered','')
            self.assertIs(c.ky_recover_incomplete_discovery(org,negative),negative)

class HawaiiControls(unittest.TestCase):
    def setUp(self):c.HI_DOCUMENT_PERIOD_CACHE.clear();c.TAX_PERIOD_EVIDENCE_CACHE.clear()
    def tearDown(self):c.HI_DOCUMENT_PERIOD_CACHE.clear();c.TAX_PERIOD_EVIDENCE_CACHE.clear()

    def test_incomplete_attachment_cannot_use_calendar_assumption(self):
        for reason in ['download timeout','PDF lock busy','OCR deadline','HTML instead of PDF']:
            with self.subTest(reason=reason),patch.object(c,'hi_attachment_period',side_effect=c.FilingPeriodReadIncomplete(reason)),patch.object(c,'irs_period_for_label',return_value={}):
                found=c.hi_public_filing_period(page(),'20-8084828')
            self.assertTrue(found['period_unconfirmed']);self.assertFalse(found.get('period_assumed'))

    def test_same_year_irs_evidence_can_rescue_incomplete_attachment(self):
        with patch.object(c,'hi_attachment_period',side_effect=c.FilingPeriodReadIncomplete('timeout')),patch.object(c,'irs_period_for_label',return_value=period()):
            found=c.hi_public_filing_period(page(),'20-8084828')
        self.assertEqual(found['period_end'],'2025-09-30');self.assertFalse(found.get('period_assumed'))

    def test_document_cache_requires_same_bytes_year_ein_and_url(self):
        with patch.object(c,'identity_fetch',side_effect=[b'%PDF first',b'%PDF first',b'%PDF replacement']),patch.object(c,'form990_pdf_period',side_effect=[period(),c.FilingPeriodReadIncomplete('unreadable new document')]) as parse:
            a=c.hi_attachment_period(page().content(),'208084828',2024,time.monotonic()+10)
            b=c.hi_attachment_period(page().content(),'208084828',2024,time.monotonic()+10)
            self.assertEqual(a,b);self.assertEqual(parse.call_count,1)
            with self.assertRaises(c.FilingPeriodReadIncomplete):c.hi_attachment_period(page().content(),'208084828',2024,time.monotonic()+10)
        self.assertEqual(parse.call_count,2)

    def test_unreadable_pdf_and_busy_text_reader_are_incomplete(self):
        with self.assertRaises(c.FilingPeriodReadIncomplete):c.form990_pdf_period(b'<html>Loading</html>','208084828',2024,'https://state',require_complete=True)
        body=io.BytesIO();pdf=canvas.Canvas(body);pdf.drawString(20,750,'Form 990 for 2024 EIN 20-8084828');pdf.save()
        lock=SimpleNamespace(acquire=lambda **kwargs:False)
        with patch.object(c,'IRS_PDF_TEXT_LOCK',lock):
            with self.assertRaises(c.FilingPeriodReadIncomplete):c.form990_pdf_period(body.getvalue(),'208084828',2024,'https://state',require_complete=True)

    def test_completely_read_undated_same_ein_header_keeps_disclosed_assumption(self):
        body=io.BytesIO();pdf=canvas.Canvas(body);pdf.drawString(20,750,'Form 990 for 2024 EIN 20-8084828');pdf.save()
        with patch.object(c,'identity_fetch',return_value=body.getvalue()),patch.object(c,'irs_period_for_label',return_value={}):
            found=c.hi_public_filing_period(page(),'20-8084828')
        self.assertTrue(found['period_assumed']);self.assertEqual(found['period_end'],'2024-12-31')

    def test_fifteen_ocr_reads_wait_for_capacity_without_ein_mixups(self):
        local=threading.local();barrier=threading.Barrier(15)
        def row(text):return ([[0,0],[900,0],[900,10],[0,10]],text,.999)
        def title(*args,**kwargs):time.sleep(.09);return [row('Form 8879-TE')],None
        def read(*args,**kwargs):return [row(f'Form 8879-TE EIN {local.ein} For fiscal year beginning OCT 1, 2024 and ending SEP 30, 2025')],None
        def run(i):
            local.ein=f'12{i:07}';barrier.wait()
            return local.ein,c.irs_scanned_header_period([(0,Image.new('RGB',(1000,100),'white'))],local.ein,2024,'https://state',time.monotonic()+8,require_complete=True)
        with patch.object(c,'IRS_HEADER_TITLE_OCR',side_effect=title),patch.object(c,'IRS_HEADER_OCR',side_effect=read),concurrent.futures.ThreadPoolExecutor(max_workers=15) as pool:
            for ein,found in pool.map(run,range(15)):
                self.assertEqual(found['ein'],ein);self.assertEqual(found['period_end'],'2025-09-30')

if __name__=='__main__':unittest.main(verbosity=2)
