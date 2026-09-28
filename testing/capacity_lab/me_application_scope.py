"""Normalize only the reviewed explicit-error handling; preserve older scope proofs."""
import ast

def strip_me_application_recovery(tree):
    names={'MainePublicApplicationError','lab_me_application_recovery_enabled'}
    if not any(getattr(n,'name','') in names for n in tree.body):return
    assert sum(getattr(n,'name','') in names for n in tree.body)==2
    tree.body=[n for n in tree.body if getattr(n,'name','') not in names]
    parser=next(n for n in tree.body if getattr(n,'name','')=='me_parse_search_rows')
    assert ast.unparse(parser.body[0].test)=='lab_me_application_recovery_enabled()'
    parser.body.pop(0)
    fn=next(n for n in tree.body if getattr(n,'name','')=='me_fast_direct_confirmation_result')
    hits=[]
    class Strip(ast.NodeTransformer):
        def visit_Assign(self,n):
            if ast.unparse(n)=='application_error = False':hits.append('init');return None
            return self.generic_visit(n)
        def visit_ExceptHandler(self,n):
            if ast.unparse(n.type)=='MainePublicApplicationError':
                assert [ast.unparse(x) for x in n.body]==['application_error = True','last_error = str(exc)',"attempt_evidence.update(error=last_error, stage='source application error')"]
                hits.append('catch');return None
            return self.generic_visit(n)
        def visit_If(self,n):
            if ast.unparse(n.test)=='application_error':
                assert ast.unparse(n.body[-2])=="result.reason_code = 'ME_SOURCE_APPLICATION_ERROR'"
                assert ast.unparse(n.body[-1])=='return result'
                hits.append('result');return None
            return self.generic_visit(n)
        def visit_BoolOp(self,n):
            if isinstance(n.op,ast.Or) and ast.unparse(n.values[-1])=='application_error':
                n.values.pop();hits.append('stop')
            return self.generic_visit(n)
    Strip().visit(fn);assert sorted(hits)==['catch','init','result','stop','stop']
    fn=next(n for n in tree.body if getattr(n,'name','')=='run_single_state_lookup_reliably')
    hits=[]
    class Semantic(ast.NodeTransformer):
        def visit_If(self,n):
            if ast.unparse(n.test)=="result.get('reason_code') == 'ME_SOURCE_APPLICATION_ERROR'":
                assert len(n.body)==1 and ast.unparse(n.body[0])=='return result' and not n.orelse
                hits.append(1);return None
            return self.generic_visit(n)
    Semantic().visit(fn);assert len(hits)==1

def strip_queue_recovery(new):
    helper=next((n for n in new.body if getattr(n,'name','')=='source_application_retry'),None)
    if helper is None:return
    new.body.remove(helper)
    hits=[]
    class Strip(ast.NodeTransformer):
        def visit_Constant(self,n):
            if isinstance(n.value,str) and 'SELECT j.*,w.ein,w.source_version,w.stop_reason,w.mode,w.deadline FROM' in n.value:
                n.value=n.value.replace('w.stop_reason,w.mode,w.deadline FROM','w.stop_reason FROM');hits.append('select')
            return n
        def visit_Assign(self,n):
            s=ast.unparse(n)
            if s in ["recovery = (j.get('result') or {}).get('lab_source_retry')","prior_recovery = (j.get('result') or {}).get('lab_source_retry')"] or s.startswith('recovery = source_application_retry('):
                hits.append('assign');return None
            return self.generic_visit(n)
        def visit_If(self,n):
            if ast.unparse(n.test).startswith(('recovery and ', 'prior_recovery and ')) or ast.unparse(n.test)=='recovery':
                hits.append('if');return None
            return self.generic_visit(n)
        def visit_Call(self,n):
            if ast.unparse(n)== 'updates.append((j, result, error, recovery))':
                hits.append('append');return ast.parse('updates.append((j,result,error))',mode='eval').body
            return self.generic_visit(n)
        def visit_For(self,n):
            if ast.unparse(n.target)=='(j, result, error, recovery)':
                n.target=ast.parse('for j,result,error in updates: pass').body[0].target;hits.append('loop')
            return self.generic_visit(n)
    Strip().visit(new)
    assert sorted(hits)==sorted(['select','assign','assign','assign','if','if','if','if','append','loop']),hits

def assert_queue_recovery_only(root,reference):
    import subprocess
    file='deployment/durable_queue.py'
    old=ast.parse(subprocess.check_output(['git','show',reference+':'+file],cwd=root).decode())
    new=ast.parse((root/file).read_text());strip_queue_recovery(new)
    assert ast.dump(old)==ast.dump(new),file
