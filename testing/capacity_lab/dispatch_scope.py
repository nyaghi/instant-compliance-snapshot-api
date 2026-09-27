"""Exact allowance for the separately controlled Sales workflow ordering."""
import ast

def strip_dispatch_fairness(tree):
    helper = next((n for n in tree.body if getattr(n, 'name', '') == 'order_workflows'), None)
    if helper is None: return
    tree.body.remove(helper)
    q = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Queue')
    fn = next(n for n in q.body if getattr(n, 'name', '') == 'claim')
    expected = "order_workflows(workflows, pending, running, self.sales_policy, cfg['source_version'])"
    matches = [n for n in ast.walk(fn) if isinstance(n, ast.Expr) and ast.unparse(n) == expected]
    assert len(matches) == 1
    original = ast.parse("workflows.sort(key=lambda w: (running[w['id']], w['dispatched'], w['submitted'], w['id']))").body[0]
    for node in ast.walk(fn):
        for field, value in ast.iter_fields(node):
            if isinstance(value, list) and matches[0] in value:
                value[value.index(matches[0])] = original
                return
    raise AssertionError('Missing exact workflow-order call')
