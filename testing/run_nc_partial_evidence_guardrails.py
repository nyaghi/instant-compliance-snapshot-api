"""Completed source evidence survives a later failure; no live requests."""
import copy
import time
import unittest
from unittest.mock import patch
import registry_snapshot_server as cc
from testing.run_final_four_source_guardrails import NC, NC_PROFILE, AsOf


class PartialEvidenceControls(unittest.TestCase):
    def record(self,name='Beacon Literacy Network'):
        card={**NC,'CSL Legal Name':name}
        fields={**NC_PROFILE,'Name':name}
        search={'state':'NC','operation':'search','name':name}
        detail={'state':'NC','operation':'detail','identifier':card['License'],'url':card['profile_url']}
        return {'state':'NC','organization_name':name,'ein':'123456789','mode':'standard','alternate_names':[],
                'issued':time.time()-10,'completed':[
                    {'query':search,'evidence':{'query':search,'state':'NC','complete':True,'verification_pending':False,'total':1,'rows':[card]}},
                    {'query':detail,'evidence':{'query':detail,'complete':True,'fields':fields}}],
                'pending':{'query':{'state':'NC','operation':'search','name':'Beacon'}}}

    def test_completed_profile_retained_for_review_without_extra_requests(self):
        for name in ['Beacon Literacy Network','Harbor Animal Rescue']:
            with self.subTest(name=name),patch.object(cc,'date',AsOf),patch.object(cc,'reconciled_registry_address',side_effect=AssertionError('No new lookup')):
                rows=cc.nc_completed_candidates_for_review(self.record(name))
                self.assertEqual(len(rows),1)
                self.assertEqual(rows[0]['name'],name)
                self.assertEqual(rows[0]['_identity_outcome'],'possible')
                self.assertEqual(rows[0]['expiration'].isoformat(),'2026-11-15')

    def test_partial_or_mismatched_details_are_not_review_candidates(self):
        base=self.record()
        mutations=[lambda r:r['completed'].pop(),
                   lambda r:r['completed'][1]['evidence'].update(complete=False),
                   lambda r:r['completed'][1]['evidence']['fields'].update({'Registration #':'SL999999'}),
                   lambda r:r['completed'][1]['query'].update(url='https://unrelated.invalid'),
                   lambda r:r['completed'][0]['evidence'].update(total=2)]
        for mutate in mutations:
            r=copy.deepcopy(base);mutate(r)
            self.assertEqual(cc.nc_completed_candidates_for_review(r),[])

    def test_related_entity_and_different_state_not_added(self):
        record=self.record()
        record['organization_name']='Different Research Foundation'
        self.assertEqual(cc.nc_completed_candidates_for_review(record),[])
        record=self.record();record['state']='NV'
        self.assertEqual(cc.nc_completed_candidates_for_review(record),[])

    def test_failure_retains_incomplete_status_and_review_context(self):
        captured=[]
        def render(result,*args):
            captured.append(result)
            return {'status':result.status,'success':result.success}
        with patch.object(cc,'response_data_for_lookup',side_effect=render):
            result=cc.final_four_connector_failure(self.record(),'NY_CONNECTOR_REGISTRY_NC_CARD_CHANGED')
        self.assertEqual(result['status'],'Unable to Confirm')
        self.assertFalse(result['success'])
        self.assertFalse(captured[0]._cc_identity_review['search_complete'])
        self.assertIn('Rejecting them does not establish non-registration',result['comments'])


if __name__=='__main__':unittest.main()
