"""Prove only Oregon's search acquisition gains a completion fence."""
import ast
import copy
from pathlib import Path
import subprocess


def strip_or_completion(tree):
    helper=next((n for n in tree.body if getattr(n,'name','')=='search_or_completed'),None)
    if helper is None:return
    old=ast.parse(subprocess.check_output(['git','show','e05c18d:registry_snapshot_server.py'],
        cwd=Path(__file__).resolve().parents[2]).decode())
    original=next(n for n in old.body if getattr(n,'name','')=='search_bundled_extension_state')
    expected=copy.deepcopy(original)
    calls=0;guards=0
    for n in ast.walk(expected):
        if isinstance(n,ast.Call) and ast.unparse(n.func)=='module.search_or':
            n.func=ast.Name(id='search_or_completed',ctx=ast.Load())
            n.args.append(ast.Name(id='module',ctx=ast.Load()));calls+=1
        if isinstance(getattr(n,'body',None),list):
            for i,item in reversed(list(enumerate(n.body))):
                if isinstance(item,ast.Assign) and ast.unparse(item)=="result = copy_external_result(org, 'OR', external_result)":
                    n.body[i+1:i+1]=ast.parse('''if getattr(result, "reason_code", "") == "OR_INCOMPLETE_QUERY_RESPONSE":
    result.success = False
    return result
''').body
                    guards+=1
    assert (calls,guards)==(3,2)
    actual=next(n for n in tree.body if getattr(n,'name','')=='search_bundled_extension_state')
    assert ast.dump(actual)==ast.dump(expected), 'Oregon matching/filing rules changed beyond completion guard'
    tree.body[tree.body.index(actual)]=original
    tree.body.remove(helper)

