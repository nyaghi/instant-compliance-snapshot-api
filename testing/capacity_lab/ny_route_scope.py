"""Normalize only the independently controlled lab NY same-document route."""
import ast

def strip_ny_routed_detail(tree):
    from testing.capacity_lab.nj_grid_scope import strip_nj_complete_grid
    strip_nj_complete_grid(tree)
    helpers={'lab_ny_routed_detail','ny_open_registry_detail'}
    present={getattr(n,'name','') for n in tree.body}&helpers
    if not present:return
    assert present==helpers
    tree.body[:]=[n for n in tree.body if getattr(n,'name','') not in helpers]
    fn=next(n for n in tree.body if getattr(n,'name','')=='ny_browser_registry_response')
    calls=[n for n in ast.walk(fn) if isinstance(n,ast.Lambda) and ast.unparse(n.body)=='ny_open_registry_detail(page, identifier, remaining_ms)']
    assert len(calls)==1
    calls[0].body=ast.parse('page.get_by_role("link", name=identifier, exact=True).click(timeout=remaining_ms())',mode='eval').body
