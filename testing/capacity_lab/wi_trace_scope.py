"""Normalize only passive WI observation, tested against the prior whole engine."""
import ast

def strip_wi_trace_engine(tree):
    from testing.capacity_lab.failure_label_scope import strip_failure_labels
    strip_failure_labels(tree)
    from testing.capacity_lab.identity_grace_scope import strip_identity_grace_engine
    strip_identity_grace_engine(tree)
    added = {'wi_transport_route', 'observe_wi_transport'}
    if not any(getattr(n, 'name', '') in added for n in tree.body): return
    tree.body[:] = [n for n in tree.body if getattr(n, 'name', '') not in added]
    fn = next(n for n in tree.body if getattr(n, 'name', '') == 'observe_transport')
    guards = [n for n in fn.body if isinstance(n, ast.If) and ast.unparse(n.test) == "state == 'WI'"]
    assert len(guards) == 1 and 'observe_wi_transport(master, sink)' in ast.unparse(guards[0])
    fn.body.remove(guards[0])

def strip_wi_trace_worker(tree):
    from testing.capacity_lab.failure_label_scope import strip_failure_labels
    strip_failure_labels(tree)
    fn = next((n for n in tree.body if getattr(n, 'name', '') == 'log_transport_failure'), None)
    if fn is None: return  # A chained whole-file comparison may already have stripped it.
    for n in ast.walk(fn):
        if isinstance(n, ast.Set):
            if ast.unparse(n) == "{'MI', 'NJ', 'WI'}": n.elts.pop()
            if ast.unparse(n) == "{'disclaimer', 'search', 'results', 'configuration', 'verification', 'query', 'registration', 'details', 'reader'}": n.elts.pop()
