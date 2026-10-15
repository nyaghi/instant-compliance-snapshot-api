"""Master retrieval order; no network or organization-specific runtime rules."""
import copy
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import registry_snapshot_server as cc


class CandidatePriorityControls(unittest.TestCase):
    def setUp(self):
        token=cc.REVIEWED_NAME_CONTEXT.set({})
        self.addCleanup(cc.REVIEWED_NAME_CONTEXT.reset,token)

    def test_exact_legal_name_precedes_institutional_affiliates_without_omission(self):
        for base in ['LAHEY CLINIC','RIVER CLINIC']:
            rows=[dict(name=base+suffix,identifier=str(i),aliases=[]) for i,suffix in
                  enumerate([' FOUNDATION, INC.',' HOSPITAL, INC.',', INC.'])]
            before=copy.deepcopy(rows)
            result=cc.prioritized_registry_candidates(base+', INC.','123456789','TN',rows)
            self.assertEqual([r['identifier'] for r in result],['2','0','1'])
            self.assertEqual(rows,before)
            self.assertEqual(cc.final_four_search_candidate_scores(base+', INC.','123456789','TN',rows[0])[0]['decision'],'possible')

    def test_exact_ein_precedes_name_and_conflicting_ein_remains_rejected(self):
        rows=[dict(name='Beacon Literacy',ein='987654321',aliases=[]),
              dict(name='Beacon Literacy',aliases=[]),
              dict(name='Beacon Reading Network',ein='123456789',aliases=[])]
        result=cc.prioritized_registry_candidates('Beacon Literacy','123456789','TN',rows)
        self.assertEqual(result,[rows[2],rows[1],rows[0]])
        self.assertEqual(cc.final_four_search_candidate_scores('Beacon Literacy','123456789','TN',rows[0])[0]['decision'],'rejected')

    def test_reviewed_alias_and_registry_alias_retain_existing_scores(self):
        token=cc.REVIEWED_NAME_CONTEXT.set({'123456789':('Beacon Reading Network',)})
        try:
            rows=[dict(name='Beacon Reading Network',aliases=[]),dict(name='Beacon Literacy',aliases=[])]
            self.assertEqual(cc.prioritized_registry_candidates('Beacon Literacy','123456789','TN',rows),list(reversed(rows)))
        finally:cc.REVIEWED_NAME_CONTEXT.reset(token)

    def test_real_lookup_reads_exact_detail_first_but_still_collects_all_candidates(self):
        name='RIVER CLINIC, INC.'
        rows=[dict(name=n,identifier='CO'+str(i+1),aliases=[],city='BURLINGTON',region='MA')
              for i,n in enumerate(['RIVER CLINIC FOUNDATION, INC.','RIVER CLINIC HOSPITAL, INC.',name])]
        queries=[]
        def evidence(query):
            queries.append(query)
            if query['operation']=='search':
                return dict(state='TN',query=query,complete=True,verification_pending=False,total=3,rows=copy.deepcopy(rows))
            row=next(r for r in rows if r['identifier']==query['identifier'])
            return dict(query=query,complete=True,fields={'Name':row['name'],'CO Number':row['identifier'],
                'Status':'Expired','Registration Date':'01/01/2023','Expiration Date':'03/31/2025',
                'Address':'41 MALL ROAD BURLINGTON MA 01805'})
        with patch.object(cc,'licensed_charity_names',return_value=([name],[])), \
             patch.object(cc,'select_licensed_charity',return_value=(None,'Fixture identity pending')), \
             patch.object(cc,'final_four_license_result',return_value=SimpleNamespace(success=False,status='Unable to Confirm')):
            cc.final_four_browser_lookup(cc.checker.Organization(name,'123456789'),'TN',evidence,time.monotonic()+5)
        self.assertEqual([q['identifier'] for q in queries if q['operation']=='detail'],['CO3','CO1','CO2'])

    def test_new_connector_admission_remains_staging_only_for_mature_routes(self):
        origin='https://fixture-final-four.onrender.com'
        payload=dict(action='start',email='test@compliance-express.com',admin_passcode='fixture',
                     device_id='fixture-device',organization_name='Beacon Literacy',ein='123456789',connector_version='0.6.132')
        with patch.object(cc,'is_verified_internal_passcode',return_value=True), \
             patch.object(cc,'ny_connector_origin_allowed',return_value=True), \
             patch.object(cc,'NY_CONNECTOR_SIGNING_KEY','fixture-'*8), \
             patch.object(cc,'ny_connector_advance',return_value={'phase':'complete','result':{}}):
            for state in ['IL','GA']:
                with patch.object(cc,'trial_identity',return_value={'origin':origin}):
                    code,result=cc.ny_connector_request({**payload,'state':state},origin)
                    self.assertEqual(code,200,result)
                with patch.object(cc,'trial_identity',return_value=None):
                    code,result=cc.ny_connector_request({**payload,'state':state},cc.NY_CONNECTOR_ORIGIN)
                    self.assertEqual(code,400,result)


if __name__=='__main__':unittest.main()
