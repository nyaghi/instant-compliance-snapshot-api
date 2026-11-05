"""Literal retrieval and distinct institutional EIN paths, without live sources."""
import unittest
from unittest.mock import Mock,MagicMock,patch
import registry_snapshot_server as m

class NamePaths(unittest.TestCase):
    name="The Children's Hospital of Philadelphia"
    ein='231352166'

    def test_ar_changed_institution_descriptor_is_review_only_with_original_row(self):
        org=m.checker.Organization('National Jewish Health','742044647')
        row={'name':'National Jewish Center for Immunology & Respirator','status':'Not Current','registration_date':'1999-08-30'}
        targets=m.organization_match_target_variants(org.organization_name,org.ein)
        self.assertEqual(m.ar_candidate_identity(row,org.organization_name,targets,org.ein),'unconfirmed_scope')
        self.assertEqual(m.ar_candidate_identity({**row,'ein':'987654321'},org.organization_name,targets,org.ein),'reject')
        for unrelated in ['National Jewish Outreach Program','National Jewish Health Foundation','National Jewish Center Foundation',
                          'National Asthma Center for Immunology','Jewish Center for Immunology','National Health Center']:
            self.assertFalse(m.ar_institution_name_reviewable(unrelated,org.organization_name,org.ein))
        self.assertTrue(m.ar_institution_name_reviewable('Mountain Valley Medical Center','Mountain Valley Health','123456789'))
        page=Mock(url=m.AR_SEARCH_URL)
        with patch.object(m,'ar_preferred_name_variants',return_value=[org.organization_name]), \
             patch.object(m,'ar_reviewed_search_plan',return_value=([org.organization_name],{})), \
             patch.object(m,'ar_wait_for_search_form',return_value=True), \
             patch.object(m,'registry_page_body',return_value='Back to Search Form Registration Date'), \
             patch.object(m,'safe_wait_for_network_idle'),patch.object(m,'ar_result_rows',return_value=[row]), \
             patch('deployment.source_visual_adapters.capture_ar_review_page') as capture:
            result=m.search_ar_precise(page,org)
        self.assertFalse(result.success);self.assertNotEqual(m.public_status(result),'Not Registered')
        self.assertEqual(result._cc_identity_review['records'][0]['name'],row['name'])
        self.assertEqual(result._cc_identity_review['records'][0]['status'],'Delinquent')
        capture.assert_called_once()

    def test_ar_first_literal_probe_finds_complete_hospital_without_accepting_foundation(self):
        org=m.checker.Organization(self.name,self.ein);page=Mock(url=m.AR_SEARCH_URL)
        rows=[{'name':'Childrens Hospital of Philadelphia Foundation','status':'Current','registration_date':'2009-01-01'},
              {'name':'Childrens Hospital of Philadelphia','status':'Current','registration_date':'2008-09-18'}]
        with patch.object(m,'ar_wait_for_search_form',return_value=True), \
             patch.object(m,'registry_page_body',return_value='Back to Search Form Registration Date'), \
             patch.object(m,'safe_wait_for_network_idle'),patch.object(m,'ar_result_rows',return_value=rows):
            result=m.search_ar_precise(page,org)
        self.assertTrue(result.success);self.assertEqual(result.status,'Current')
        self.assertEqual(result.matched_registry_name,'Childrens Hospital of Philadelphia')
        self.assertEqual(result.queries_attempted,['Childrens Hospital of Philadelphia'])
        queries,_=m.ar_reviewed_search_plan(org,m.ar_preferred_name_variants(org))
        self.assertLessEqual(len(queries),m.AR_NAME_SEARCH_MAX_VARIANTS)

    def mn(self,rows):
        org=m.checker.Organization(self.name,self.ein);page=MagicMock()
        page.evaluate.return_value=rows
        with patch.object(m,'build_search_queries',return_value=[self.name]), \
             patch.object(m.checker,'find_visible_input',return_value=Mock()), \
             patch.object(m.checker,'safe_wait_for_network_idle'),patch.object(m.time,'sleep'), \
             patch.object(m,'readable_page_text',side_effect=['No results found','No results found','Search result']):
            return m.search_mn(page,org),page

    def test_mn_different_ein_foundation_alias_cannot_be_hospital_registration(self):
        row={'index':0,'text':self.name+' Foundation','linkText':self.name+' Foundation',
             'aliases':[self.name],'href':'CHR_GeneralInfo.asp?FederalID=232237932&Yr=CURR&cmdSearch=View'}
        result,page=self.mn([row])
        self.assertEqual(m.public_status(result),'Not Registered');self.assertTrue(result.success)
        self.assertFalse(result.matched_registry_name)
        page.locator.return_value.first.click.assert_not_called()

    def test_mn_unreadable_nonempty_page_never_becomes_negative(self):
        result,_=self.mn([])
        self.assertEqual(result.status,'Unable to Confirm');self.assertFalse(result.success)

if __name__=='__main__':unittest.main()
