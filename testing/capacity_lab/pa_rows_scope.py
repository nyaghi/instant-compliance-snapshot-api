"""Restore only the independently tested PA row-acquisition helper."""
import ast
def strip_pa_rows(tree):
    from testing.capacity_lab.wa_public_scope import strip_wa_public
    strip_wa_public(tree)
    added=next((n for n in tree.body if getattr(n,'name','')=='pa_name_rows'),None)
    if added is None:return
    tree.body.remove(added)
    fn=next(n for n in tree.body if getattr(n,'name','')=='search_pa_with_name_fallback_core')
    calls=[n for n in ast.walk(fn) if isinstance(n,ast.Call) and ast.unparse(n.func)=='pa_name_rows']
    assert len(calls)==1 and [ast.unparse(a) for a in calls[0].args]==['page','selector']
    calls[0].func=ast.parse('page.locator',mode='eval').body;calls[0].args=calls[0].args[1:]
