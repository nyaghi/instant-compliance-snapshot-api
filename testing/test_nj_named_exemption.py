"""Complete exemption evidence and master identity checks; no name-only acceptance."""
import copy
import ast
from pathlib import Path
import subprocess
import time
import unittest
from unittest.mock import patch, Mock
import registry_snapshot_server as m
from testing.capacity_lab.test_nj_query_completion import response_body, API


class NamedExemption(unittest.TestCase):
    def setUp(self):
        self.org = m.checker.Organization('Example Relief', '123456789')
        self.row = {'name': 'Example Relief', 'accountnumber': '', 'crsm_filestanding': 'Exempt',
                    'crsm_federalein': '', 'crsm_addressline1': '100 Main Street',
                    'crsm_mailingcity': 'Denver', 'crsm_mailingstate': 'CO'}
        self.data = response_body([self.row])

    def result(self, data=None, decision='corroborated'):
        with patch.object(m, 'reconciled_registry_address', return_value={'decision': decision, 'basis': 'EIN-linked office'}), \
             patch.object(m, 'licensed_charity_street_evidence', return_value=None), \
             patch.object(m, 'known_names_for_ein', return_value=[]):
            return m.nj_name_exemption_result(self.data if data is None else data, self.org, time.monotonic()+1)

    def test_complete_exemption_requires_matching_name_and_confirmed_location(self):
        r = self.result()
        self.assertEqual(r.status, 'Exempt'); self.assertTrue(r.success)
        self.assertEqual(r.matched_registry_identifier, '')
        self.assertEqual(r.address_evidence['decision'], 'corroborated')

    def test_unknown_or_conflicting_location_never_confirms_name_only_record(self):
        for decision in ('unavailable', 'conflict', 'different_ein'):
            self.assertIsNone(self.result(decision=decision))

    def test_other_entity_ein_or_name_cannot_inherit_the_exemption(self):
        for field, value in [('crsm_federalein', '987654321'), ('name', 'Entirely Different Charity'),
                             ('name', 'Example Relief of Texas'), ('crsm_filestanding', 'Compliant')]:
            with self.subTest(field=field):
                self.assertIsNone(self.result(response_body([{**self.row, field:value}])))

    def test_partial_error_duplicate_and_multirow_grids_remain_unconfirmed(self):
        variants=[{**self.data,'MoreRecords':True}, {**self.data,'ItemCount':True},
                  {**self.data,'PageNumber':True}, {**self.data,'Success':False},
                  {**self.data,'Error':'failed'}, response_body([self.row,self.row])]
        duplicate=copy.deepcopy(self.data)
        duplicate['Records'][0]['Attributes'].append({'Name':'name','DisplayValue':'Example Relief'})
        for data in variants+[duplicate]: self.assertIsNone(self.result(data))

    def test_completed_name_query_may_render_an_exemption_without_number(self):
        request=Mock(url=API,method='POST',post_data_json={'search':'Example Relief','page':1})
        response=request.response.return_value
        response.url=API;response.status=200;response.headers={'content-type':'application/json'}
        response.json.return_value=self.data
        self.assertIsNotNone(m.nj_completed_query_rows(request,'Example Relief'))
        self.assertIsNone(m.nj_completed_query_rows(request,'Another Charity'))
        response.json.return_value=response_body([{**self.row,'crsm_filestanding':'Compliant'}])
        self.assertIsNone(m.nj_completed_query_rows(request,'Example Relief'))

    def test_scope_keeps_mature_state_rules_discovery_and_shared_matching_exact(self):
        root=Path(__file__).resolve().parents[1]
        old=ast.parse(subprocess.check_output(['git','show','887ccc7:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        new=ast.parse((root/'registry_snapshot_server.py').read_text(encoding='utf-8'))
        functions=lambda tree:{n.name:ast.dump(n) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        before,after=functions(old),functions(new)
        self.assertEqual({name for name in before if before[name]!=after.get(name)}, {
            'nj_completed_query_rows','nj_search_body','search_nj_public_details',
            'search_nj_direct','search_nj_with_name_fallback','final_four_browser_lookup',
            'il_verification_recovery','ny_connector_request'})
        self.assertEqual(set(after)-set(before),{'nj_name_exemption_result'})


if __name__ == '__main__': unittest.main()
