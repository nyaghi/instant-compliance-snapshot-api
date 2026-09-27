"""Exact scope proof for completion waits; all matching/rules remain compared."""
import ast, copy, hashlib, subprocess
from pathlib import Path


def strip_ny_body_completion(tree):
    helper=next((n for n in tree.body if getattr(n,'name','')=='ny_complete_browser_response'),None)
    if helper is None:return
    assert hashlib.sha256(ast.dump(helper).encode()).hexdigest()=='22c76d1d0e2b177afb409250a9fd5516d578d4b4acc7e04d50ba71e6cd32aaaa'
    source=subprocess.check_output(['git','show','981510b:registry_snapshot_server.py'],
        cwd=Path(__file__).resolve().parents[2]).decode('utf-8')
    old=ast.parse(source)
    originals={n.name:n for n in old.body if isinstance(n,(ast.ClassDef,ast.FunctionDef))}
    actual={n.name:n for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef))}
    wrapper=copy.deepcopy(originals['NYBrowserResponse'])
    assignment=wrapper.body[1].body[1]
    assert ast.unparse(assignment)=='self.payload = response.json()'
    assignment.value=ast.parse('response.json() if self.status_code == 200 else {}',mode='eval').body
    assert ast.dump(wrapper)==ast.dump(actual[wrapper.name])
    expected=copy.deepcopy(originals['ny_browser_registry_response'])
    # Replace exactly the three existing response acquisition blocks. The
    # predicates, click actions, EIN checks, verification and retry rules stay.
    calls=0
    for parent in ast.walk(expected):
        body=getattr(parent,'body',None)
        if not isinstance(body,list):continue
        for at,node in list(enumerate(body)):
            if not isinstance(node,ast.With) or len(node.items)!=1:continue
            ctx=node.items[0].context_expr
            if not isinstance(ctx,ast.Call) or ast.unparse(ctx.func)!='page.expect_response':continue
            assert len(node.body)==1 and isinstance(node.body[0],ast.Expr)
            predicate=ctx.args[0];action=node.body[0].value
            call=ast.Call(func=ast.Name(id='ny_complete_browser_response',ctx=ast.Load()),
                args=[ast.Name(id='page',ctx=ast.Load()),predicate,
                      ast.Lambda(args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),body=action),
                      ast.Name(id='remaining_ms',ctx=ast.Load())],keywords=[])
            following=body[at+1]
            if isinstance(following,ast.Assign):
                assert ast.unparse(following)=='verified = verification.value'
                replacement=copy.deepcopy(following);replacement.value=call
                body[at:at+2]=[replacement]
            else:
                assert ast.unparse(following)=='return NYBrowserResponse(pending.value)'
                body[at:at+2]=[ast.Assign(targets=[ast.Name(id='response',ctx=ast.Store())],value=call),
                    ast.parse('return NYBrowserResponse(response)').body[0]]
            calls+=1
    assert calls==3
    assert ast.dump(expected)==ast.dump(actual[expected.name]), 'NY change exceeded response completion scope'
    tree.body=[copy.deepcopy(originals[n.name]) if getattr(n,'name','') in {'NYBrowserResponse','ny_browser_registry_response'} else n
               for n in tree.body if n is not helper]
