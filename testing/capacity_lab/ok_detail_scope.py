"""Exact normalization of the selected-document readiness change only."""
import ast


def strip_ok_completed_detail(tree):
    from testing.capacity_lab.nj_patient_scope import strip_nj_patient_detail
    strip_nj_patient_detail(tree)
    names={'lab_ok_completed_detail_enabled','ok_open_selected_detail'}
    if not any(getattr(n,'name','') in names for n in tree.body): return
    assert sum(getattr(n,'name','') in names for n in tree.body)==2
    tree.body=[n for n in tree.body if getattr(n,'name','') not in names]
    fn=next(n for n in tree.body if getattr(n,'name','')=='search_ok_precise')
    count=0
    for node in ast.walk(fn):
        if isinstance(node,ast.Try):
            calls=[n for n in node.body if isinstance(n,ast.Expr) and ast.unparse(n)==
                   'ok_open_selected_detail(page, selected_filing_link, org, module, filing_number)']
            for call in calls:
                i=node.body.index(call)
                node.body[i:i+1]=ast.parse('''selected_filing_link.click(timeout=ok_action_timeout(org, 5000))
module.safe_wait_for_network_idle(page, timeout=20000)
page.wait_for_timeout(2500)''').body
                count+=1
    assert count==1


def assert_ok_detail_only(root, reference):
    import subprocess
    file='registry_snapshot_server.py'
    old=ast.parse(subprocess.check_output(['git','show',reference+':'+file],cwd=root).decode())
    new=ast.parse((root/file).read_text());strip_ok_completed_detail(new)
    assert ast.dump(old)==ast.dump(new),file
