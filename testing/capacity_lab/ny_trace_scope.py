"""Normalize only passive NY timing for whole-file controls."""
import ast

def strip_browser_trace_engine(tree):
    added={'browser_trace_route','observe_browser_transport'}
    if not any(getattr(n,'name','') in added for n in tree.body):return
    tree.body=[n for n in tree.body if getattr(n,'name','') not in added]
    fn=next(n for n in tree.body if getattr(n,'name','')=='execute')
    count=0
    for node in ast.walk(fn):
        if isinstance(node,ast.With):
            entries=[i for i in node.items if isinstance(i.context_expr,ast.Call) and ast.unparse(i.context_expr.func)=='observe_browser_transport']
            if entries:
                assert len(entries)==1
                node.items.remove(entries[0]);count+=1
    assert count==1
    items=[n for n in fn.body if isinstance(n,ast.If) and ast.unparse(n.test)=='browser_trace']
    assert len(items)==1 and ast.unparse(items[0].body[0])=="results[0]['lab_browser_trace'] = browser_trace.events"
    fn.body.remove(items[0])

def strip_browser_trace_worker(tree):
    added=next((n for n in tree.body if getattr(n,'name','')=='log_browser_failure'),None)
    if added is None:return
    tree.body.remove(added)
    fn=next(n for n in tree.body if getattr(n,'name','')=='log_failure_trace')
    items=[n for n in fn.body if ast.unparse(n)=='log_browser_failure(r, error)']
    assert len(items)==1;fn.body.remove(items[0])
