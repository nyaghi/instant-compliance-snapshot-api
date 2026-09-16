"""Alternate legal names must not authorize unrelated local organizations."""
import sys, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
EIN='362934689';NAME='Ronald McDonald House Global / RMHC'
OLD='RONALD MCDONALD HOUSE CHARITIES, INC.'
HOUSTON='RONALD MCDONALD HOUSE CHARITIES GREATER HOUSTON, INC.'
class ReviewedScopeTests(unittest.TestCase):
    def setUp(self):self.token=c.REVIEWED_NAME_CONTEXT.set({EIN:('Ronald McDonald House Global',OLD)})
    def tearDown(self):c.REVIEWED_NAME_CONTEXT.reset(self.token)
    def test_live_reported_affiliate_is_rejected(self):
        for candidate in [HOUSTON,'Ronald McDonald House Charities Greater Houston, I','Ronald McDonald House Charities of Kentuckiana, Inc']:
            with self.subTest(candidate=candidate):self.assertFalse(c.registry_name_is_safe_for_org(candidate,NAME,EIN))
    def test_former_national_name_is_preserved(self):
        for candidate in [OLD,'Ronald McDonald House Charities, Inc','Ronald McDonald House Global']:
            self.assertTrue(c.registry_name_is_safe_for_org(candidate,NAME,EIN))
    def test_la_actual_export_row_is_rejected(self):
        row={'Name':'Ronald McDonald House Charities Greater Houston, I','Registered Through':'12/12/2026'}
        self.assertIsNone(c.la_find_export_match([row],SimpleNamespace(organization_name=NAME,ein=EIN)))
    def test_explicit_reviewed_local_name_still_works(self):
        c.REVIEWED_NAME_CONTEXT.set({'012345678':(HOUSTON,)})
        self.assertTrue(c.registry_name_is_safe_for_org(HOUSTON,'Houston Family Housing','012345678'))
    def test_legal_suffix_and_approved_generic_words_stay_permissive(self):
        for original,alias,candidate in [
            ('American Farriers Association Foundation Inc','American Farriers Association','American Farriers Association Inc'),
            ('Coptic Orphans Support Association','Coptic Orphans Support Organization','Coptic Orphans Support Organization Inc'),
            ('End Violence Against Women International','End Violence Against Women International','End Violence Against Women International (EVAWI)'),
            ('YWCA USA','National Board of the YWCA of the USA','National Board of the YWCA of the USA, Inc')]:
            with self.subTest(original=original):
                c.REVIEWED_NAME_CONTEXT.set({'012345678':(alias,)})
                self.assertTrue(c.registry_name_is_safe_for_org(candidate,original,'012345678'))
    def test_different_ein_still_controls_exact_alias(self):
        self.assertEqual(c.score_candidate(NAME,EIN,{'name':OLD,'ein':'999999999'})['reason'],'REJECT_DIFFERENT_EIN')
    def test_fl_skips_affiliate_and_keeps_searching_for_national(self):
        page=MagicMock();page.expect_navigation.return_value.__enter__.return_value.value=Mock(status=200)
        page.evaluate.side_effect=[
            [{'text':f'Business Name {HOUSTON} License/Registration Number CH76217 Status Active Expiration Date 8/14/2027','index':0}],
            [{'text':'Business Name RONALD MCDONALD HOUSE GLOBAL License/Registration Number CH100 Status Active Expiration Date 12/15/2026','index':0}]]
        with patch.object(c,'high_signal_search_phrases',return_value=['Ronald McDonald House','Ronald McDonald House Global']),patch.object(c,'possessive_search_phrases',return_value=[]),patch.object(c.checker,'find_visible_input',return_value=page),patch.object(c,'readable_page_text',return_value='Search results CH100'),patch.object(c,'registry_candidate_fields',return_value={'status':'Active'}),patch.object(c.time,'sleep'):
            result=c.search_fl(page,SimpleNamespace(organization_name=NAME,ein=EIN))
        self.assertEqual(result.matched_registry_name,'RONALD MCDONALD HOUSE GLOBAL')
        self.assertEqual(result.matched_registry_identifier,'CH100')
if __name__=='__main__':unittest.main(verbosity=2)
