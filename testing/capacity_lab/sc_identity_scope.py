"""Normalize separately tested SC identity checks in historical master guards."""
import ast
from pathlib import Path
import subprocess


def restore_sc_identity_guard(tree):
    helper=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='sc_related_entity_requires_ein')
    if len(helper.args.args)==2:return
    assert [a.arg for a in helper.args.args]==['original','candidate','ein']
    old=ast.parse(subprocess.check_output(['git','show','ed83811:registry_snapshot_server.py'],
        cwd=Path(__file__).resolve().parents[2]).decode('utf-8'))
    for name in ('sc_related_entity_requires_ein','sc_official_detail_lookup','debug_trace_for_result'):
        prior=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name==name)
        index=next(i for i,n in enumerate(tree.body) if isinstance(n,ast.FunctionDef) and n.name==name)
        tree.body[index]=prior
