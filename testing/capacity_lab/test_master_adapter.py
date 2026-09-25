"""Actual master normalization/context with stubbed registry execution only."""
import socket
import ast
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def blocked(*args, **kwargs):
    raise AssertionError('Network disabled during local master integration')


socket.socket.connect = blocked
socket.getaddrinfo = blocked
import registry_snapshot_server as master
from master_adapter import MasterAdapter
from router import CapacityRouter, Request, Worker, Control


class MasterIntegration(unittest.TestCase):
    def test_only_supplied_name_and_authorized_pa_completion_changes_in_master_ast(self):
        root = Path(__file__).resolve().parents[2]
        baseline = subprocess.check_output(['git', 'show', '35e61ae:registry_snapshot_server.py'], cwd=root).decode('utf-8')
        current = (root / 'registry_snapshot_server.py').read_text(encoding='utf-8')
        before, after = ast.parse(baseline), ast.parse(current)
        old = next(n for n in before.body if isinstance(n, ast.FunctionDef) and n.name == 'resolved_organization_name')
        new = next(n for n in after.body if isinstance(n, ast.FunctionDef) and n.name == 'resolved_organization_name')
        self.assertIsInstance(new.body[1], ast.If)
        self.assertEqual(ast.dump(new.body[1].test), "Name(id='supplied_name', ctx=Load())")
        new.body.pop(1)
        # CPU optimizations only wrap pure operations; their rule bodies must
        # remain byte-for-byte equivalent in the AST. The contextual memo key
        # and Kansas exact-workbook cache have dedicated mutation/isolation tests.
        for name in ('canonical_name_punctuation','complete_name_identity_key',
                     'redundant_bracket_acronym_key','organization_match_target_variants'):
            node=next(n for n in after.body if isinstance(n,ast.FunctionDef) and n.name==name)
            self.assertEqual(len(node.decorator_list),1)
            node.decorator_list=[]
        after.body.remove(next(n for n in after.body if isinstance(n,ast.FunctionDef) and n.name=='memoize_reviewed_name_targets'))
        loader=next(n for n in after.body if isinstance(n,ast.FunctionDef) and n.name=='load_ks_weekly_checker')
        cache_assignment=loader.body[1].body.pop()
        self.assertIsInstance(cache_assignment,ast.Assign)
        self.assertEqual(ast.unparse(cache_assignment.targets[0]),'KS_WEEKLY_CHECKER.records_from_workbook_bytes')
        # The Sep 25 request explicitly authorizes PA's response-completion fix.
        # All other master functions, including PA classification and shared
        # matching/discovery rules, must still equal the protected baseline.
        for name in ('search_pa_with_name_fallback', 'search_pa_with_name_fallback_core',
                     'enrich_registration_date_sources', 'fl_verified_registration_issue'):
            for tree in (before,after):
                nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name]
                self.assertEqual(len(nodes),1)
                tree.body.remove(nodes[0])
        # FL date diagnostics are additive metadata, not a classification edit.
        response = next(n for n in after.body if isinstance(n,ast.FunctionDef) and n.name=='response_data_for_lookup')
        lists=[n for n in ast.walk(response) if isinstance(n,ast.List) and any(
            isinstance(e,ast.Constant) and e.value=='registration_date_diagnostics' for e in n.elts)]
        self.assertEqual(len(lists),1)
        lists[0].elts=[e for e in lists[0].elts if not isinstance(e,ast.Constant) or e.value!='registration_date_diagnostics']
        self.assertEqual(ast.dump(before), ast.dump(after))

    def test_supplied_name_does_not_fetch_unused_fallback_metadata(self):
        with patch.object(master, 'organization_name_for_ein', side_effect=AssertionError('Unused reference lookup')), \
             patch.object(master, 'public_profile_name_for_ein', side_effect=AssertionError('Unused remote profile lookup')):
            self.assertEqual(master.resolved_organization_name('123456789', '  Supplied Legal Name  '), 'Supplied Legal Name')

    def test_missing_name_keeps_existing_fallback_order(self):
        with patch.object(master, 'organization_name_for_ein', return_value='Reference Name') as reference, \
             patch.object(master, 'public_profile_name_for_ein', return_value='Profile Name') as profile:
            self.assertEqual(master.resolved_organization_name('123456789', ' '), 'Profile Name')
            reference.assert_called_once()
            profile.assert_called_once()
        with patch.object(master, 'organization_name_for_ein', return_value='Reference Name'), \
             patch.object(master, 'public_profile_name_for_ein', return_value=''):
            self.assertEqual(master.resolved_organization_name('123456789', ''), 'Reference Name')

    def test_15_organizations_32_states_preserve_master_name_scope_and_result_fields(self):
        expected, observed, lock = {}, [], threading.Lock()
        states = list(master.SUPPORTED_STATES)
        self.assertEqual(len(states), 32)
        def registry(name, ein, state):
            key = master.canonical_ein_digits(ein)
            names = master.known_names_for_ein(ein)
            self.assertEqual(names, expected[key]['alternate_names'])
            self.assertEqual(name, expected[key]['organization_name'])
            time.sleep(.0005)
            self.assertEqual(master.known_names_for_ein(ein), names)
            self.assertEqual(set(master.REVIEWED_NAME_CONTEXT.get()), {key})
            row = {'ein': ein, 'state': state, 'organization_name': name, 'status': 'Current', 'success': True,
                   'matched_registry_name': names[0], 'matched_registry_identifier': 'record-' + key,
                   'registration_date': '2000-01-01', 'last_filed_period': '2025-06-30',
                   'comments': 'Fixture EIN and address evidence retained',
                   'identity_anchor': {'ein': key, 'locations': ['Oakland, CA', 'Concord, CA']}}
            with lock:
                observed.append(row)
            return row
        adapter = MasterAdapter(master)
        workers = [Worker(f'{pool}-{i}', pool, {'browser': 2}, adapter) for pool in ('a', 'b') for i in range(6)]
        with patch.object(master, 'run_single_state_lookup_reliably', side_effect=registry):
            with CapacityRouter(workers) as router:
                futures = []
                for org in range(15):
                    ein = f'{org+1:09}'
                    payload = {'ein': ein, 'organization_name': f'Fixture Organization {org}',
                               'alternate_names': [f'Official Former Name {org}', f'Registry DBA {org}']}
                    expected[ein] = payload
                    jobs = [Request(state, {**payload, 'state': state}) for state in states]
                    futures.extend(router.submit('trusted-fixture-workspace', f'org-{org}', jobs, time.monotonic() + 5).values())
                results = [f.result(5) for f in futures]
                router.drain()
        self.assertEqual(len(observed), 480)
        self.assertEqual(len(results), 480)
        self.assertTrue(all(r['success'] and r['status'] == 'Current' for r in results))
        self.assertEqual({(r['ein'], r['state']) for r in results}, {(r['ein'], r['state']) for r in observed})
        self.assertTrue(all(r['registration_date'] == '2000-01-01' and len(r['identity_anchor']['locations']) == 2 for r in results))
        self.assertEqual(master.REVIEWED_NAME_CONTEXT.get(), {})

    def test_reused_worker_does_not_restore_removed_aliases_or_previous_organization(self):
        seen = []
        def registry(name, ein, state):
            seen.append(master.known_names_for_ein(ein))
            return {'ein': ein, 'state': state, 'status': 'Not Registered', 'success': True}
        adapter = MasterAdapter(master)
        with patch.object(master, 'run_single_state_lookup_reliably', side_effect=registry):
            for aliases in (['Reviewed Name'], []):
                adapter({'ein': '123456789', 'organization_name': 'Fixture', 'alternate_names': aliases, 'state': 'CO'}, Control(time.monotonic()+1))
        self.assertEqual(seen, [['Reviewed Name'], []])
        self.assertEqual(master.REVIEWED_NAME_CONTEXT.get(), {})

    def test_unsupported_state_never_calls_registry(self):
        with patch.object(master, 'run_single_state_lookup_reliably', side_effect=AssertionError('Registry called')):
            with self.assertRaises(ValueError):
                MasterAdapter(master)({'ein': '123456789', 'organization_name': 'Fixture', 'state': 'XX'}, Control(time.monotonic()+1))


if __name__ == '__main__':
    unittest.main(verbosity=2)
