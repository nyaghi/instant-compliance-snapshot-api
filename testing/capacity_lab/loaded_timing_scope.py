"""Exact normalization for elapsed-time metadata and the loaded-source floor."""
import ast,subprocess
SCHEMA_ADDITION="""
-- Timing metadata only: actual held source reservations when a job is claimed.
-- Zero means unavailable, including historical jobs predating this observer.
ALTER TABLE cc_lab_jobs ADD COLUMN IF NOT EXISTS source_pressure integer NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS cc_lab_jobs_loaded_duration ON cc_lab_jobs(state,finished DESC)
 WHERE phase='done' AND source_pressure>=2 AND attempt=1 AND claimed IS NOT NULL
 AND (error IS NULL OR error IN ('WORKFLOW_DEADLINE','TASK_TIME_LIMIT'));
"""
def strip_loaded_schema(source):
    if SCHEMA_ADDITION not in source:return source
    assert source.count(SCHEMA_ADDITION)==1
    return source.replace(SCHEMA_ADDITION,'')
def strip_loaded_timing(tree):
    helper=next((n for n in tree.body if getattr(n,'name','')=='apply_loaded_timing_floor'),None)
    if helper is None:return
    tree.body.remove(helper)
    fn=next(n for n in tree.body if getattr(n,'name','')=='cohort_timing_estimates')
    init=next(n for n in fn.body if isinstance(n,ast.Assign) and ast.unparse(n.targets[0])=='loaded_timing')
    assert ast.unparse(init.value)=="workload_timing and os.environ.get('CE_LAB_SALES_LOADED_TIMING') == '1'"
    fn.body.remove(init)
    guard=next(n for n in fn.body if isinstance(n,ast.If) and isinstance(n.test,ast.BoolOp) and ast.unparse(n.test).startswith('cache and'))
    assert ast.unparse(guard.test.values[-1])=="getattr(cache[3], 'loaded_timing', False) == loaded_timing"
    guard.test.values.pop()
    call=next(n for n in fn.body if isinstance(n,ast.If) and ast.unparse(n.test)=='loaded_timing')
    assert ast.unparse(call.body[0])=='apply_loaded_timing_floor(c, before, states, values)' and len(call.body)==1 and not call.orelse
    fn.body.remove(call)
    marker=next(n for n in fn.body if isinstance(n,ast.Assign) and ast.unparse(n.targets[0])=='values.loaded_timing')
    assert ast.unparse(marker.value)=='loaded_timing';fn.body.remove(marker)
    claim=next(n for c in tree.body if isinstance(c,ast.ClassDef) and c.name=='Queue' for n in c.body if getattr(n,'name','')=='claim')
    calls=[n for n in ast.walk(claim) if isinstance(n,ast.Call) and n.args and isinstance(n.args[0],ast.Constant) and isinstance(n.args[0].value,str) and 'source_pressure=%s' in n.args[0].value]
    assert len(calls)==1
    sql,args=calls[0].args
    assert sql.value=="UPDATE cc_lab_jobs SET phase='running',owner=%s,token=%s,attempt=attempt+1,claimed=%s,lease_until=%s,run_until=%s,source_pressure=%s WHERE id=%s"
    assert ast.unparse(args.elts[-2])=="busy[j['state']] + 1 if j['state'] in j['resources'] else 0"
    args.elts.pop(-2);sql.value=sql.value.replace(',source_pressure=%s','')
def assert_loaded_scope(root,reference,path):
    old=subprocess.check_output(['git','show',reference+':'+path],cwd=root).decode()
    new=(root/path).read_text(encoding='utf-8')
    if path.endswith('.sql'):
        assert strip_loaded_schema(new)==old,path
    else:
        a,b=ast.parse(old),ast.parse(new);strip_loaded_timing(b)
        assert ast.dump(a)==ast.dump(b),path
