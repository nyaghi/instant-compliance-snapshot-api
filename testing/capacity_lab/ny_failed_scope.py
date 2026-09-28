"""Restore only the opt-in failed-request wakeup for full master comparisons."""
import ast
def strip_ny_failed_wakeup(tree):
    from testing.capacity_lab.ny_route_scope import strip_ny_routed_detail
    strip_ny_routed_detail(tree)
    added={'NYBrowserConnectionError','lab_ny_failed_request_wakeup','ny_wait_for_completed_or_failed_response'}
    if not any(getattr(n,'name','') in added for n in tree.body):return
    tree.body=[n for n in tree.body if getattr(n,'name','') not in added]
    fn=next(n for n in tree.body if getattr(n,'name','')=='ny_complete_browser_response')
    nodes=[n for n in fn.body if isinstance(n,ast.If) and ast.unparse(n.test)=='lab_ny_failed_request_wakeup()']
    assert len(nodes)==1 and ast.unparse(nodes[0].body[0])=='return ny_wait_for_completed_or_failed_response(page, predicate, submit, remaining_ms)'
    fn.body.remove(nodes[0])
    count=0
    for n in ast.walk(tree):
        if isinstance(n,ast.Tuple) and any(isinstance(v,ast.Name) and v.id=='NYBrowserConnectionError' for v in n.elts):
            assert ast.unparse(n)=='(TimeoutError, checker.PlaywrightTimeoutError, NYBrowserConnectionError)'
            n.elts.pop();count+=1
    assert count==2
