"""Allow the separately tested FL alias guard in older whole-master AST controls."""
import ast
from pathlib import Path
import subprocess


def remove_fl_alias_guard(tree):
    helper=next((n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='fl_reviewed_alias_address'),None)
    if helper is None:return
    tree.body.remove(helper)
    old=ast.parse(subprocess.check_output(['git','show','022aa01:registry_snapshot_server.py'],
        cwd=Path(__file__).resolve().parents[2]).decode('utf-8'))
    # Florida lookup is the authorized behavior change. All other master
    # functions remain byte-for-AST equivalent except the two FL-only comments.
    old_fn=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name=='search_fl_with_transport')
    index=next(i for i,n in enumerate(tree.body) if isinstance(n,ast.FunctionDef) and n.name==old_fn.name)
    tree.body[index]=old_fn
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='response_data_for_lookup')
    removed=[]
    for node in list(fn.body):
        if isinstance(node,ast.If) and ast.unparse(node.test).startswith("result.state == 'FL' and"):
            assert any(label in ast.unparse(node.test) for label in ['cross_state_name_address','FL_ALIAS_IDENTITY_UNCONFIRMED'])
            fn.body.remove(node);removed.append(node)
    assert len(removed)==2
