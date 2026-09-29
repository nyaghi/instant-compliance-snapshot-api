"""Normalize only the separately guarded public Washington transport."""
import ast

def strip_wa_public(tree):
    from testing.capacity_lab.pa_completed_scope import strip_pa_completed
    strip_pa_completed(tree)
    helper=next((n for n in tree.body if getattr(n,'name','')=='lab_wa_public_detail'),None)
    if helper is None:return
    tree.body.remove(helper)
    fn=next(n for n in tree.body if getattr(n,'name','')=='search_wa_nm_state')
    wa=next(n for n in fn.body if isinstance(n,ast.If))
    assert ast.unparse(wa.body[0])=='external_result = lab_wa_public_detail(org, module)'
    assert isinstance(wa.body[1],ast.If) and ast.unparse(wa.body[1].test)=='external_result is None'
    assert len(wa.body[1].body)==1 and not wa.body[1].orelse
    wa.body[:2]=wa.body[1].body
