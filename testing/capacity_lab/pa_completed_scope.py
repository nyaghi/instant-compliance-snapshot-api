"""Restore only the proof-gated PA duplicate-confirmation optimization."""
import ast

def strip_pa_completed(tree):
    helper=next((n for n in tree.body if getattr(n,'name','')=='lab_pa_completed_no_match'),None)
    if helper is None:return
    tree.body.remove(helper)
    fn=next(n for n in tree.body if getattr(n,'name','')=='pa_guard_search_completion')
    assert ast.unparse(fn.body[1])=='result._cc_pa_completed_negative = None';fn.body.pop(1)
    guard=next(n for n in fn.body if isinstance(n,ast.If) and ast.unparse(n.test)=="status == 'Not Registered' and negative_complete")
    assert ast.unparse(guard.body[0])=='result._cc_pa_completed_negative = (org.organization_name, ein)';guard.body.pop(0)
    fn=next(n for n in tree.body if getattr(n,'name','')=='run_state_lookup');hits=0
    for node in ast.walk(fn):
        if isinstance(node,ast.BoolOp):
            drop=[n for n in node.values if ast.unparse(n)=='not lab_pa_completed_no_match(result, org)']
            for n in drop:node.values.remove(n);hits+=1
    assert hits==1
