"""Validate only the reviewed sample statistic and its cache discriminator."""
import ast, subprocess
from pathlib import Path

def strip_observed_tail(tree):
    fn=next((n for n in tree.body if getattr(n,'name','')=='cohort_timing_estimates'),None)
    if fn is None:return
    added=next((n for n in fn.body if isinstance(n,ast.Assign)
                and ast.unparse(n.targets[0])=='observed_tail'),None)
    if added is None:return
    assert ast.unparse(added.value)=="workload_timing and os.environ.get('CE_LAB_SALES_OBSERVED_TAIL') == '1'"
    fn.body.remove(added)
    guard=next(n for n in fn.body if isinstance(n,ast.If)
               and isinstance(n.test,ast.BoolOp) and ast.unparse(n.test).startswith('cache and'))
    assert ast.unparse(guard.test.values[-1])=="getattr(cache[3], 'observed_tail', False) == observed_tail"
    guard.test.values.pop()
    rows=next(n for n in fn.body if isinstance(n,ast.FunctionDef) and n.name=='rows')
    stat=next(n for n in rows.body if isinstance(n,ast.Assign) and ast.unparse(n.targets[0])=='tail_stat')
    assert ast.unparse(stat.value)=="'max(recent.seconds)' if observed_tail else 'percentile_cont(0.95) WITHIN GROUP (ORDER BY recent.seconds)'"
    rows.body.remove(stat)
    projection=next(n for n in rows.body if isinstance(n,ast.Assign) and ast.unparse(n.targets[0])=='projection')
    expected=ast.parse('''projection = (f"{tail_stat} AS tail_seconds" if include_censored else
        "percentile_cont(0.5) WITHIN GROUP (ORDER BY recent.seconds) AS seconds, "
        f"{tail_stat} AS tail_seconds")''').body[0]
    assert ast.dump(projection)==ast.dump(expected)
    root=Path(__file__).resolve().parents[2]
    old=ast.parse(subprocess.check_output(['git','show','3383085:deployment/durable_queue.py'],cwd=root).decode())
    old_fn=next(n for n in old.body if getattr(n,'name','')=='cohort_timing_estimates')
    old_rows=next(n for n in old_fn.body if isinstance(n,ast.FunctionDef) and n.name=='rows')
    old_projection=next(n for n in old_rows.body if isinstance(n,ast.Assign) and ast.unparse(n.targets[0])=='projection')
    rows.body[rows.body.index(projection)]=old_projection
    marker=next(n for n in fn.body if isinstance(n,ast.Assign) and ast.unparse(n.targets[0])=='values.observed_tail')
    assert ast.unparse(marker.value)=='observed_tail';fn.body.remove(marker)
    assert ast.dump(fn)==ast.dump(old_fn), 'Unexpected change outside reviewed timing statistic'
