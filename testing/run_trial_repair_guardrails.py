"""Controls for the approved October 1 trial repairs, including failure cases."""
import copy
from datetime import date
import unittest
from unittest.mock import patch
import registry_snapshot_server as cc
from testing.run_final_four_source_guardrails import AsOf, TN, TN_ROW, NV, NV_FILINGS

class Repairs(unittest.TestCase):
    def setUp(self):
        p=patch.object(cc,'date',AsOf);p.start();self.addCleanup(p.stop)
    def test_tn_stale_complete_history_without_expiration_is_delinquent(self):
        for period in ['09/30/2015','09/30/2017']:
            r=cc.tn_charity_detail_evidence({**TN,'Expiration Date':'','financial_periods':[period],'financial_count':1},'CO3674',TN_ROW)
            self.assertEqual(r['status'],'Delinquent');self.assertIn('annual-renewal rule',r['date_evidence_note'])
            self.assertEqual(r['expiration'].month,3)
    def test_tn_no_expiry_missing_history_cannot_be_current(self):
        fields={k:v for k,v in TN.items() if k not in {'financial_periods','financial_count'}}
        fields['Expiration Date']=''
        self.assertEqual(cc.tn_charity_detail_evidence(fields,'CO3674',TN_ROW)['status'],'Unable to Confirm')
    def test_tn_explicit_exemption_and_expiry_keep_priority(self):
        for raw,expiry,status in [('Exempt','','Exempt'),('Revoked','','Revoked'),('Active','11/27/2026','Upcoming Filing')]:
            r=cc.tn_charity_detail_evidence({**TN,'Status':raw,'Expiration Date':expiry,'financial_periods':['09/30/2015'],'financial_count':1},'CO3674',TN_ROW)
            self.assertEqual(r['status'],status)
    def test_nv_corporate_currency_without_charity_filing_is_unconfirmed(self):
        r=cc.nv_charity_detail_evidence(NV,NV['NV Business ID'])
        self.assertEqual(r['status'],'Unable to Confirm')
        with self.assertRaises(ValueError):cc.nv_charity_filings_evidence(r,NV_FILINGS)
    def test_mi_distinct_reviewed_alias_survives_equivalent_spellings(self):
        org=cc.checker.Organization('Human Trafficking Legal Center','46-1349584')
        names=['Human Trafficking Legal Center','HUMAN TRAFFICKING LEGAL CENTER','Human Trafficking Legal Center, Inc.',
               'The Human Trafficking Legal Center','Human Trafficking Pro Bono Legal Center']
        with patch.object(cc,'organization_name_variants',return_value=names):
            self.assertIn(names[-1],cc.mi_name_fallback_queries(org))
    def test_actual_trial_submission_counts_eight_browser_lanes_inside_the_ceiling(self):
        from deployment import durable_queue as q, staging_workflows as w
        from types import SimpleNamespace
        payload={'organization_name':'Example Charity','ein':'123456789','alternate_names':['Example Charity'],
                 'states':['NY','IL','GA','AL','NC','NV','TN','NM','CO'], 'mode':'standard','request_id':'a'*36}
        seen=[]
        def transport(path,data,key):
            normalized=q.normalize_submission(data,payload['states']);seen.append(normalized)
            return {'id':'11111111-1111-1111-1111-111111111111'}
        master=SimpleNamespace(SUPPORTED_STATES=payload['states'],NY_CONNECTOR_SIGNING_KEY='fixture-'*8,
                               APP_VERSION='fixture',canonical_ein_digits=cc.canonical_ein_digits)
        with patch.object(q,'trial_identity',return_value={'origin':'isolated'}):
            w.prepare(master,payload,['fixture','device'],transport=transport,
                      external_states=set(payload['states'])-{'CO'},external_slots=8)
        self.assertEqual(seen[0]['external_state_slots'],8)
        self.assertEqual(q.workflow_state_limit({'payload':seen[0]}),7)
        with patch.object(q,'trial_identity',return_value=None):
            with self.assertRaises(ValueError):q.normalize_submission(seen[0],payload['states'])

    def test_nm_incomplete_or_wrong_ein_evidence_cannot_be_a_negative(self):
        q={'state':'NM','operation':'search','ein':'461349584','name':''}
        good={'query':q,'complete':True,'rows':[],'total':0}
        self.assertEqual(cc.nm_browser_clean_evidence(good,q),good)
        for change in [{'complete':False},{'total':1},{'rows':[{'name':'Other','ein':'123'}],'total':1},
                       {'query':{**q,'ein':'123456789'}},{'html':'unneeded page'}]:
            with self.assertRaises(ValueError):cc.nm_browser_clean_evidence({**good,**change},q)

    def test_nm_completed_empty_ein_and_names_reuse_master_required_names(self):
        org=cc.checker.Organization('Human Trafficking Legal Center','46-1349584');seen=[]
        def source(q):
            seen.append(q)
            return {'query':q,'complete':True,'rows':[],'total':0}
        with patch.object(cc,'licensed_charity_names',return_value=(['Legal Name','Reviewed Alias'],['Generated Name'])):
            result=cc.nm_browser_lookup(org,source)
        self.assertEqual(result.status,'Not Registered')
        self.assertEqual([q['name'] for q in seen],['','Legal Name','Reviewed Alias','Generated Name'])

    def test_nm_browser_history_matches_mature_master_classification(self):
        org=cc.checker.Organization('NATCA Charitable Foundation','75-2556496')
        rows=[['2025','Extension Granted','6/10/2026'],['2024','Registration Submitted 20244922536459055','12/30/2025']]
        def source(q):
            if q['operation']=='search':return {'query':q,'complete':True,'rows':[{'name':org.organization_name,'ein':'752556496'}],'total':1}
            return {'query':q,'complete':True,'name':org.organization_name,'ein':'752556496',
                    'history_rows':rows,'financial_periods':[{'tax_year':2024,'period_start':'1/1/2024','period_end':'12/31/2024'}]}
        result=cc.nm_browser_lookup(org,source)
        module=cc.load_wa_nm_module()
        baseline=module.SearchResult(org.organization_name,org.ein,'NM',module.STATUS_UNKNOWN,'','','')
        baseline.matched_registry_name=org.organization_name;baseline.matched_registry_identifier=org.ein
        baseline=cc.nm_apply_status_history_master(module,baseline,[(int(y),s,d) for y,s,d in rows],fye_text='12/31/2024')
        self.assertEqual(result.status,cc.copy_external_result(org,'NM',baseline).status)
        self.assertNotEqual(result.status,'Not Registered')
if __name__=='__main__':unittest.main()
