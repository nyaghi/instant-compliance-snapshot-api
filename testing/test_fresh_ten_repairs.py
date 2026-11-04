"""Focused source fixtures and rejection controls; no live registry calls."""
import copy, time, unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import registry_snapshot_server as m
from deployment import dc_boss_evidence as dc, dc_native_capture as native

class Repairs(unittest.TestCase):
    def test_pa_exact_ein_excluded_is_not_missing_date_delinquency(self):
        page=MagicMock();org=m.checker.Organization('Example Medical Board','123456789')
        from contextlib import ExitStack
        with ExitStack() as stack:
            for name,value in [('find_pa_ein_input',MagicMock()),('click_pa_search_button',True),
                               ('extract_pa_result_expiration',('Example Medical Board 12-3456789 Excluded','Excluded'))]:
                stack.enter_context(patch.object(m.checker,name,return_value=value))
            result=m.checker.search_pa(page,org)
        self.assertEqual(result.status,'Exempt');self.assertTrue(result.success)

    def test_nd_navigation_recovery_stays_once_and_does_not_fabricate_negative(self):
        org=m.checker.Organization('Example Medical Board','123456789')
        for sequence,expected in [([None],1),([TimeoutError('first'),None],2),([TimeoutError('first'),TimeoutError('second')],2)]:
            page=MagicMock();page.goto.side_effect=sequence
            page.locator.return_value.first.wait_for.side_effect=TimeoutError('modeled form unavailable')
            with patch.object(m,'known_names_for_ein',return_value=[]):result=m.search_nd_completed(page,org)
            self.assertEqual(page.goto.call_count,expected);self.assertFalse(result.success)
            self.assertNotEqual(result.status,'Not Registered')
            self.assertTrue(all(call.kwargs['timeout']<=12000 for call in page.goto.call_args_list))

    def test_card_change_recovery_keeps_signed_deadline_and_is_only_once(self):
        from testing.test_nc_specific_fallback import SpecificFallback
        case=SpecificFallback();case.setUp()
        try:
            with case.contexts('Family Health International'):
                _,first=case.start('NC');before=case.unpack(first)
                code,nextres=case.t.request({'action':'fail','check_token':first['check_token'],
                    'query_id':first['query_id'],'reason':'NY_CONNECTOR_REGISTRY_NC_CARD_CHANGED'})
                self.assertEqual(code,200);after=case.unpack(nextres)
                self.assertEqual(before['expires'],after['expires'])
                self.assertNotEqual(first['query_id'],nextres['query_id'])
                self.assertEqual(nextres['query']['name'],'Family Health International')
                self.assertFalse(m.nc_specific_name_recovery(after,{'query_id':nextres['query_id'],
                    'reason':'NY_CONNECTOR_REGISTRY_NC_CARD_CHANGED'},time.time()))
        finally:case.doCleanups()

    def test_generated_fragments_preserve_whole_brands(self):
        required=['Family Health International','FHI 360']
        self.assertEqual(m.focused_generated_name_queries(required,
            ['Family','Health','Family Health','FHI 360','Family-Health International']),
            ['Family Health','FHI 360','Family-Health International'])
        for brand in ['CARE','PATH','Sierra Club','Sierra','Celiac Disease Foundation']:
            self.assertEqual(m.focused_generated_name_queries([brand],[brand]),[brand])
        self.assertEqual(m.focused_generated_name_queries(['Vasculitis Foundation'],['Vasculitis']),['Vasculitis'])

    def test_pa_related_entity_and_ein_conflicts_rejected(self):
        org=m.checker.Organization('Family Health International','237413005')
        base={'PersonId':123,'EntityName':'Child Family Health International','CertificateNumber':'13731','ExpDate':'1998-01-01','StatusName':''}
        with patch.object(m,'known_names_for_ein',return_value=[]):
            self.assertIsNone(m.pa_completed_name_rows(org,[base],'https://state'))
            self.assertIsNone(m.pa_completed_name_rows(org,[dict(base,EntityName=org.organization_name,EIN='943145385')],'https://state'))
            exact=m.pa_completed_name_rows(org,[dict(base,EntityName=org.organization_name,ExpDate='2027-12-31')],'https://state')
            self.assertIsNotNone(exact)
            self.assertEqual(exact.matched_registry_name,org.organization_name)

    def test_pa_excluded_name_row(self):
        org=m.checker.Organization('Example Medical Board','123456789')
        with patch.object(m,'known_names_for_ein',return_value=[]):
            result=m.pa_completed_name_rows(org,[{'PersonId':1,'EIN':org.ein,'EntityName':org.organization_name,'StatusName':'Excluded','ExpDate':'Excluded'}],'https://state')
        self.assertEqual(result.status,'Exempt')
        with patch.object(m,'known_names_for_ein',return_value=[]):
            result=m.pa_completed_name_rows(org,[{'PersonId':1,'EIN':org.ein,'EntityName':org.organization_name,'StatusName':'','ExpDate':'Excluded'}],'https://state')
        self.assertEqual(result.status,'Exempt')

    def test_nc_precise_prefix_keeps_primary_distinctive_words(self):
        name='Partners in Health a Nonprofit Corporation'
        probes,coverage,modes,generated=m.nc_covering_query_plan([name],['Partners in Health'],{name:'IN HEALTH'},name)
        self.assertEqual(probes,['Partners in Health'])
        self.assertNotIn('IN HEALTH',modes.values())
        self.assertEqual(coverage[probes[0]],[name])

    def test_tn_compound_requires_both_known_names(self):
        value='PATH (PROGRAM FOR APPROPRIATE TECHNOLOGY IN HEALTH)'
        with patch.object(m,'known_names_for_ein',return_value=['Program for Appropriate Technology in Health']),patch.object(m,'is_reviewed_alias',side_effect=lambda ein,n: m.normalized_match_name(n)==m.normalized_match_name('Program for Appropriate Technology in Health')):
            self.assertEqual(m.tn_reviewed_compound_names(value,'PATH','911157127'),['PATH','PROGRAM FOR APPROPRIATE TECHNOLOGY IN HEALTH'])
            self.assertEqual(m.tn_reviewed_compound_names('PATH (UNRELATED HEALTH FOUNDATION)','PATH','911157127'),[])
            self.assertEqual(m.tn_reviewed_compound_names('OTHER (PROGRAM FOR APPROPRIATE TECHNOLOGY IN HEALTH)','PATH','911157127'),[])
            self.assertEqual(m.tn_reviewed_compound_names(value+' LOCAL CHAPTER','PATH','911157127'),[])

    def test_dc_terminal_undated_retains_source_and_rejects_active(self):
        fields={'Licensee':'EXAMPLE MEDICAL BOARD','Trade Name':'N/A','License Category':'Charitable Services','License Activity':'Charitable Solicitation','License Number':'39808905','Premise Address':'10 W 17TH ST','License Status':'Cancelled','Issue Date':'10/04/2010','Expiration Date':'N/A'}
        request={'identifier':fields['License Number'],'name':fields['Licensee'],'raw_status':'Cancelled','expiration':''}
        text='License Information\n'+'\n'.join(k+'\n'+fields[k] for k in dc.LABELS)+'\nLicensee Information\n'
        self.assertEqual(dc.fields('https://boss.dc.gov/licensing/license-details',text,request),fields)
        for change in [{'raw_status':'Active'},{'expiration':'2027-01-01'},{'identifier':'39808906'},{'name':'OTHER MEDICAL BOARD'}]:
            self.assertIsNone(dc.fields('https://boss.dc.gov/licensing/license-details',text,{**request,**change}))
        row={**request,'license_category':'Charitable Solicitation','url':"https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/DCRA/FeatureServer/0/query?where=CUSTOMERNUMBER%3D%2739808905%27&outFields=*&returnGeometry=false&f=pjson"}
        self.assertIsNotNone(native.expected_record(row))
        self.assertIsNone(native.expected_record({**row,'raw_status':'Active'}))

if __name__=='__main__':unittest.main()
