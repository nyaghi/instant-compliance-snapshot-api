"""Public form transport must preserve WV selection, identity and dates."""
import json
from pathlib import Path
import re
import threading
import unittest
from unittest.mock import patch, MagicMock
import registry_snapshot_server as m

FIX=Path(__file__).resolve().parents[1]/'fixtures/wv-direct-public'


class WestVirginiaDirectTests(unittest.TestCase):
    def setUp(self):
        # Other transport tests intentionally raise before the browser context
        # exists. Isolate admission so those simulated startup failures cannot
        # consume this test's slots.
        slots=patch.object(m,'BROWSER_LOOKUP_SEMAPHORE',threading.BoundedSemaphore(2))
        slots.start();self.addCleanup(slots.stop)
        self.org=m.checker.Organization('Comic Relief, Inc.','010885377')
        self.form=(FIX/'search.html').read_text(encoding='utf-8')
        self.rows=(FIX/'comic-search-all.html').read_text(encoding='utf-8')
        self.detail=(FIX/'comic-detail.html').read_text(encoding='utf-8')
        self.requests=[]

    def lookup(self, rows=None, detail=None, form=None):
        def read(transport, path, fields=None):
            self.requests.append((path,fields))
            text=(detail or self.detail) if path=='CharitiesInformation' else (rows or self.rows) if fields else (form or self.form)
            transport.body=transport.text(text)
            return text
        with patch.object(m.WestVirginiaPublicLookup,'read',read), patch.object(m,'known_names_for_ein',return_value=[]):
            return m.search_wv_public_details(self.org)

    def test_same_rules_select_active_duplicate_and_preserve_dates(self):
        result,body=self.lookup()
        self.assertEqual(result.matched_registry_identifier,'5533')
        self.assertEqual(result.matched_registry_name,'Comic Relief, Inc.')
        self.assertEqual(result.raw_status_text,'Status: Active | Expiration Date: 03/14/2027 | WV ID: 5533')
        self.assertIn('Initial Registration Date:\n03/14/2007',body)
        self.assertIn('Last Registration Date:\n03/14/2026',body)
        dates=m.registration_date_metadata(result,body=body)
        self.assertEqual(dates['registration_date'],'2007-03-14')
        self.assertEqual(dates['renewal_date'],'2026-03-14')
        search=next(fields for path,fields in self.requests if path=='Search' and fields)
        self.assertEqual(search['ddlType'],'1')
        self.assertEqual(search['ddlCharityRatingNational'],'')
        self.assertEqual(search['ddlCharityRatingWV'],'')
        self.assertEqual(search['CharitiesSearch-CharitiesSearch_txtName'],'Comic Relief')
        self.assertEqual(self.requests[-1],('CharitiesInformation',{'CharitiesId':'4703'}))

    def test_incomplete_or_paginated_table_uses_browser(self):
        for source in (self.rows.replace('Page 1 of 1','Page 1 of 2'),
                       self.rows.replace('records 1 to 2 of 2','records 1 to 3 of 3'),
                       self.rows.replace("NavigateLienInfo(4703)",'UnknownLink()')):
            self.assertIsNone(self.lookup(rows=source))

    def test_alphanumeric_public_number_is_not_the_internal_detail_id(self):
        result,_=self.lookup(rows=self.rows.replace('5533','C240415029923'),
                            detail=self.detail.replace('5533','C240415029923'))
        self.assertEqual(result.matched_registry_identifier,'C240415029923')
        self.assertEqual(self.requests[-1],('CharitiesInformation',{'CharitiesId':'4703'}))

    def test_transport_rejects_truncation_redirect_and_expired_budget(self):
        for body,url in ((b'<html>Incomplete','https://erls.wvsos.gov/OnlineCharitiesSearch/Search'),
                         (b'<html>Complete</html>','https://example.org/other')):
            lookup=m.WestVirginiaPublicLookup(m.time.monotonic()+16)
            response=MagicMock();response.status=200;response.url=url
            response.read.return_value=body;response.headers.get_content_charset.return_value='utf-8'
            with patch.object(lookup.opener,'open') as request:
                request.return_value.__enter__.return_value=response
                with self.assertRaises(ValueError):lookup.read('Search')
        lookup=m.WestVirginiaPublicLookup(m.time.monotonic()-1)
        with self.assertRaises(TimeoutError):lookup.read('Search')

    def test_wrong_selected_detail_id_or_name_uses_browser(self):
        for source in (self.detail.replace('5533','9999'),
                       self.detail.replace('Comic Relief, Inc.','Unrelated Local Chapter')):
            self.assertIsNone(self.lookup(detail=source))

    def test_changed_default_filters_do_not_create_false_negative(self):
        self.assertIsNone(self.lookup(form=self.form.replace('new Option("All", "")','new Option("Gold", "4")')))

    def test_no_record_keeps_existing_browser_confirmation(self):
        no_record='<input type="hidden" name="hdnMessage" value="No records found with your search criteria.">'
        self.assertIsNone(self.lookup(rows=no_record))

    def test_timeout_keeps_existing_browser_path(self):
        with patch.object(m.WestVirginiaPublicLookup,'read',side_effect=TimeoutError('response incomplete')):
            self.assertIsNone(m.search_wv_public_details(self.org))
        with patch.object(m,'search_wv_public_details',return_value=None), \
             patch.object(m.checker,'sync_playwright',side_effect=RuntimeError('browser fallback')):
            with self.assertRaisesRegex(RuntimeError,'browser fallback'):
                m.run_state_lookup(self.org.organization_name,self.org.ein,'WV')

    def test_success_skips_browser_and_capture_retains_browser(self):
        value=self.lookup()
        with patch.object(m,'search_wv_public_details',return_value=value), \
             patch.object(m,'response_data_for_lookup',side_effect=lambda r,*a:r), \
             patch.object(m.checker,'sync_playwright',side_effect=RuntimeError('capture browser')):
            self.assertIs(m.run_state_lookup(self.org.organization_name,self.org.ein,'WV'),value[0])
            with self.assertRaisesRegex(RuntimeError,'capture browser'):
                m.run_state_lookup(self.org.organization_name,self.org.ein,'WV',capture_source_snapshot=True)


if __name__=='__main__':unittest.main()
