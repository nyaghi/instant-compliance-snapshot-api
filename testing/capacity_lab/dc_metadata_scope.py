"""Exact AST exclusions for separately tested DC result diagnostics."""
import ast

def remove_dc_result_metadata(tree):
    from testing.capacity_lab.fl_alias_scope import remove_fl_alias_guard
    remove_fl_alias_guard(tree)
    helper=next((n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='dc_corroborated_result_match'),None)
    if helper is None:return
    tree.body.remove(helper)
    expected=ast.parse('''if state == "DC" and dc_corroborated_result_match(result):
    result.reason_code = selected["match"]["reason"]
    result.identity_anchor = "cross_state_name_address"
    result.identity_review_evidence = {"kind": "cross_state_name_address", "name": selected["match"]}
''').body[0]
    trace=ast.parse('''if state == "DC":
    decision = dc_corroborated_result_match(result) or decision
''').body[0]
    for function,statement in [('licensed_charity_result',expected),('debug_trace_for_result',trace)]:
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==function)
        removed=0
        for parent in ast.walk(fn):
            for _,value in ast.iter_fields(parent):
                if isinstance(value,list):
                    matches=[n for n in value if isinstance(n,ast.AST) and ast.dump(n)==ast.dump(statement)]
                    for node in matches:value.remove(node);removed+=1
        assert removed==1, 'DC diagnostic hook scope changed'
