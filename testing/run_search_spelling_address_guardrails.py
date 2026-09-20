"""Regression controls for literal registry searches and EIN-bound office evidence."""
import copy, io, itertools, json, sys, time, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class SearchSpellings(unittest.TestCase):
    def scope(self,names):
        token=c.REVIEWED_NAME_CONTEXT.set({'020784790':tuple(names)})
        self.addCleanup(c.REVIEWED_NAME_CONTEXT.reset,token)
    def test_request_retains_discovered_ascii_hyphen(self):
        payload={'organization_name':'FII\u2013National','ein':'020784790',
                 'alternate_names':['FII - NATIONAL','UPTOGETHER','FII-NATIONAL','Family Independence Initiative']}
        org=c.normalize_organization_requests(payload,True)[0]
        self.assertIn('FII-NATIONAL',org['alternate_names'])
        self.scope(org['alternate_names'])
        self.assertEqual(c.equivalent_name_queries(org['organization_name'],org['ein'])[0].casefold(),'fii-national')
        self.assertEqual(c.wv_preferred_query_variants(org['organization_name'],org['ein'])[0].casefold(),'fii-national')
        self.assertEqual(c.build_search_queries(org['organization_name'],org['ein'])[0].casefold(),'fii-national')
    def test_ascii_hyphen_survives_both_alias_orders(self):
        for names in [['FII\u2013National','FII-NATIONAL'],['FII-NATIONAL','FII\u2013National']]:
            self.assertEqual(len(c.normalize_reviewed_names(names)),2)
    def test_case_and_legal_suffix_duplicates_still_collapse(self):
        self.assertEqual(c.normalize_reviewed_names(['Example Relief','EXAMPLE RELIEF, INC.','Example Relief incorporated']),['Example Relief'])
    def test_existing_apostrophe_deduplication_is_unchanged(self):
        self.assertEqual(len(c.normalize_reviewed_names(["Children's Relief","Children\u2019s Relief"])),1)
    def test_same_literal_primary_not_reintroduced_as_alias(self):
        row=c.normalize_organization_requests({'organization_name':'FII-National','ein':'020784790','alternate_names':['FII-NATIONAL, INC.']},True)[0]
        self.assertEqual(row['alternate_names'],[])
    def test_dash_alternative_does_not_require_discovery(self):
        self.scope([])
        for dash in ['\u2010','\u2011','\u2012','\u2013','\u2014','\u2015','\u2212']:
            name='FII'+dash+'National'
            self.assertIn('FII-National',c.build_search_queries(name,'020784790')[:4])
            self.assertEqual(c.wv_preferred_query_variants(name,'020784790')[0],'FII-National')
    def test_no_spelling_changes_add_identity_or_remove_locations(self):
        self.assertTrue(c.institution_location_conflict('Beth Israel Deaconess Hospital \u2013 Milton','Beth Israel Deaconess Hospital'))
        self.assertNotEqual(c.score_candidate('AIR FORCE ACADEMY FOUNDATION','',{'name':'AIR FORCE ACADEMY ATHLETIC CORPORATION'})['decision'],'accepted')
    def test_alternate_name_bound_and_validation_remain(self):
        with self.assertRaises(ValueError):c.normalize_reviewed_names(['Name']*33)
        with self.assertRaises(ValueError):c.normalize_reviewed_names(['bad\nname'])
    def test_ms_reaches_distinct_reviewed_names_before_dash_duplicate(self):
        self.scope(['FII - NATIONAL','UPTOGETHER','FII-NATIONAL','Family Independence Initiative'])
        plan=c.ms_name_search_plan('FII\u2013National','020784790')
        self.assertEqual([p.casefold() for p in plan[:4]],['fii-national','fii - national','uptogether','family independence initiative'])
        self.assertTrue(c.reviewed_identity_queries_completed(plan[:4],c.equivalent_name_queries('FII\u2013National','020784790')))
        self.assertFalse(any('\u2013' in p for p in plan))
    def test_ms_dash_normalization_keeps_distinct_alias_and_identity_guard(self):
        self.scope(['North\u2013South Learning','Different Former Name'])
        plan=c.ms_name_search_plan('North-South Learning','020784790')
        self.assertIn('Different Former Name',plan)
        self.assertEqual(sum(p.casefold()=='north-south learning' for p in plan),1)
        self.assertFalse(c.ms_registry_name_is_safe('Organization for Autism Research','Autism Research Institute','952548452'))

