"""Allow only tested elapsed-time snapshot/one-query-floor changes."""
import ast

def strip_cohort_timing(tree):
    from testing.capacity_lab.global_priority_scope import strip_global_priority
    strip_global_priority(tree)
    helper=next((n for n in tree.body if getattr(n,'name','')=='cohort_timing_estimates'),None)
    if helper is None:return
    tree.body.remove(helper)
    scores=next(n for n in tree.body if getattr(n,'name','')=='sales_tail_scores')
    floor=[n for n in scores.body if isinstance(n,ast.If) and ast.unparse(n.test)=="getattr(estimates, 'as_of', None) is not None"]
    assert len(floor)==1;scores.body.remove(floor[0])
    q=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Queue')
    fn=next(n for n in q.body if getattr(n,'name','')=='claim')
    calls=[n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='cohort_timing_estimates']
    assert len(calls)==1
    call=calls[0];assert ast.unparse(call.args[0])=='self' and ast.unparse(call.args[-1])=='workflows'
    call.func=ast.parse('self.cached_duration_estimates').body[0].value
    call.args=call.args[1:-1]
    telemetry=[n for n in ast.walk(fn) if isinstance(n,ast.Call) and any(k.arg=='source_timing_as_of' for k in n.keywords)]
    assert len(telemetry)==1
    kw=next(k for k in telemetry[0].keywords if k.arg=='source_timing_as_of')
    assert ast.unparse(kw.value)=="getattr(estimates, 'as_of', None)"
    telemetry[0].keywords.remove(kw)
