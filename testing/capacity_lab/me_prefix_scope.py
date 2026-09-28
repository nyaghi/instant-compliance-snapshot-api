"""Exact normalization of same-lookup complete-prefix acquisition only."""
import ast

def strip_me_prefix_coverage(tree):
    names={'lab_me_prefix_coverage_enabled','me_covering_literal_prefix',
           'me_complete_prefix_list','me_search_with_prefix_coverage'}
    if not any(getattr(n,'name','') in names for n in tree.body):return
    assert sum(getattr(n,'name','') in names for n in tree.body)==4
    tree.body=[n for n in tree.body if getattr(n,'name','') not in names]
    hits=[]
    class Strip(ast.NodeTransformer):
        def visit_If(self,node):
            if ast.unparse(node.test)=='lab_me_prefix_coverage_enabled()':
                assert [ast.unparse(n) for n in node.body]==['self.completed_search_html = response.text']
                assert not node.orelse;hits.append('body');return None
            if ast.unparse(node.test)=='session.covered_source_query':
                assert [ast.unparse(n) for n in node.body]==["attempt_evidence['covered_by_completed_prefix'] = session.covered_source_query",
                    'completed.update((candidate for candidate in queries if candidate.casefold().startswith(session.covered_source_query)))']
                assert not node.orelse;hits.append('evidence');return None
            return self.generic_visit(node)
        def visit_Call(self,node):
            if ast.unparse(node.func)=='me_search_with_prefix_coverage':
                assert [ast.unparse(a) for a in node.args]==['session','query','queries']
                hits.append('call');return ast.parse('session.search(query)',mode='eval').body
            return self.generic_visit(node)
    Strip().visit(tree);assert sorted(hits)==['body','call','evidence']
