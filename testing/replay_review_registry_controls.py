"""Offline comparison of saved approved controls through master interpretation.

This never calls a registry, launches a browser, or measures live speed. It
cannot validate collection paths whose source responses were not preserved.
"""
import copy
import dataclasses
import json
import socket
import subprocess
import sys
import time
import types
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parents[1] / 'review-registry-fixes-20261014'
OLD = ROOT.parents[1] / 'gigi-denver-diagnostic-20261013'
sys.path.insert(0, str(ROOT))


def deny(*args, **kwargs):
    raise AssertionError('Offline replay cannot make network requests')


def main():
    source = subprocess.check_output(['git', 'show', '3c576dd:registry_snapshot_server.py'], cwd=ROOT).decode('utf-8')
    baseline = types.ModuleType('review_baseline_master')
    baseline.__file__ = str(ROOT / 'registry_snapshot_server.py')
    sys.modules[baseline.__name__] = baseline
    with patch.object(urllib.request, 'urlopen', side_effect=deny), patch.object(socket.socket, 'connect', deny):
        exec(compile(source, baseline.__file__, 'exec'), baseline.__dict__)
        import registry_snapshot_server as candidate
        controls = json.loads((OLD / 'EU-release-controls.json').read_text(encoding='utf-8-sig'))
        fresh = json.loads((OUTPUT / 'fresh-test-renewed.json').read_text(encoding='utf-8-sig'))
        grids = fresh['sheets'][0]['data']
        headers = [v.get('formattedValue', '') for v in grids[0]['rowData'][0]['values']]
        sheet_rows = {}
        for grid in grids[1:]:
            for offset, row in enumerate(grid.get('rowData', [])):
                sheet_rows[grid.get('startRow', 0) + offset + 1] = row.get('values', [])
        saved = json.loads((OLD / 'all31-initial-live-controls.json').read_text(encoding='utf-8-sig'))
        snapshots = {case['ein'].replace('-', ''): case for case in saved}
        records, missing = [], []
        for control in controls:
            ein = control['ein'].replace('-', '')
            values = sheet_rows.get(control['row'], [])
            if len(values) < 2 or values[1].get('formattedValue', '').replace('-', '') != ein:
                raise AssertionError(f'Fresh sheet row/identity changed: {control["row"]}')
            case = snapshots.get(ein)
            if not case:
                missing.append({'ein': ein, 'gap': 'No saved approved result'}); continue
            for original in case.get('results', []):
                state = original['state']
                expected = values[headers.index(state)].get('formattedValue', '')
                result = {'ein': ein, 'name': control['organization_name'], 'state': state,
                          'sheet_expected': expected, 'saved_status': original['status'],
                          'saved_lookup_seconds': original.get('lookup_seconds'), 'kind': 'saved-result interpretation replay'}
                for label, module in [('baseline', baseline), ('candidate', candidate)]:
                    token = module.REVIEWED_NAME_CONTEXT.set({ein: tuple(case.get('alternate_names') or [])})
                    try:
                        fields = {f.name for f in dataclasses.fields(module.checker.StateResult)}
                        obj = module.checker.StateResult(**{k: copy.deepcopy(v) for k, v in original.items() if k in fields})
                        for k, v in original.items():
                            if k not in fields: setattr(obj, k, copy.deepcopy(v))
                        result[label + '_status'] = module.true_status_from_body(obj, original.get('raw_status_text', ''))
                        matched = original.get('matched_registry_name')
                        if matched:
                            proof_ein = original.get('verified_registry_ein') or ''
                            result[label + '_identity'] = module.score_candidate(control['organization_name'], ein,
                                {'name': matched, 'ein': proof_ein})
                    except Exception as exc:
                        result[label + '_gap'] = type(exc).__name__ + ': ' + str(exc)[:180]
                    finally:
                        module.REVIEWED_NAME_CONTEXT.reset(token)
                result['changed'] = (result.get('baseline_status') != result.get('candidate_status') or
                                     result.get('baseline_identity') != result.get('candidate_identity'))
                # Ignore only whitespace around slash-separated labels. Never
                # replace a user-maintained expectation with the saved result.
                normalize = lambda value: '/'.join(part.strip() for part in str(value).split('/'))
                result['matches_current_sheet'] = normalize(expected) == normalize(result.get('candidate_status', ''))
                if not result['matches_current_sheet']:
                    result['mismatch_category'] = 'Needs manual review'
                    result['mismatch_note'] = ('Baseline has the same result; full current source/collector evidence '
                        'is required to reconcile this sheet difference. No expected cell was changed.')
                records.append(result)
        summary = {'kind': 'OFFLINE saved-result interpretation and matching replay; not fresh registry checks',
                   'baseline_commit': '3c576dd', 'approved_organizations': len(controls),
                   'organizations_covered': len({r['ein'] for r in records}), 'comparisons': len(records),
                   'changes': [r for r in records if r['changed']],
                   'gaps': missing + [r for r in records if r.get('baseline_gap') or r.get('candidate_gap')],
                   'current_sheet_mismatches': [r for r in records if not r['matches_current_sheet']],
                   'collection_paths_replayed': False, 'live_speed_validated': False,
                   'states_without_full31_saved_source_coverage': ['AL', 'HI', 'KY', 'MA', 'MS', 'TN'],
                   'records': records}
        (OUTPUT / 'approved31-replay.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print(json.dumps({k: v if k not in {'changes', 'gaps', 'current_sheet_mismatches'} else len(v) for k, v in summary.items() if k != 'records'}, indent=2))
        return 1 if summary['changes'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
