"""Normalize the separately tested CO-only Sales allowance for historic scopes."""
import ast

def strip_identity_grace_queue(tree):
    imports=[n for n in tree.body if isinstance(n,ast.ImportFrom) and n.module=='deployment.lab_capacity'
             and [a.name for a in n.names]==['sales_identity_seconds']]
    if not imports:return
    assert len(imports)==1;tree.body.remove(imports[0]);count=0
    for n in ast.walk(tree):
        if isinstance(n,ast.IfExp) and ast.unparse(n.test)=="j['state'] == '@sales_identity'":
            assert ast.unparse(n.body)=="sales_identity_seconds(w['source_version']) + 2"
            n.body=ast.Constant(8);count+=1
    assert count==1

def strip_identity_grace_engine(tree):
    fn=next(n for n in tree.body if getattr(n,'name','')=='execute')
    guard=next(n for n in fn.body if isinstance(n,ast.If) and ast.unparse(n.test)=="job['state'] == '@sales_identity'")
    if not isinstance(guard.body[0],ast.ImportFrom):return
    assert ast.unparse(guard.body[0])=='from deployment.lab_capacity import sales_identity_seconds'
    assert ast.unparse(guard.body[1])=="return master.sales_identity_evidence(p['organization_name'], p['ein'], budget_seconds=sales_identity_seconds(job['version']))"
    guard.body=ast.parse("return master.sales_identity_evidence(p['organization_name'], p['ein'])").body

def strip_identity_grace(tree):
    from testing.capacity_lab.pa_rows_scope import strip_pa_rows
    strip_pa_rows(tree)
    co=next((n for n in tree.body if getattr(n,'name','')=='identity_co_names'),None)
    if co is None or not co.args.kwonlyargs:return
    assert [a.arg for a in co.args.kwonlyargs]==['request_timeout']
    co.args.kwonlyargs=[];co.args.kw_defaults=[]
    call=next(n for n in ast.walk(co) if isinstance(n,ast.Call) and ast.unparse(n.func)=='identity_fetch')
    assert ast.unparse(call.keywords[0].value)=='request_timeout';call.keywords=[]
    fn=next(n for n in tree.body if getattr(n,'name','')=='sales_identity_evidence')
    assert [a.arg for a in fn.args.kwonlyargs]==['budget_seconds']
    fn.args.kwonlyargs=[];fn.args.kw_defaults=[]
    fn.body[0].value.value=fn.body[0].value.value.replace('bounded allowance','six-second allowance')
    remove=[]
    for node in fn.body:
        if isinstance(node,ast.If) and ast.unparse(node.test)=='budget_seconds not in (6.0, 10.0)':remove.append(node)
        if isinstance(node,ast.FunctionDef) and node.name=='timed':remove.append(node)
        if isinstance(node,ast.Assign):
            key=ast.unparse(node.targets[0])
            if key in ('ordinary_deadline','timings'):remove.append(node)
            if key=='deadline':
                assert ast.unparse(node.value)=='started + budget_seconds';node.value=ast.parse('started + 6.0',mode='eval').body
            if key=='collectors':
                assert ast.unparse(node.value.values[0]).startswith('lambda: identity_co_names(requested, deadline, request_timeout=budget_seconds) if')
                node.value.values[0]=ast.parse('lambda: identity_co_names(requested, deadline)',mode='eval').body
            if key=='futures':
                assert ast.unparse(node.value)=='{source: executor.submit(timed, source, fn) for source, fn in collectors.items()}'
                node.value=ast.parse('{source: executor.submit(fn) for source, fn in collectors.items()}',mode='eval').body
    assert len(remove)==4
    for node in remove:fn.body.remove(node)
    for node in ast.walk(fn):
        if isinstance(node,ast.Name) and node.id=='ordinary_deadline':node.id='deadline'
    result=fn.body[-1].value
    i=next(i for i,k in enumerate(result.keys) if isinstance(k,ast.Constant) and k.value=='source_seconds')
    result.keys.pop(i);result.values.pop(i)
