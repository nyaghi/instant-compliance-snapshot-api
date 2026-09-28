"""Normalize only the independently tested lab Sales grid reuse change."""
import ast

def strip_nj_complete_grid(tree):
    added = {'nj_complete_grid_enabled', 'nj_complete_grid_excludes_org'}
    if not any(getattr(n, 'name', '') in added for n in tree.body):
        return
    tree.body[:] = [n for n in tree.body if getattr(n, 'name', '') not in added]
    fn = next(n for n in tree.body if getattr(n, 'name', '') == 'search_nj_public_details')
    fetch = next(n for n in ast.walk(fn) if isinstance(n, ast.FunctionDef) and n.name == 'fetch')
    for n in ast.walk(fetch):
        if isinstance(getattr(n, 'body', None), list):
            n.body[:] = [v for v in n.body if not (isinstance(v, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'maximum_bytes' for t in v.targets))]
        if isinstance(n, ast.Compare) and ast.unparse(n.left) == 'size' and ast.unparse(n.comparators[0]) == 'maximum_bytes':
            n.comparators[0] = ast.Constant(1_000_000)
    count = 0
    for n in ast.walk(fn):
        if isinstance(n, ast.For) and ast.unparse(n.iter) == 'planned_queries':
            assert ast.unparse(n.body[1]) == "name_payload = {**payload, 'search': query}"
            assert ast.unparse(n.body[2]) == "if nj_complete_grid_enabled():\n    name_payload['pageSize'] = 50"
            assert ast.unparse(n.body[3]) == "named = json.loads(fetch(query_path, 'json', name_payload, tokens[0]))"
            n.body[1:4] = ast.parse("named = json.loads(fetch(query_path, 'json', {**payload, 'search': query}, tokens[0]))").body
            guard = n.body[2]
            assert 'nj_complete_grid_excludes_org(named, org)' in ast.unparse(guard.test)
            guard.test = ast.parse('not (nj_complete_public_zero(named) or nj_complete_other_ein_rows(named, ein))', mode='eval').body
            count += 1
    assert count == 1
