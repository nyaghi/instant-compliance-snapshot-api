"""Normalize only the fixed passive failure-label additions."""
import ast


def strip_failure_labels(tree):
    from testing.capacity_lab.me_trace_scope import strip_me_transport_trace
    strip_me_transport_trace(tree)
    failures={'net::ERR_FAILED', 'net::ERR_ABORTED', 'net::ERR_TIMED_OUT',
        'net::ERR_CONNECTION_RESET', 'net::ERR_CONNECTION_CLOSED',
        'net::ERR_NAME_NOT_RESOLVED', 'net::ERR_HTTP2_PROTOCOL_ERROR',
        'net::ERR_BLOCKED_BY_CLIENT', 'net::ERR_INTERNET_DISCONNECTED'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            labels=[n for n in node.body if isinstance(n,ast.Assign)
                    and ast.unparse(n.targets[0])=='safe_status']
            if labels:
                assert len(labels)==1
                i=node.body.index(labels[0])
                assert ast.unparse(node.body[i-1])=="status = getattr(result, 'status', '')"
                assert ast.unparse(node.body[i+1])=="self.record('attempt_return', result_status=safe_status)"
                assert isinstance(labels[0].value,ast.IfExp)
                assert ast.unparse(labels[0].value.body)=='status'
                assert ast.unparse(labels[0].value.orelse)=="'other'"
                assert set(ast.literal_eval(labels[0].value.test.comparators[0]))=={
                    'Current','Upcoming Filing','Delinquent','Not Registered','Not registered','Delinquent/Non-compliant','Not Found',
                    'Site Not Reachable','Unable to Confirm','Unable to Verify','Unknown',
                    'Suspended','Revoked','Closed / Withdrawn / Canceled'}
                node.body[i-1:i+2]=ast.parse("self.record('attempt_return')").body
        if isinstance(node,ast.For):
            added=[n for n in node.body if isinstance(n,ast.If)
                   and ast.unparse(n.test).startswith("row.get('result_status') in ")]
            for n in added:
                assert ast.unparse(n.body[0])=="event['result_status'] = row['result_status']"
                assert len(n.body)==1 and not n.orelse
                assert set(ast.literal_eval(n.test.comparators[0]))=={
                    'Current','Upcoming Filing','Delinquent','Not Registered','Not registered','Delinquent/Non-compliant','Not Found',
                    'Site Not Reachable','Unable to Confirm','Unable to Verify','Unknown',
                    'Suspended','Revoked','Closed / Withdrawn / Canceled','other'}
                node.body.remove(n)
    fn=next((n for n in tree.body if getattr(n,'name','')=='observe_browser_transport'),None)
    if fn:
        for node in ast.walk(fn):
            if isinstance(node,ast.If):
                added=[n for n in node.body if isinstance(n,ast.If)
                       and ast.unparse(n.test)=="event == 'browser_failed'"]
                for n in added:
                    assert len(n.body)==2 and not n.orelse
                    assert ast.unparse(n.body[0])=='failure = request.failure'
                    guard=n.body[1]
                    assert ast.literal_eval(guard.test.comparators[0])==failures
                    assert ast.unparse(guard.body[0])=="details['failure'] = failure"
                    node.body.remove(n)
    fn=next((n for n in tree.body if getattr(n,'name','')=='log_browser_failure'),None)
    if fn:
        for node in ast.walk(fn):
            if isinstance(node,ast.Dict):
                indexes=[i for i,k in enumerate(node.keys) if isinstance(k,ast.Constant) and k.value=='failure']
                for i in reversed(indexes):
                    assert ast.literal_eval(node.values[i])==failures
                    node.keys.pop(i); node.values.pop(i)


def assert_diagnostics_only(root, reference, path):
    import subprocess
    old=ast.parse(subprocess.check_output(['git','show',reference+':'+path],cwd=root).decode())
    new=ast.parse((root/path).read_text())
    strip_failure_labels(new)
    assert ast.dump(old)==ast.dump(new),path
