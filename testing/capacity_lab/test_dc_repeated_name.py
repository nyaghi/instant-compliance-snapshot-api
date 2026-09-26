"""DC malformed-source identity recovery and whole-master scope controls."""
import ast
import copy
import json
from pathlib import Path
import subprocess
import time
import unittest
from unittest.mock import patch
import registry_snapshot_server as cc
from testing.capacity_lab.dc_scope import remove_dc_recovery

ROOT = Path(__file__).resolve().parents[2]
LEGAL = 'National Low Income Housing Coalition and Low Income Housing Information Service'
RAW = LEGAL + 'nd Low Incomend Low Income Housing Information Services'


class DcRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.org = cc.checker.Organization('National Low Income Housing Coalition', '521089824')
        self.token = cc.REVIEWED_NAME_CONTEXT.set({self.org.ein: [LEGAL]})
        self.addCleanup(cc.REVIEWED_NAME_CONTEXT.reset, self.token)
        self.row = dict(name=RAW, aliases=[], identifier='400215000366', status='Current',
                        raw_status='Active', expiration=cc.date(2027,5,31), location='',
                        street='1000 VERMONT AVE NW Suite 500', region='DC', postal_code='20005')
        self.record = dict(ein=self.org.ein, source='CA', names=[LEGAL], address_role='organization',
                           street='1000 VERMONT AVE, NW, SUITE 500', state='DC', postal_code='20005',
                           city='WASHINGTON', source_url='https://state.example/record')
        self.source = patch.object(cc, 'identity_source_result', return_value={'organization_records':[self.record]})
        self.source.start(); self.addCleanup(self.source.stop)
        self.address = patch.object(cc, 'reconciled_registry_address', return_value={'decision':'unavailable'})
        self.address.start(); self.addCleanup(self.address.stop)

    def result(self, rows=None, state='DC'):
        return cc.licensed_charity_result(self.org, state, rows if rows is not None else [self.row],
                                         time.monotonic()+10, 'https://state.example')

    def test_complete_same_ein_legal_name_and_exact_office_recover_record(self):
        r = self.result()
        self.assertEqual(r.status, 'Current')
        self.assertEqual(r.matched_registry_identifier, '400215000366')
        self.assertEqual(r.matched_registry_name, RAW)
        self.assertIn('joined repeated text', r.source_note)
        self.assertEqual(r.identity_evidence['name']['reason'], 'MATCH_EIN_LINKED_NAME_REPEATED_TEXT')

    def test_shared_address_policy_center_is_not_accepted(self):
        sibling = {**self.row, 'name':'National Low Income Housing Policy Center', 'identifier':'400216000400'}
        self.assertEqual(self.result([sibling]).status, 'Not Registered')
        self.assertEqual(self.result([sibling, self.row]).matched_registry_identifier, '400215000366')

    def test_old_closed_record_cannot_displace_confirmed_active_record(self):
        old = {**self.row, 'name':self.org.organization_name, 'identifier':'70105063',
               'status':'Closed / Withdrawn / Canceled', 'raw_status':'Cancelled', 'expiration':cc.date(2020,5,31)}
        self.assertEqual(self.result([old, self.row]).matched_registry_identifier, '400215000366')

    def test_adverse_status_is_not_replaced_by_current(self):
        self.row.update(status='Closed / Withdrawn / Canceled',raw_status='Cancelled')
        self.assertEqual(self.result().status, 'Closed / Withdrawn / Canceled')

    def test_missing_or_conflicting_identity_proof_is_review_not_negative(self):
        for key, value in [('ein','987654321'),('address_role','agent'),('street','999 Another Street'),
                           ('state','VA'),('postal_code','20006'),('names',[self.org.organization_name])]:
            with self.subTest(key=key):
                record = {**self.record,key:value}
                with patch.object(cc,'identity_source_result',return_value={'organization_records':[record]}):
                    self.assertEqual(self.result().status,'Needs Review')

    def test_source_failure_does_not_create_negative(self):
        with patch.object(cc,'identity_source_result',side_effect=TimeoutError()):
            self.assertEqual(self.result().status,'Needs Review')

    def test_explicit_other_ein_cannot_be_overridden(self):
        self.row['ein']='987654321'
        self.assertEqual(self.result().status,'Not Registered')

    def test_rule_is_dc_only(self):
        self.assertEqual(self.result(state='RI').status,'Not Registered')

    def test_new_chapter_or_distinctive_suffix_cannot_be_stripped(self):
        for suffix in (' New York Chapter',' Policy Center','nd Low Income Housing Chapter','nd Wisconsin', 'ndLowInco NEW YORK'):
            self.assertFalse(cc.dc_repeated_name_prefix(LEGAL+suffix,LEGAL),suffix)

    def test_generic_duplicate_join_not_organization_hardcoding(self):
        name='National Coastal Habitat Education Alliance'
        self.assertTrue(cc.dc_repeated_name_prefix(name+'oastal Habitat Education Alliance',name))
        self.assertFalse(cc.dc_repeated_name_prefix(name+' Coastal Habitat Education Alliance',name))
        self.assertFalse(cc.dc_repeated_name_prefix('Aid FundundAidFund','Aid Fund'))

    def test_full_response_pipeline_keeps_recovered_identity(self):
        r=self.result()
        data=cc.response_data_for_lookup(r,r.raw_status_text,self.org,self.org.organization_name,self.org.ein,'DC',time.perf_counter())
        self.assertEqual(data['status'],'Current')
        self.assertEqual(data['matched_registry_identifier'],'400215000366')

    def test_entire_master_unchanged_except_dc_branch_and_two_helpers(self):
        old=ast.parse(subprocess.check_output(['git','show','de45053:registry_snapshot_server.py'],cwd=ROOT).decode())
        new=ast.parse((ROOT/'registry_snapshot_server.py').read_text(encoding='utf-8'))
        remove_dc_recovery(new)
        self.assertEqual(ast.dump(old),ast.dump(new))


if __name__=='__main__': unittest.main(verbosity=2)
