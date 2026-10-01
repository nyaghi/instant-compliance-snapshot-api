"""Controls for the approved October 1 trial repairs, including failure cases."""
import copy
import json
from pathlib import Path
from datetime import date
import unittest
from unittest.mock import patch
import registry_snapshot_server as cc
from testing.run_final_four_source_guardrails import AsOf, TN, TN_ROW, NV, NV_FILINGS

class Repairs(unittest.TestCase):
    def setUp(self):
        p=patch.object(cc,'date',AsOf);p.start();self.addCleanup(p.stop)
    def test_signed_current_trial_ny_search_continues_to_browser_detail(self):
        from testing import run_ny_connector_guardrails as base
        legacy=base.ConnectorTests();legacy.setUp();self.addCleanup(legacy.doCleanups)
        with patch.object(cc,'trial_identity',return_value={'origin':'isolated'}):
            code,state=legacy.request(action='start',organization_name=base.ROW['orgName'],
                                      ein=base.ROW['ein'],connector_version='0.6.29')
            self.assertEqual(code,200)
            code,state=legacy.submit(state)
            self.assertEqual(code,200);self.assertEqual(state['phase'],'search')
            self.assertEqual(state['query'],{'orgID':base.ROW['orgID']})
            code,state=legacy.submit(state,detail=base.DETAIL)
            self.assertEqual(code,200);self.assertEqual(state['result']['status'],'Current')
            self.assertEqual(state['result']['connector_version'],'0.6.29')
            legacy.session.get.assert_not_called()
        with patch.object(cc,'trial_identity',return_value=None):
            code,_=legacy.request(action='start',organization_name=base.ROW['orgName'],
                                   ein=base.ROW['ein'],connector_version='0.6.29')
            self.assertEqual(code,400)
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

    def test_nm_validated_broad_searches_stay_within_signed_evidence_bound(self):
        record={'state':'NM','ein':'46-1349584','completed':[]}
        for i in range(12):
            query={'state':'NM','operation':'search','ein':'461349584','name':'Alias '+str(i)}
            rows=[{'name':'Other registered organization '+str(j),'ein':str(100000000+j)} for j in range(685)]
            raw={'query':query,'complete':True,'rows':rows,'total':len(rows)}
            cleaned=cc.nm_browser_clean_evidence(raw,query)
            compact=cc.final_four_compact_search_evidence(record,cleaned)
            record['completed'].append({'query':query,'evidence':compact})
            self.assertEqual(compact['rows'],[])
        with patch.object(cc,'NY_CONNECTOR_SIGNING_KEY','test-key'*8):
            self.assertLess(len(cc.ny_connector_pack(record)),10000)
        self.assertEqual([a['source_total'] for a in record['nm_search_audits']],[685]*12)
        self.assertEqual(len(rows),685)  # Original validated evidence remains intact.

    def test_nm_compaction_preserves_exact_ein_and_rejects_client_audit_fields(self):
        query={'state':'NM','operation':'search','ein':'461349584','name':'Reviewed Alias'}
        match={'name':'Source legal name','ein':'461349584'}
        raw={'query':query,'complete':True,'rows':[{'name':'Unrelated','ein':'123456789'},match],'total':2}
        record={'state':'NM','ein':'46-1349584'}
        compact=cc.final_four_compact_search_evidence(record,cc.nm_browser_clean_evidence(raw,query))
        self.assertEqual(compact['rows'],[match]);self.assertEqual(compact['total'],1)
        self.assertEqual(record['nm_search_audits'][0]['source_total'],2)
        with self.assertRaises(ValueError):
            cc.nm_browser_clean_evidence({**raw,'nm_search_audits':[{'completed':True}]},query)

    def test_nm_browser_history_matches_mature_master_classification(self):
        org=cc.checker.Organization('NATCA Charitable Foundation','75-2556496')
        rows=[['2025','Extension Granted','6/10/2026'],['2024','Registration Submitted 20244922536459055','12/30/2025'],
              ['', 'Charity Added to COROS', '11/16/2018']]
        def source(q):
            if q['operation']=='search':return {'query':q,'complete':True,'rows':[{'name':org.organization_name,'ein':'752556496'}],'total':1}
            return {'query':q,'complete':True,'name':org.organization_name,'ein':'752556496',
                    'history_rows':rows,'financial_periods':[{'tax_year':2024,'period_start':'1/1/2024','period_end':'12/31/2024'}]}
        result=cc.nm_browser_lookup(org,source)
        module=cc.load_wa_nm_module()
        baseline=module.SearchResult(org.organization_name,org.ein,'NM',module.STATUS_UNKNOWN,'','','')
        baseline.matched_registry_name=org.organization_name;baseline.matched_registry_identifier=org.ein
        baseline=cc.nm_apply_status_history_master(module,baseline,[(int(y),s,d) for y,s,d in rows if y],fye_text='12/31/2024')
        self.assertEqual(result.status,cc.copy_external_result(org,'NM',baseline).status)
        self.assertNotEqual(result.status,'Not Registered')
    def test_nm_only_exact_administrative_row_can_omit_tax_year(self):
        q={'state':'NM','operation':'detail','identifier':'752556496','name':'NATCA Charitable Foundation'}
        data={'query':q,'complete':True,'name':q['name'],'ein':q['identifier'],
              'history_rows':[['','Charity Added to COROS','11/16/2018']], 'financial_periods':[]}
        self.assertEqual(cc.nm_browser_clean_evidence(data,q),data)
        for row in [['','Registration Submitted','11/16/2018'],['201','Charity Added to COROS','11/16/2018'],
                    ['','Charity Added to COROS','not a date']]:
            with self.assertRaises(ValueError):cc.nm_browser_clean_evidence({**data,'history_rows':[row]},q)
    def test_nm_observed_unassigned_submission_does_not_replace_filing_period(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/nm-make-wish-20261001.json').read_text())
        org=cc.checker.Organization('Make-A-Wish Foundation of America','86-0481941')
        def source(q):
            if q['operation']=='search':
                return {'query':q,'complete':True,'rows':[{'name':org.organization_name,'ein':'860481941'}],'total':1}
            return {'query':q,'complete':True,'name':org.organization_name,'ein':'860481941',
                    'history_rows':fixture['history_rows'],'financial_periods':fixture['financial_periods']}
        result=cc.nm_browser_lookup(org,source)
        module=cc.load_wa_nm_module()
        year_rows=[(int(y),s,d) for y,s,d in fixture['history_rows'] if y]
        self.assertEqual(module.nm_latest_submitted(year_rows)[0],2024)
        baseline=module.SearchResult(org.organization_name,org.ein,'NM',module.STATUS_UNKNOWN,'','','')
        baseline.matched_registry_name=org.organization_name;baseline.matched_registry_identifier=org.ein
        baseline=cc.nm_apply_status_history_master(module,baseline,year_rows,fye_text='8/31/2025')
        self.assertEqual(result.status,cc.copy_external_result(org,'NM',baseline).status)
        self.assertNotIn(result.status,{'Not Registered','Unknown','Unable to Confirm'})
        q={'state':'NM','operation':'detail','identifier':'860481941','name':org.organization_name}
        data=source(q)
        self.assertEqual(cc.nm_browser_clean_evidence(data,q)['history_rows'],fixture['history_rows'])
        for label in ['Registration Submitted','Registration Submitted 20244122623260437',
                      'Registration Submitted 0000412211896704','Extension Granted']:
            with self.assertRaises(ValueError):
                cc.nm_browser_clean_evidence({**data,'history_rows':[['',label,'7/8/2021']]},q)

    def test_shared_inactive_rule_and_later_qualifying_record_across_states(self):
        org=cc.checker.Organization('Example National Foundation','12-3456789')
        for state in ['AL','NC','NV','TN','IL','GA','DC','RI']:
            with self.subTest(state=state):
                closed=cc.licensed_charity_status('Inactive',date(2099,1,1))
                self.assertEqual(closed,'Closed / Withdrawn / Canceled')
                old=dict(name=org.organization_name,ein=org.ein,identifier='old',
                         raw_status='Inactive',status=closed,expiration=date(2020,1,1),location='',url='')
                current=dict(name=org.organization_name,ein=org.ein,identifier='new',
                             raw_status='Current',status='Current',expiration=date(2027,12,31),location='',url='')
                result,review=cc.select_licensed_charity(org,[old],state,cc.time.monotonic()+10)
                self.assertFalse(review);self.assertEqual(result['status'],closed)
                result,review=cc.select_licensed_charity(org,[old,current],state,cc.time.monotonic()+10)
                self.assertFalse(review);self.assertEqual(result['identifier'],'new')

    def test_nm_observed_inactive_lifecycle_has_no_invented_fiscal_year(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/nm-public-gardens-20261001.json').read_text())
        org=cc.checker.Organization('American Public Gardens Association','23-7110058')
        def source(q):
            if q['operation']=='search':return {'query':q,'complete':True,'rows':[{'name':org.organization_name,'ein':'237110058'}],'total':1}
            return {'query':q,'complete':True,'name':org.organization_name,'ein':'237110058',
                    'history_rows':fixture['history_rows'],'financial_periods':fixture['financial_periods']}
        result=cc.nm_browser_lookup(org,source)
        self.assertEqual(result.status,'Closed / Withdrawn / Canceled')
        self.assertIn('2025-09-30',result.source_note)
        self.assertNotEqual(result.status,'Not Registered')
        module=cc.load_wa_nm_module()
        # Existing mature input must use the same source-status rule.
        def classify(rows):
            baseline=module.SearchResult(org.organization_name,org.ein,'NM',module.STATUS_UNKNOWN,'','','')
            return cc.nm_apply_status_history_master(module,baseline,rows,fye_text='12/31/2024')
        rows=[(int(y) if y else 0,label,when) for y,label,when in fixture['history_rows'] if y or label=='Inactive Registration']
        self.assertEqual(classify(rows).status,module.STATUS_CLOSED)
        later=[*rows,(2025,'Registration Submitted 20250000000000000','10/1/2025')]
        self.assertNotEqual(classify(later).status,module.STATUS_CLOSED)
        same=[*rows,(2025,'Extension Granted','9/30/2025')]
        self.assertEqual(classify(same).status,'Needs Review')
        self.assertFalse(classify(same).success)
        future=[(0,'Inactive Registration','10/2/2026'),(2024,'Registration Submitted 20240000000000000','8/5/2025')]
        self.assertNotEqual(classify(future).status,module.STATUS_CLOSED)

    def test_nv_composite_name_is_retained_for_detail_not_accepted(self):
        name='American Public Gardens Association'
        row={'name':name+', American Association of Botanical Gardens and Arboreta',
             'identifier':'NV20243137331','entity_type':'Foreign Entities Not Required to Register In Nevada'}
        scores=cc.final_four_search_candidate_scores(name,'237110058','NV',row)
        self.assertEqual(scores[-1]['decision'],'possible')
        self.assertFalse(any(c['decision']=='accepted' for c in scores))
        record={'state':'NV','organization_name':name,'ein':'237110058','alternate_names':[]}
        evidence={'query':{'state':'NV','operation':'search','name':name},'rows':[row],'total':1}
        self.assertEqual(cc.final_four_compact_search_evidence(record,evidence)['rows'],[row])
        for state,changes in [('NC',{}),('NV',{'ein':'123456789'}),('NV',{'name':'Different Foundation, '+name})]:
            changed={**row,**changes}
            self.assertEqual(cc.final_four_search_candidate_scores(name,'237110058',state,changed),
                             [cc.score_candidate(name,'237110058',{'name':changed['name'],'ein':changed.get('ein','')})])
    def test_nv_observed_composite_record_requires_independent_detail_identity(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/nv-public-gardens-20261001.json').read_text())
        org=cc.checker.Organization('American Public Gardens Association','23-7110058')
        fields=fixture['fields'];identifier=fields['NV Business ID'];seen=[]
        def source(query):
            seen.append(query)
            if query['operation']=='search':
                return {'state':'NV','query':query,'complete':True,'verification_pending':False,'total':1,
                        'rows':[{'name':fields['Entity Name'],'identifier':identifier,'entity_type':fields['Entity Type']}]}
            return {'query':query,'complete':True,'fields':fields,'source_url':fixture['source_url'],
                    'filings':{'identifier':identifier,'name':fields['Entity Name'],'complete':True,'total':3,
                               'headers':fixture['headers'],'rows':fixture['rows']}}
        with patch.object(cc,'licensed_charity_names',return_value=([org.organization_name],[])), \
                patch.object(cc,'reconciled_registry_address',return_value={'decision':'unavailable'}):
            result=cc.final_four_browser_lookup(org,'NV',source)
        self.assertEqual([q['operation'] for q in seen],['search','detail'])
        self.assertEqual(result.status,'Closed / Withdrawn / Canceled')
        self.assertEqual(result.matched_registry_identifier,identifier)
if __name__=='__main__':unittest.main()
