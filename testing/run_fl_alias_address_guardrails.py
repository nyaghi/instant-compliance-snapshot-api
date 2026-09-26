"""Alternate-name collision controls; no network and no organization exceptions."""
import sys
import ast
import subprocess
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c


class FloridaAliasControls(unittest.TestCase):
    def setUp(self):
        self.org=SimpleNamespace(organization_name='Example Relief Inc',ein='123456789')
        token=c.REVIEWED_NAME_CONTEXT.set({'123456789':('Community Care',)})
        self.addCleanup(c.REVIEWED_NAME_CONTEXT.reset,token)

    def row(self,name='Community Care Inc',place='Madison, WI',credential='CH900'):
        header=name.upper()+(f', {place.upper()}' if place else '')
        return {'index':0,'text':f'{header} Print Registration Number :{credential} Expiration Date :12/31/2027'}

    def run_lookup(self,rows,decisions):
        page=MagicMock()
        page.expect_navigation.return_value.__enter__.return_value.value=SimpleNamespace(status=200)
        page.evaluate.side_effect=rows
        with patch.object(c,'reviewed_queries_first',return_value=['Community Care','Example Relief']), \
             patch.object(c.checker,'find_visible_input',return_value=page), \
             patch.object(c,'readable_page_text',return_value='Search Results Registration Number CH900'), \
             patch.object(c,'no_registry_results_seen',return_value=False), \
             patch.object(c,'registry_candidate_fields',return_value={'status':'Current'}), \
             patch.object(c,'reconciled_registry_address',side_effect=decisions) as address, \
             patch.object(c.time,'sleep'):
            result=c.search_fl(page,self.org)
        return result,address

    def test_primary_name_has_no_new_network_or_address_gate(self):
        result,address=self.run_lookup([[self.row('Example Relief Inc')]],[])
        self.assertTrue(result.success);self.assertEqual(result.matched_registry_identifier,'CH900')
        address.assert_not_called()

    def test_primary_corporate_suffix_variant_is_unchanged(self):
        with patch.object(c,'reconciled_registry_address') as address:
            value=c.fl_reviewed_alias_address(self.org,'EXAMPLE RELIEF','EXAMPLE RELIEF, Boston, MA Print',time.monotonic()+3)
        self.assertEqual(value,{});address.assert_not_called()

    def test_entered_primary_slash_segment_is_not_discovered_alias_only(self):
        self.org.organization_name='Community Care / CC'
        with patch.object(c,'reconciled_registry_address') as address:
            value=c.fl_reviewed_alias_address(self.org,'Community Care Inc',self.row()['text'],time.monotonic()+3)
        self.assertEqual(value,{});address.assert_not_called()

    def test_conflicting_alias_is_not_accepted_as_the_requested_entity(self):
        conflict={'decision':'conflict','ein_linked_location':'Chicago, IL'}
        result,address=self.run_lookup([[self.row()],[self.row('Unrelated Legal Entity')]], [conflict])
        self.assertFalse(result.success);self.assertEqual(result.status,'Unable to Confirm')
        self.assertEqual(result.reason_code,'FL_ALIAS_IDENTITY_UNCONFIRMED')
        self.assertIn('Chicago, IL',result.source_note);self.assertIn('MADISON, WI',result.source_note)
        self.assertFalse(result.matched_registry_identifier)
        self.assertEqual(address.call_args.kwargs['registry_state'],'FL')

    def test_continue_after_conflict_and_find_primary(self):
        result,_=self.run_lookup([[self.row()],[self.row('Example Relief Inc','Chicago, IL','CH100')]], [{'decision':'conflict'}])
        self.assertTrue(result.success);self.assertEqual(result.matched_registry_identifier,'CH100')

    def test_confirmed_alias_retains_state_status_and_evidence(self):
        result,_=self.run_lookup([[self.row()]], [{'decision':'corroborated','basis':'Same-EIN organization office matches.'}])
        self.assertTrue(result.success);self.assertEqual(result.status,'Current')
        self.assertEqual(result.identity_anchor,'cross_state_name_address')
        self.assertEqual(result.address_evidence['registry_location'],'MADISON, WI')

    def test_missing_address_and_unavailable_profile_are_review(self):
        for place in ('Madison, WI',''):
            with self.subTest(place=place):
                result,_=self.run_lookup([[self.row(place=place)],[self.row('Unrelated Legal Entity')]], [{'decision':'unavailable'}])
                self.assertFalse(result.success);self.assertEqual(result.status,'Unable to Confirm')

    def test_header_location_only_not_soliciting_alias_or_other_row(self):
        text='Community Care Inc, Madison, WI Print Also Soliciting as Help, Albany, NY Registration Number CH900'
        with patch.object(c,'reconciled_registry_address',return_value={'decision':'corroborated'}) as address:
            c.fl_reviewed_alias_address(self.org,'Community Care Inc',text,time.monotonic()+5)
        self.assertEqual(address.call_args.args[2],'Madison, WI')

    def test_exhausted_budget_cannot_start_address_requests(self):
        with patch.object(c,'reconciled_registry_address') as address:
            result=c.fl_reviewed_alias_address(self.org,'Community Care Inc',self.row()['text'],time.monotonic()-1)
        self.assertEqual(result['decision'],'unavailable');address.assert_not_called()

    def test_unrelated_completed_record_remains_negative(self):
        result,address=self.run_lookup([[self.row('Unrelated Legal Entity')],[self.row('Unrelated Legal Entity')]],[])
        self.assertEqual(result.status,c.checker.STATUS_NOT_REGISTERED);address.assert_not_called()

    def test_shared_office_evidence_clears_real_alternate_office_only(self):
        with patch.object(c,'public_profile_for_ein',return_value={'organization':{'ein':123456789,'city':'Chicago','state':'IL'}}), \
             patch.object(c,'registry_cross_state_identity',return_value={'decision':'corroborated','basis':'Same EIN and office in CA.'}) as cross:
            result=c.fl_reviewed_alias_address(self.org,'Community Care Inc',self.row()['text'],time.monotonic()+5)
        self.assertEqual(result['decision'],'corroborated');cross.assert_called_once()

    def test_review_explanation_survives_response_pipeline(self):
        result,_=self.run_lookup([[self.row()],[self.row('Unrelated Legal Entity')]], [{'decision':'conflict','ein_linked_location':'Chicago, IL'}])
        data=c.response_data_for_lookup(result,result.raw_status_text,self.org,self.org.organization_name,self.org.ein,'FL',time.perf_counter())
        self.assertEqual(data['status'],'Unable to Confirm')
        self.assertIn('Chicago, IL',data['comments']);self.assertIn('MADISON, WI',data['comments'])
        self.assertEqual(data['address_evidence']['decision'],'conflict')

    def test_all_other_master_behavior_is_unchanged(self):
        from testing.capacity_lab.fl_alias_scope import remove_fl_alias_guard
        root=Path(__file__).resolve().parents[1]
        old=ast.parse(subprocess.check_output(['git','show','022aa01:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        current=ast.parse((root/'registry_snapshot_server.py').read_text(encoding='utf-8'))
        remove_fl_alias_guard(current)
        self.assertEqual(ast.dump(old),ast.dump(current))


if __name__=='__main__':unittest.main()
