"""Normalize only two MI request sublimits; all outer deadlines stay exact."""
import ast

def strip_mi_patient_transport(tree):
    helper=next((n for n in tree.body if getattr(n,'name','')=='lab_mi_patient_transport_enabled'),None)
    if helper is None:return
    tree.body.remove(helper)
    class Strip(ast.NodeTransformer):
        hits=0
        def visit_IfExp(self,node):
            if ast.unparse(node.test)=='lab_mi_patient_transport_enabled()':
                assert (ast.unparse(node.body),ast.unparse(node.orelse)) in [('24.0','18.0'),('45.0','MI_SEARCH_RESPONSE_TIMEOUT_MS / 1000')]
                self.hits+=1;return node.orelse
            return self.generic_visit(node)
    strip=Strip();strip.visit(tree);assert strip.hits==2
