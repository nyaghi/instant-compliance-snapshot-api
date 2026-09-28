"""Restore only the candidate-order wrapper for whole-file scope checks."""
import ast

def strip_global_priority(tree):
    from testing.capacity_lab.start_pacing_scope import strip_start_pacing
    strip_start_pacing(tree)
    helper=next((n for n in tree.body if getattr(n,'name','')=='claim_candidates'),None)
    if helper is None:return
    tree.body.remove(helper)
    queue=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Queue')
    claim=next(n for n in queue.body if getattr(n,'name','')=='claim')
    loops=[n for n in ast.walk(claim) if isinstance(n,ast.For) and isinstance(n.iter,ast.Call)
           and isinstance(n.iter.func,ast.Name) and n.iter.func.id=='claim_candidates']
    assert len(loops)==1
    loop=loops[0]
    assert ast.unparse(loop.target)=='(w, j)'
    assert [ast.unparse(n) for n in loop.iter.args]==[
        'workflows','pending','running','estimates','tail_scores','now',"cfg['source_version']",'protected']
    assert all(isinstance(n,ast.If) for n in loop.body[:2])
    nested=ast.parse("for j in pending.get(w['id'], []):\n pass").body[0]
    nested.body=loop.body[2:]
    loop.target=ast.Name(id='w',ctx=ast.Store());loop.iter=ast.Name(id='workflows',ctx=ast.Load())
    loop.body=loop.body[:2]+[nested]
