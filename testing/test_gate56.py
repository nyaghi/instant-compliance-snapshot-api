"""Offline contracts covering the original Gate 56 failures and previously used identities."""
import json
import os
import socket
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import registry_snapshot_server as cc
from deployment import staging_workflows as workflows
from testing.run_final_four_source_guardrails import NC, NC_PROFILE

ROSTER = json.loads((Path(__file__).parent / "fixtures/gate55/LOCAL-70.json").read_text())


class Gate56(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(socket.socket, 'connect', side_effect=AssertionError('offline')))
        self.enterContext(patch.object(cc, 'trial_identity', return_value=True))
        self.enterContext(patch.object(cc, 'reconciled_registry_address', return_value={'decision': 'unavailable'}))
        self.assertEqual(len({row['ein'] for row in ROSTER}), 70)

    def test_nc_mixed_grid_and_bound_profile(self):
        for case in ROSTER:
            query = {'state': 'NC', 'operation': 'search', 'name': case['name']}
            good = {**NC, 'CSL Legal Name': case['name']}
            unrelated = {**NC, 'CSL Legal Name': 'Unrelated license', 'License':'SL000333',
                         'Extension End Date':'', 'profile_url': NC['profile_url'].replace('5700751','5700752')}
            grid = dict(state='NC', query=query, complete=True, verification_pending=False,
                        rows=[unrelated, good], total=2)
            other, selected = cc.final_four_search_evidence(grid, 'NC', query)
            self.assertIsNone(other['expiration'])
            self.assertEqual(other['status'], 'Unable to Confirm')
            self.assertEqual(selected['identifier'], NC['License'])
            detail = {**NC_PROFILE, 'Name': case['name']}
            self.assertEqual(cc.nc_charity_profile_evidence(selected, detail)['expiration'], selected['expiration'])
            with self.assertRaises(ValueError):
                cc.nc_charity_profile_evidence(other, detail)
            with self.assertRaisesRegex(ValueError, 'end date'):
                cc.nc_charity_profile_evidence(selected, {**detail, 'Extension End Date': ''})
            with self.assertRaises(ValueError):
                cc.final_four_search_evidence({**grid, 'total':3}, 'NC', query)

    def test_nv_original_completed_search_and_controls(self):
        row = dict(name='LIRS, LP', identifier='NV20071702661', entity_type='Domestic Limited Partnership (88)')
        org = cc.checker.Organization('Lutheran Immigration and Refugee Service, Inc.', '132574854')
        token = cc.REVIEWED_NAME_CONTEXT.set({org.ein: ['LIRS','Global Refuge']})
        try:
            def collect(q):
                self.assertEqual(q['operation'],'search')
                return dict(state='NV',query=q,total=1,complete=True,verification_pending=False,rows=[row])
            result = cc.final_four_browser_lookup(org,'NV',collect)
            self.assertEqual(result.status, 'Not Registered')
            self.assertEqual(result.rejected_candidates[0]['identifier'], row['identifier'])
            with self.assertRaises(ValueError):
                cc.final_four_browser_lookup(org,'NV',lambda q: {**collect(q), 'complete': False})
        finally:
            cc.REVIEWED_NAME_CONTEXT.reset(token)
        for case in ROSTER:
            for category in ('Domestic Non-Profit Corporation (82)', '', 'Foreign Corporation (80)'):
                self.assertFalse(cc.nv_acronym_partnership(case['name'], {**row,'entity_type':category}))
            self.assertFalse(cc.nv_acronym_partnership(case['name'], {**row,'name':case['name']}))
        self.assertFalse(cc.nv_acronym_partnership(org.organization_name, {**row,'ein':org.ein}))
        self.assertFalse(cc.nv_acronym_partnership('LIRS, LP',row))

    def test_tn_confirm_office_only_for_same_order_and_full_name(self):
        for case in [*ROSTER, dict(name='LOYOLA UNIVERSITY MARYLAND, INC.',ein='520591623')]:
            name = cc.normalized_match_name(case['name']).replace(' of ',' ')
            primary = name if len(name.split())>=3 else name+' community association'
            words=primary.split()
            org=cc.checker.Organization(primary,case['ein'])
            row=dict(name=' '.join([*words[:-1],'of',words[-1]]),identifier='CO14912',ein='')
            with patch.object(cc,'score_candidate',return_value={'decision':'possible','score':55,'reason':'MATCH_RARE_TOKENS'}), patch.object(cc,'licensed_charity_foreign_ein',return_value={}), patch.object(cc,'licensed_charity_street_evidence',return_value={'decision':'corroborated'}):
                self.assertEqual(cc.licensed_charity_identity(org,dict(row),'TN',time.monotonic()+1), 'accepted')
                with patch.object(cc,'licensed_charity_foreign_ein',return_value={'decision':'different_ein'}):
                    self.assertEqual(cc.licensed_charity_identity(org,dict(row),'TN',time.monotonic()+1),'rejected')
                with patch.object(cc,'licensed_charity_street_evidence',return_value={}):
                    self.assertNotEqual(cc.licensed_charity_identity(org,dict(row),'TN',time.monotonic()+1),'accepted')

    def test_poll_receipts_are_client_scoped_and_optional(self):
        master=SimpleNamespace(canonical_ein_digits=str,APP_VERSION='test')
        record=dict(states=['AK','WI'],ein='123456789',mode='standard',name='Example')
        rows=[dict(phase='done',state=s,result=dict(state=s,ein=record['ein'],app_version='test',
                   status='Current',workflow_observation={'trace':'x'*8192})) for s in record['states']]
        with patch.dict(os.environ,CE_STAGING_WORKFLOW_VERSION='test'):
            baseline=workflows.poll_results(master,rows,record,[])
            self.assertEqual(workflows.poll_results(master,rows,record,['AK']),baseline[1:])
            self.assertEqual(workflows.poll_results(master,rows,record,['AK','WI']),[])
            self.assertEqual(workflows.poll_results(master,rows,record,[]),baseline)
            rows[1]['result']['evidence_url']='/state-snapshots/test.pdf'
            self.assertEqual(workflows.poll_results(master,rows,record,[])[1]['evidence_url'],rows[1]['result']['evidence_url'])
            for invalid in ('AK',None,['AL'],[['AK']]):
                with self.assertRaises(ValueError): workflows.poll_results(master,rows,record,invalid)
