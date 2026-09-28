"""Normalize only the lab Sales query ordering and proven-zero coverage."""
import ast

def strip_mi_query_order(tree):
    from testing.capacity_lab.mi_patient_scope import strip_mi_patient_transport
    strip_mi_patient_transport(tree)
    helper=next((n for n in tree.body if getattr(n,'name','')=='lab_mi_query_dominance_enabled'),None)
    if helper is None:return
    tree.body.remove(helper)
    plan=next(n for n in tree.body if getattr(n,'name','')=='mi_name_fallback_queries')
    assert ast.unparse(plan.body[-3])=='planned = variants[:4]'
    assert ast.unparse(plan.body[-2].test)=='lab_mi_query_dominance_enabled()'
    assert ast.unparse(plan.body[-1])=='return planned'
    plan.body[-3:]=ast.parse('return variants[:4]').body
    coverage=next(n for n in tree.body if getattr(n,'name','')=='mi_completed_query_covers')
    expected='bool(original) and (original.issubset(set(query.casefold().split())) or original.issubset(joined))'
    assert ast.dump(coverage.body[-3].value)==ast.dump(ast.parse(expected,mode='eval').body)
    assert ast.unparse(coverage.body[-1])=='return covered'
    coverage.body[-3:]=ast.parse('return '+expected).body
