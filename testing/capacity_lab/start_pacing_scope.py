"""Remove only the lab's source start-rate guard for whole-file scope checks."""
import ast

START_INDEX=("-- A completed fast response still participates in a configured source start rate.\n"
             "CREATE INDEX IF NOT EXISTS cc_lab_source_last_start ON cc_lab_jobs(state,claimed DESC)\n"
             " WHERE claimed IS NOT NULL;\n")

def strip_start_index(source):
    assert source.count(START_INDEX)==1
    return source.replace(START_INDEX,'')

def strip_start_pacing(tree):
    helpers={'sales_source_start_intervals','sales_source_start_after'}
    present=[n for n in tree.body if getattr(n,'name','') in helpers]
    if not present:return
    assert len(present)==2
    tree.body[:]=[n for n in tree.body if n not in present and not (
        isinstance(n,ast.Import) and len(n.names)==1 and n.names[0].name=='math')]
    claim=next(n for c in tree.body if isinstance(c,ast.ClassDef) and c.name=='Queue'
               for n in c.body if getattr(n,'name','')=='claim')
    removed=[]
    for parent in ast.walk(claim):
        for _,children in ast.iter_fields(parent):
            if not isinstance(children,list):continue
            for child in list(children):
                text=ast.unparse(child) if isinstance(child,ast.stmt) else ''
                if text in ["start_after = sales_source_start_after(c, workflows, cfg['source_version'], now)",
                            "if start_after.get(j['state'], now) > now:\n    continue"]:
                    children.remove(child);removed.append(text)
    assert len(removed)==2
