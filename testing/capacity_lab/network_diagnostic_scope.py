"""Remove only the reviewed passive TCP/TLS and browser-network observations."""
import ast

def strip_network_diagnostics(tree):
    added={'observe_fl_connection','attach_ny_network_diagnostics'}
    if not any(getattr(n,'name','') in added for n in tree.body):return
    assert sum(getattr(n,'name','') in added for n in tree.body)==2
    tree.body=[n for n in tree.body if getattr(n,'name','') not in added]
    fn=next(n for n in tree.body if getattr(n,'name','')=='observe_fl_headers')
    found=0
    for node in ast.walk(fn):
        if isinstance(node,ast.Try):
            for index,child in enumerate(node.body):
                if isinstance(child,ast.With) and ast.unparse(child.items[0].context_expr)=='observe_fl_connection(trace)':
                    assert len(child.items)==1 and len(child.body)==1
                    assert ast.unparse(child.body[0])=='response = original(opener, request, *args, **kwargs)'
                    node.body[index:index+1]=child.body;found+=1
    assert found==1
    fn=next(n for n in tree.body if getattr(n,'name','')=='observe_browser_transport')
    found=0
    for node in ast.walk(fn):
        if hasattr(node,'body') and isinstance(node.body,list):
            for child in list(node.body):
                if ast.unparse(child) in ('diagnostics = []','diagnostics.append(attach_ny_network_diagnostics(context, page, trace))'):
                    node.body.remove(child);found+=1
        if isinstance(node,ast.Try):
            for child in list(node.finalbody):
                if isinstance(child,ast.For) and ast.unparse(child.target)=='session' and ast.unparse(child.iter)=='diagnostics':
                    assert ast.unparse(child)=="for session in diagnostics:\n    if session is not None:\n        try:\n            session.detach()\n        except Exception:\n            pass"
                    node.finalbody.remove(child);found+=1
    assert found==3
