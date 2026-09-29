"""Normalize only the separately tested negative-name transport allowance."""
import ast

def strip_nj_name_budget(tree):
    from testing.capacity_lab.identity_grace_scope import strip_identity_grace
    strip_identity_grace(tree)
    fn=next((n for n in tree.body if getattr(n,'name','')=='search_nj_public_details'),None)
    if fn is None:return
    starts=[n for n in fn.body if isinstance(n,ast.Assign) and ast.unparse(n)=='started = time.monotonic()']
    if not starts:return
    assert len(starts)==1
    fn.body.remove(starts[0])
    deadline=next(n for n in fn.body if isinstance(n,ast.Assign) and ast.unparse(n.targets[0])=='deadline')
    assert ast.unparse(deadline.value)=='started + 18.0'
    deadline.value=ast.parse('time.monotonic() + 18.0',mode='eval').body
    count=0
    for node in ast.walk(fn):
        if isinstance(node,ast.If) and ast.unparse(node.test)=='progress is not None and nj_complete_public_zero(data)':
            assert ast.unparse(node.body[0])=='if nj_complete_grid_enabled():\n    deadline = started + 30.0'
            node.body.pop(0);count+=1
    assert count==1