class OfficeEvidence(unittest.TestCase):
    ein='123456789';name='Regional Learning Association'
    def profile(self):
        return {'organization':{'ein':123456789,'city':'Concord','state':'CA'}}
    def record(self,source='CA',**changes):
        return dict({'source':source,'ein':self.ein,'source_url':'https://state.example/record',
            'names':[self.name],'city':'Oakland','state':'CA','address_role':'organization'},**changes)
    def run_evidence(self,records,location='Oakland, CA',state='ME',name=None):
        def cached(source,ein):
            return {'organization_records':[r for r in records if r['source']==source]}
        with patch.object(c,'public_profile_for_ein',return_value=self.profile()), \
             patch.object(c,'identity_cached_source_result',side_effect=cached), \
             patch.object(c,'identity_source_result') as fetch:
            result=c.reconciled_registry_address(self.ein,name or self.name,location,registry_state=state)
        fetch.assert_not_called()
        return result
    def test_second_office_resolves_conflict_in_me_and_wv(self):
        for state in ['ME','WV']:
            result=self.run_evidence([self.record()],state=state)
            self.assertEqual(result['decision'],'corroborated')
            self.assertEqual(result['requested_ein'],self.ein)
            self.assertIn('Maine' if state=='ME' else 'West Virginia',result['basis'])
            self.assertNotIn('Wisconsin',result['basis'])
    def test_wrong_ein_role_name_or_location_never_resolves(self):
        for changes in [{'ein':'999999999'},{'address_role':'mailing'},{'address_role':'agent'},
                        {'city':'Madison'},{'state':'WI'},
                        {'names':[self.name+' Wisconsin Chapter']},{'names':[self.name+' Foundation']}]:
            with self.subTest(changes=changes):
                self.assertEqual(self.run_evidence([self.record(**changes)])['decision'],'conflict')
    def test_same_city_different_state_is_not_a_match(self):
        self.assertEqual(self.run_evidence([self.record()],location='Oakland, NJ')['decision'],'conflict')
    def test_original_agreement_or_missing_address_adds_no_requests(self):
        for location in ['Concord, CA','']:
            with patch.object(c,'public_profile_for_ein',return_value=self.profile()),patch.object(c,'registry_cross_state_identity') as other:
                c.reconciled_registry_address(self.ein,self.name,location,registry_state='ME')
                other.assert_not_called()
    def test_expired_budget_does_not_start_cross_state_requests(self):
        with patch.object(c,'public_profile_for_ein',return_value=self.profile()),patch.object(c,'registry_cross_state_identity') as other:
            r=c.reconciled_registry_address(self.ein,self.name,'Oakland, CA',registry_state='ME',deadline=time.monotonic()-1)
        self.assertEqual(r['decision'],'conflict');other.assert_not_called()
    def test_incomplete_sources_do_not_clear_conflict(self):
        with patch.object(c,'public_profile_for_ein',return_value=self.profile()), \
             patch.object(c,'identity_cached_source_result',return_value=None), \
             patch.object(c,'identity_source_result',side_effect=TimeoutError):
            self.assertEqual(c.reconciled_registry_address(self.ein,self.name,'Oakland, CA',registry_state='ME')['decision'],'conflict')
    def test_maine_multiple_marker_is_not_sent_as_city(self):
        self.assertEqual(self.run_evidence([self.record()],location='*MULTIPLES IN OAKLAND, CA')['decision'],'corroborated')
    def test_short_name_requires_same_ein_name_office(self):
        self.assertEqual(self.run_evidence([self.record(names=['RLA'])],state='WV',name='RLA')['decision'],'corroborated')
        self.assertEqual(self.run_evidence([self.record()],state='WV',name='RLA')['decision'],'conflict')
    def test_maine_status_still_comes_from_local_credential(self):
        evidence=self.run_evidence([self.record()])
        row={'name':self.name,'number':'CO12345','href':'pub/Details.aspx?token=test',
             'status':'FAILED TO RENEW','location':'Oakland, CA','address_evidence':evidence}
        detail=b'<html>License Number: CO12345 Status: Failed to Renew Expiration Date: 11/30/2024</html>'
        reader=type('Reader',(),{'open':lambda self,*a,**kw:io.BytesIO(detail)})()
        result=c.me_result_from_search(c.checker.Organization(self.name,self.ein),row,reader,True,'')
        self.assertEqual(c.public_status(result),'Failed to Renew')
        self.assertIn('Maine',result.source_note);self.assertIn('CA',result.source_note)
    def test_unresolved_maine_comment_identifies_profile_source(self):
        row={'name':self.name,'number':'CO12345','href':'pub/Details.aspx?token=test',
             'address_evidence':{'decision':'conflict','registry_location':'Madison, WI','ein_linked_location':'Concord, CA'}}
        result=c.me_result_from_search(c.checker.Organization(self.name,self.ein),row,object(),True,'')
        self.assertEqual(result.status,'Unable to Confirm')
        self.assertIn('ProPublica',result.source_note)

