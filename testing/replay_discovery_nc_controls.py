"""Recorded discovery/NC source controls, not a fresh full-workflow run.

The original completed NC result metadata reconstructs source-card fields;
new captures contain the actual public card fields. Neither supplies a full
browser continuation history or validates live workflow speed.
"""
import ast
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import registry_snapshot_server as cc
from testing.test_discovery_cap_nc_scope import CONSULTANT

ART = ROOT.parent
OUTPUTS = ART.parent
SAVED = OUTPUTS / 'lab-as-staging-20261010/validation-nc-ms-20261011/nc-21-first-pass-29.2EI-0.6.126.json'
BASELINE = OUTPUTS / 'wv-fritsch-fix-20261012/repo/registry_snapshot_server.py'


def main():
    controls = json.loads((ART / 'control31-current.json').read_text(encoding='utf-8'))['controls']
    saved = {r['ein'].replace('-', ''): r for r in json.loads(SAVED.read_text(encoding='utf-8'))}
    live = {r['row']: r for r in json.loads((ART / 'nc-live-source-controls.json').read_text(encoding='utf-8'))}
    gate_path = ART / 'gate6-live-discovery.json'
    gates = {r['row']: r for r in json.loads(gate_path.read_text(encoding='utf-8'))} if gate_path.exists() else {}
    namespace = dict(vars(cc))
    source_functions = {'nc_charity_record_evidence', 'final_four_search_evidence', 'final_four_clean_evidence'}
    for node in ast.parse(BASELINE.read_text(encoding='utf-8')).body:
        if isinstance(node, ast.FunctionDef) and node.name in source_functions:
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(BASELINE), 'exec'), namespace)
    report = {'scope': 'Source-card interpretation and discovered-name selection replay; not full workflow regression',
              'baseline_commit': '10607eb', 'nc': [], 'discovery': [], 'gaps': []}
    for control in controls:
        row, ein = control['row'], control['ein'].replace('-', '')
        prior = saved.get(ein)
        evidence = live.get(row)
        if evidence:
            raw_rows = copy.deepcopy(evidence['rows'])
            assert evidence['displayed_total'] == len(raw_rows), (row, 'Incomplete displayed count')
            query_name = evidence['query']
            source = 'Fresh public source cards collected in the existing Compliance Express Chrome tab'
        elif prior and prior['results'][0]['success']:
            result = prior['results'][0]
            source = 'Reconstructed card from completed October 11 result metadata; not original raw collector payload'
            query_name = control['organization_name']
            if result['status'] == 'Not Registered':
                raw_rows = []
                source = 'Saved completed no-record result; not a fresh search or full raw continuation'
            else:
                identifier = result['matched_registry_identifier']
                due = result.get('computed_due_date') or ''
                raw_rows = [{'CSL Legal Name': result['matched_registry_name'],
                             'CSL Type': 'In-Process' if identifier.startswith('NCAPP-') else
                                         'CSL Exempt Organization' if result['status'] == 'Exempt' else 'Charitable Organization',
                             'Status': result['raw_status_text'],
                             'License': '' if identifier.startswith('NCAPP-') else identifier,
                             'Expiration Date': due, 'profile_url': result['source_url']}]
                if 'extension end date' in result.get('source_note', ''):
                    raw_rows[0]['Extension End Date'] = due
        else:
            report['gaps'].append({'row': row, 'scope': 'NC source', 'reason': 'No completed saved evidence or new card capture'})
            continue
        query = {'state': 'NC', 'operation': 'search', 'name': query_name}
        payload = {'state': 'NC', 'query': query, 'complete': True, 'verification_pending': False,
                   'search_mode': 'STARTS_WITH', 'total': len(raw_rows), 'rows': raw_rows}
        namespace['final_four_clean_evidence'](payload, query)
        cc.final_four_clean_evidence(payload, query)
        before = namespace['final_four_search_evidence'](payload, 'NC', query)
        after = cc.final_four_search_evidence(payload, 'NC', query)
        assert before == after, (row, 'NC interpretation regression')
        mixed = {**payload, 'rows': [*raw_rows, copy.deepcopy(CONSULTANT)], 'total': len(raw_rows)+1}
        cc.final_four_clean_evidence(mixed, query)
        assert cc.final_four_search_evidence(mixed, 'NC', query) == after, (row, 'Consultant displaced a charity')
        approved_names = prior['alternate_names'] if prior else [n['name'] for n in gates.get(row, {}).get('names', []) if n.get('selected')]
        token = cc.REVIEWED_NAME_CONTEXT.set({ein: tuple(approved_names)})
        try:
            identities = [{'identifier': r['identifier'], 'name': r['name'], 'status': r['status'],
                           'scores': cc.final_four_search_candidate_scores(control['organization_name'], ein, 'NC', r)}
                          for r in after]
        finally:
            cc.REVIEWED_NAME_CONTEXT.reset(token)
        plausible_statuses = sorted({item['status'] for item in identities
                                     if any(score['decision'] != 'rejected' for score in item['scores'])})
        expected = control['expected']['NC'].replace(' ', '')
        source_comparison = (any(status.replace(' ', '') == expected for status in plausible_statuses)
                             if plausible_statuses else expected == 'NotRegistered')
        report['nc'].append({'row': row, 'organization_name': control['organization_name'], 'ein': control['ein'],
                             'source': source, 'expected_sheet_status': control['expected']['NC'],
                             'interpreted_records': [{'name': r['name'], 'identifier': r['identifier'], 'status': r['status']}
                                                     for r in after],
                             'candidate_identity_scores': identities, 'plausible_source_statuses': plausible_statuses,
                             'source_comparison_agrees_with_sheet': source_comparison,
                             'comparison_scope': 'Name shortlist and card status only; not final identity or full negative-search confirmation',
                             'mismatch_category': None if source_comparison else 'Needs manual review',
                             'unchanged': True, 'consultant_injection_preserved_all_records': True})
        discovery = prior['discovery']['names'] if prior else gates.get(row, {}).get('names')
        if discovery is None:
            report['gaps'].append({'row': row, 'scope': 'Discovery', 'reason': 'Gate 6 discovery capture not yet available'})
            continue
        original = copy.deepcopy(discovery)
        selected = cc.prioritized_discovery_names(control['organization_name'], discovery)
        assert len(selected) <= 7
        assert discovery == original, 'Selection mutated evidence'
        report['discovery'].append({'row': row, 'organization_name': control['organization_name'],
                                    'before_count': len(discovery), 'after_count': len(selected),
                                    'unchanged': selected == original,
                                    'omitted_names': [n['name'] for n in discovery if n not in selected],
                                    'baseline_discovery_seconds': prior['discovery_seconds'] if prior else gates[row].get('elapsed'),
                                    'method': 'Saved discovery evidence' if prior else 'Fresh discovery on unchanged live staging, then local selection replay'})
    report['nc_unchanged_count'] = len(report['nc'])
    report['discovery_unchanged_count'] = sum(r['unchanged'] for r in report['discovery'])
    report['workflow_speed_validated'] = False
    report['identity_and_full_query_completion_validated'] = False
    (ART / 'control31-replay-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"NC source interpretation unchanged: {len(report['nc'])}/31; consultant injection preserved each result set")
    print(f"Discovery selection unchanged: {report['discovery_unchanged_count']}/{len(report['discovery'])}; gaps: {len(report['gaps'])}")


if __name__ == '__main__':
    main()
