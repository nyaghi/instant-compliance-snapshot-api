"""Exact AST exclusions for the separately tested DC query and NY history changes."""
import ast
from pathlib import Path
import subprocess


def remove_transport_recovery(tree):
    old = ast.parse(subprocess.check_output(['git','show','6eed5f9:registry_snapshot_server.py'],
                    cwd=Path(__file__).resolve().parents[2]).decode())
    def function(tree,name):
        return next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    tree.body.remove(function(tree,'dc_license_query_patterns'))
    current_dc, old_dc = function(tree,'dc_charity_records'), function(old,'dc_charity_records')
    current_loop, old_loop = current_dc.body[2], old_dc.body[2]
    assert ast.unparse(current_loop.iter)=='dc_license_query_patterns(required + generated)'
    assert ast.dump(ast.Module(body=current_loop.body,type_ignores=[]))==ast.dump(ast.Module(body=old_loop.body[-1:],type_ignores=[]))
    current_dc.body[2]=old_loop
    current_ny, old_ny = function(tree,'ny_browser_registry_response'), function(old,'ny_browser_registry_response')
    expected = ast.parse('''search_url = getattr(page, "_cc_ny_search_url", None)
if isinstance(search_url, str) and page.url != search_url:
    page.go_back(wait_until="commit", timeout=remaining_ms())
    page.wait_for_url(search_url, wait_until="commit", timeout=remaining_ms())
''').body
    assert ast.dump(ast.Module(body=current_ny.body[3:5],type_ignores=[]))==ast.dump(ast.Module(body=expected,type_ignores=[]))
    del current_ny.body[3:5]
    search = current_ny.body[3]
    assert ast.unparse(search.body[0])=='page._cc_ny_search_url = page.url'
    del search.body[0]
    assert ast.unparse(search.body[0])=="page.get_by_role('button', name='Clear fields', exact=True).click(timeout=remaining_ms())"
    del search.body[0]
    fields=search.body[0]
    assert len(fields.body)==1 and isinstance(fields.body[0],ast.If)
    assert ast.unparse(fields.body[0].test)=='field in params'
    fields.body=fields.body[0].body
    assert ast.dump(current_ny)==ast.dump(old_ny)