class NewYorkDuplicates(unittest.TestCase):
    def records(self):
        return [
          {'orgID':'101','ein':'123456789','orgName':'Regional Learning Association','address':'10 Main St','city':'Oakland','state':'CA','zip':'94612','status':'Active'},
          {'orgID':'102','ein':'123456789','orgName':'Regional Learning Association Former Name','address':'20 East St','city':'Concord','state':'CA','zip':'94520','status':'Closed'}]
    def choose(self,rows):
        org=c.checker.Organization('Regional Learning Association','123456789')
        with patch.object(c,'public_profile_for_ein',return_value={'organization':{'ein':123456789,'city':'Concord','state':'CA'}}):
            return c.ny_select_confirmed_duplicate(org,rows,{r['orgID']:r for r in rows}.__getitem__)
    def test_active_original_beats_closed_profile_office_in_both_orders(self):
        for rows in itertools.permutations(self.records()):
            self.assertEqual(self.choose(rows)['orgID'],'101')
    def test_equal_active_prefers_original_before_profile_city(self):
        rows=self.records();rows[1]['status']='Active'
        self.assertEqual(self.choose(rows)['orgID'],'101')
    def test_same_name_active_beats_closed_profile_office(self):
        rows=self.records();rows[1]['orgName']=rows[0]['orgName']
        self.assertEqual(self.choose(rows)['orgID'],'101')
    def test_address_remains_tiebreak_for_equivalent_active_names(self):
        rows=self.records();rows[1].update(orgName=rows[0]['orgName'],status='Active')
        self.assertEqual(self.choose(rows)['orgID'],'102')
    def test_different_ein_cannot_be_confirmed_by_name_or_address(self):
        rows=self.records();rows[0]['ein']='999999999'
        with self.assertRaises(ValueError):self.choose(rows)
    def test_identical_rank_remains_ambiguous(self):
        rows=self.records();rows[1]={**rows[0],'orgID':'102'}
        with self.assertRaises(ValueError):self.choose(rows)
    def test_duplicate_detail_must_have_matching_record_id(self):
        rows=self.records();org=c.checker.Organization(rows[0]['orgName'],'123456789')
        with self.assertRaises(ValueError):c.ny_select_confirmed_duplicate(org,rows,lambda key:{**rows[0],'orgID':'bad'})
    def test_missing_name_cannot_be_selected(self):
        rows=self.records();rows[0]['orgName']=''
        with self.assertRaises(ValueError):self.choose(rows)

if __name__=='__main__':unittest.main(verbosity=2)
