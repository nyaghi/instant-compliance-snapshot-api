"""Normalize only the selected New Jersey detail-request sublimit."""
import ast

def strip_nj_patient_detail(tree):
    from testing.capacity_lab.me_prefix_scope import strip_me_prefix_coverage
    strip_me_prefix_coverage(tree)
    helper=next((n for n in tree.body if getattr(n,'name','')=='nj_public_request_timeout'),None)
    if helper is None:return
    tree.body.remove(helper)
    class Strip(ast.NodeTransformer):
        hits=0
        def visit_Call(self,node):
            if ast.unparse(node.func)=='nj_public_request_timeout':
                assert [ast.unparse(a) for a in node.args]==['request_path','remaining']
                self.hits+=1
                return ast.parse('min(4.0, remaining)',mode='eval').body
            return self.generic_visit(node)
    strip=Strip();strip.visit(tree);assert strip.hits==1
