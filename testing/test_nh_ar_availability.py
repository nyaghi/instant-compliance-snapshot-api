"""No live requests: stale NH and official AR maintenance fail promptly."""
import sys,time,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
from deployment.source_availability import apply

NOTICE=('Maintenance Alert: We apologize for any inconvenience. This website will be temporarily '
        'unavailable due to scheduled maintenance beginning Thursday, November 19, 2026, at 6:00 PM. '
        'Normal operations will resume by Friday, November 20, 2026, at 8:00 AM.')

class AvailabilityTests(unittest.TestCase):
    def test_stale_nh_never_downloads_or_extracts_in_a_customer_lookup(self):
        with patch.object(c,'weekly_asset',return_value=None), \
             patch.object(c,'nh_download_live_pdf_records',side_effect=AssertionError('runtime extraction')) as download:
            result=c.search_nh_live_pdf(c.checker.Organization('YWCA USA, Inc','131624103'))
        download.assert_not_called()
        self.assertFalse(result.success)
        self.assertEqual(result.status_reason,'NH_DATASET_UNAVAILABLE')
        data=apply(dict(state='NH',status=result.status,success=False,status_reason=result.status_reason))
        self.assertEqual(data['status'],'Site Not Reachable')
        self.assertEqual(data['source_availability']['schema'],1)
        self.assertIn('verified New Hampshire registry download',data['comments'])

    def test_fresh_nh_keeps_the_existing_verified_lookup(self):
        records=[{'registry_id':'1','registry_name':'Named Charity'}]*1001
        with patch.object(c,'weekly_asset',return_value=Path('verified')), \
             patch.object(c,'nh_download_live_pdf_records',return_value=(records,'verified source')):
            self.assertEqual(c.nh_live_pdf_records(),(records,'verified source'))

    def test_reviewed_missing_name_cells_do_not_depend_on_unrelated_pdf_rows(self):
        row=c.nh_record_from_cells(['2652','','G','11/15/2026'],source_digest='new weekly PDF')
        self.assertFalse(row['registry_name'])
        self.assertEqual(row['prior_registry_name'],'New England Circle, Inc.')
        with patch.object(c,'nh_live_pdf_records',return_value=([row],'verified source')):
            result=c.search_nh_live_pdf(c.checker.Organization('New England Circle Inc','123456789'))
        self.assertEqual(result.status,'Needs Review')
        self.assertFalse(result.matched_registry_identifier)

    def test_other_missing_name_cells_still_fail(self):
        for cells in [['2653','','G','11/15/2026'],['2652','','G','11/15/2027']]:
            with self.subTest(cells=cells),self.assertRaises(ValueError):
                c.nh_record_from_cells(cells,source_digest='new weekly PDF')

    def test_ar_maintenance_ends_before_a_name_is_submitted(self):
        page=MagicMock();page.locator.return_value.count.return_value=0
        with patch.object(c,'registry_page_body',return_value=NOTICE), \
             patch.object(c,'AR_LAST_LOOKUP_FINISHED',0),patch.object(c.time,'sleep') as delay:
            result=c.search_ar_serialized(page,c.checker.Organization('YWCA USA, Inc','131624103'))
        self.assertEqual(page.goto.call_count,1)
        page.get_by_role.assert_not_called()
        delay.assert_not_called()
        self.assertFalse(result.success)
        data=apply(dict(state='AR',status=result.status,success=False,status_reason=result.status_reason))
        self.assertEqual(data['status'],'Site Not Reachable')
        self.assertIn('scheduled registry maintenance',data['comments'])
        self.assertIn('8:00 AM',result.source_note)

    def test_ar_warning_does_not_disable_a_working_search_form(self):
        page=MagicMock();page.locator.return_value.count.return_value=1
        with patch.object(c,'registry_page_body',return_value=NOTICE):
            self.assertTrue(c.ar_wait_for_search_form(page,100))

    def test_ar_no_results_or_unrelated_maintenance_words_are_not_an_outage(self):
        for body in ['Back to Search Form No Results Found','Charity: Maintenance Alert Foundation',
                     'Maintenance Alert: future maintenance is planned. Search charities now.']:
            with self.subTest(body=body):self.assertFalse(c.ar_maintenance_notice(body))

if __name__=='__main__':unittest.main()
