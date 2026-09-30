"""Expanded MS legal description: full name plus EIN-linked office evidence."""
import ast
import subprocess
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import registry_snapshot_server as c

NAME = 'Focus on the Family'
EIN = '953188150'
SOURCE_NAME = NAME + ', a California nonprofit religious corporation'
DETAIL = f'''{SOURCE_NAME}
Purpose
SPREAD THE GOSPEL OF JESUS CHRIST
Filing Information
Filing Number:\t100002691
Filing Status:\tCurrent - Exempted
Initial Date Filed:
Expiration Date:
Address
8655 Explorer Drive
Colorado Springs, CO\u00a080920
Contact Information
Registered Name:\t{SOURCE_NAME}
Business Phone:\t1-719-531-3400
Web Address:
'''


class Tests(unittest.TestCase):
    def setUp(self):
        self.org = c.checker.Organization(NAME, EIN)
        self.token = c.REVIEWED_NAME_CONTEXT.set({})

    def tearDown(self):
        c.REVIEWED_NAME_CONTEXT.reset(self.token)

    def record(self, name=SOURCE_NAME, detail=DETAIL, ein=''):
        return SimpleNamespace(organization_name=name, matched_registry_name=name,
            status='Exempt', success=True, raw_status_text='Current - Exempted',
            source_note='', source_url='https://charities.sos.ms.gov/',
            verified_registry_ein=ein,
            ms_detail_identity=c.ms_detail_identity_fields(detail, name))

    def run_record(self, record, address='corroborated'):
        with patch.object(c, 'ms_name_search_plan', return_value=[NAME]), \
             patch.object(c, 'search_ms_fast', return_value=record), \
             patch.object(c, 'reconciled_registry_address', return_value={
                 'decision': address, 'registry_location': 'Colorado Springs, CO 80920',
                 'ein_linked_location': 'Colorado Springs, CO', 'basis': 'Same-EIN office confirmed.'}), \
             patch.object(c, 'licensed_charity_street_evidence', return_value={}):
            return c.search_batch_browser_state(Mock(), self.org, 'MS')

    def test_live_record_description_and_corroborated_office_accept_exemption(self):
        result = self.run_record(self.record())
        self.assertEqual(c.public_status(result), 'Exempt')
        self.assertEqual(result.matched_registry_name, SOURCE_NAME)
        self.assertEqual(result.identity_confidence['parsed_legal_name'], NAME)
        self.assertIn('EIN-linked', result.source_note)

    def test_unavailable_or_conflicting_address_never_confirms(self):
        for evidence in ['unavailable', 'conflict', 'different_ein']:
            with self.subTest(evidence=evidence):
                result = self.run_record(self.record(), evidence)
                self.assertEqual(c.public_status(result), 'Needs Review')
                self.assertFalse(result.success)

    def test_wrong_ein_dominates_full_name_and_matching_address(self):
        self.assertEqual(c.public_status(self.run_record(self.record(ein='123456789'))), 'Needs Review')

    def test_regional_word_before_legal_description_is_not_removed(self):
        regional = 'Focus on the Family Wisconsin, a California nonprofit religious corporation'
        result = self.run_record(self.record(regional, DETAIL.replace(SOURCE_NAME, regional)))
        self.assertEqual(c.public_status(result), 'Needs Review')

    def test_ordinary_comma_geography_or_chapter_suffix_is_not_legal_description(self):
        for name in [NAME + ', California', NAME + ', California chapter',
                     NAME + ', a California nonprofit religious corporation chapter']:
            with self.subTest(name=name):
                result = self.run_record(self.record(name, DETAIL.replace(SOURCE_NAME, name)))
                self.assertEqual(c.public_status(result), 'Needs Review')

    def test_detail_for_other_candidate_cannot_corroborate(self):
        self.assertEqual(c.ms_detail_identity_fields(DETAIL.replace('Registered Name:\t' + SOURCE_NAME,
            'Registered Name:\tAnother Organization'), SOURCE_NAME), {})
        self.assertEqual(c.public_status(self.run_record(self.record(detail='Please Wait'))), 'Needs Review')

    def test_duplicate_detail_or_agent_section_cannot_corroborate(self):
        for detail in [DETAIL + DETAIL, DETAIL.replace('\nAddress\n', '\nAgent Address\n'),
                       DETAIL.replace('\nContact Information\n', '\nOther Information\n')]:
            self.assertEqual(c.ms_detail_identity_fields(detail, SOURCE_NAME), {})

    def test_reviewed_complete_former_name_still_uses_master_identity(self):
        self.org.organization_name = 'Example Requested Name'
        c.REVIEWED_NAME_CONTEXT.set({EIN: (NAME,)})
        result = self.run_record(self.record())
        self.assertEqual(c.public_status(result), 'Exempt')

    def test_expired_budget_performs_no_identity_requests(self):
        with patch.object(c, 'licensed_charity_identity') as identify:
            self.assertFalse(c.ms_legal_description_identity(self.org, self.record(), time.perf_counter() - 1))
        identify.assert_not_called()

    def test_ordinary_exact_name_does_not_add_address_requests(self):
        with patch.object(c, 'ms_legal_description_identity', side_effect=AssertionError('No added request')):
            self.assertEqual(c.public_status(self.run_record(self.record(NAME, DETAIL.replace(SOURCE_NAME, NAME)))), 'Exempt')

    def test_scope_keeps_shared_matching_discovery_budgets_and_other_states_exact(self):
        old = ast.parse(subprocess.check_output(['git', 'show', 'bc56e10:registry_snapshot_server.py'], cwd=ROOT).decode())
        new = ast.parse((ROOT / 'registry_snapshot_server.py').read_text(encoding='utf-8'))
        from testing.performance_origin_audit import restore_nv_business_scope_0613, restore_trial_0614
        new = restore_trial_0614(new)
        new.body = [restore_nv_business_scope_0613(n) if isinstance(n, ast.FunctionDef) else n for n in new.body]
        functions = lambda tree: {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        before, after = functions(old), functions(new)
        self.assertEqual({name for name in before if ast.dump(before[name]) != ast.dump(after[name])},
                         {'search_ms_fast', 'search_batch_browser_state'})
        self.assertEqual(set(after) - set(before), {'ms_detail_identity_fields', 'ms_legal_description_identity'})
        budgets = lambda node: [ast.dump(n) for n in ast.walk(node) if isinstance(n, ast.Assign)
            and any(isinstance(x, ast.Name) and x.id == 'ms_deadline' for x in n.targets)]
        self.assertEqual(budgets(before['search_batch_browser_state']), budgets(after['search_batch_browser_state']))


if __name__ == '__main__':
    unittest.main()
