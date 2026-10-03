"""Exact normalization of the lab Sales redundant form waits only."""
import ast

def strip_wa_form_waits(tree):
    fn=next((n for n in tree.body if getattr(n,'name','')=='fill_fein_and_search'),None)
    if fn is None or not fn.args.kwonlyargs:return
    assert [a.arg for a in fn.args.kwonlyargs]==['readiness_waits_only']
    fn.args.kwonlyargs=[];fn.args.kw_defaults=[]
    class Restore(ast.NodeTransformer):
        count=0
        def visit_If(self,node):
            if ast.unparse(node.test)=='not readiness_waits_only':
                assert len(node.body)==1 and ast.unparse(node.body[0])=='time.sleep(1)' and not node.orelse
                self.count+=1;return node.body
            return self.generic_visit(node)
    restore=Restore();restore.visit(fn);assert restore.count==2
    # The later Sales submission correction changes only actionability of the
    # same Search click; normalize that exact branch for this historical test.
    for node in ast.walk(fn):
        if isinstance(node,ast.Try) and node.body and isinstance(node.body[0],ast.If):
            branch=node.body[0]
            if ast.unparse(branch.test)=='readiness_waits_only':
                assert ast.unparse(branch.body[0])=='candidate.click(timeout=5000)'
                assert len(branch.orelse)==1 and ast.unparse(branch.orelse[0])=='candidate.click(timeout=5000, force=True)'
                node.body[:1]=branch.orelse
    wait=next(n for n in tree.body if getattr(n,'name','')=='wait_for_result_link_or_no_value')
    loop=next(n for n in wait.body if isinstance(n,ast.While))
    matches=[(i,n) for i,n in enumerate(loop.body) if isinstance(n,ast.If) and ast.unparse(n.test)=='not require_complete_before_link']
    assert len(matches)==1
    i,node=matches[0];assert len(node.body)==1 and ast.unparse(node.body[0])=='scroll_to_results(page)'
    loop.body[i:i+1]=node.body
    search=next(n for n in tree.body if getattr(n,'name','')=='search_wa')
    calls=[n for n in ast.walk(search) if isinstance(n,ast.Call) and ast.unparse(n.func)=='fill_fein_and_search']
    assert len(calls)==1 and len(calls[0].keywords)==1
    assert calls[0].keywords[0].arg=='readiness_waits_only'
    calls[0].keywords=[]
