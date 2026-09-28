"""Exact removal of the optional source pacing estimate, nothing else."""
import ast

def strip_paced_timing(tree):
    helper=next((n for n in tree.body if getattr(n,'name','')=='apply_paced_tail_floor'),None)
    if helper is None:return
    tree.body.remove(helper)
    claim=next(n for c in tree.body if isinstance(c,ast.ClassDef) and c.name=='Queue'
               for n in c.body if getattr(n,'name','')=='claim')
    found=[]
    for node in ast.walk(claim):
        for _,children in ast.iter_fields(node):
            if not isinstance(children,list):continue
            for child in list(children):
                if isinstance(child,ast.Expr) and ast.unparse(child)=="apply_paced_tail_floor(tail_scores, workflows, pending, estimates, cfg['source_version'])":
                    children.remove(child);found.append(child)
    assert len(found)==1
