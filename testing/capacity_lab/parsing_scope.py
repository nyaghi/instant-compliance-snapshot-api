"""Scope normalization for independently tested public-table reuse."""
import ast
from pathlib import Path
import subprocess

CHANGED = {'nj_loaded_detail_body', 'search_fl_with_transport', 'search_wv_public_details', 'search_wv_precise', 'registry_table_text_snapshot', 'identity_oh_names', 'search_oh', 'oh_ein_search_source', 'oh_result_from_detail_text', 'search_oh_direct_details', 'hi_direct_details_from_source', 'search_hi_direct_details', 'identity_irs_names', 'sales_identity_evidence', 'sales_names_from_evidence', 'sales_result_with_identity', 'search_sc_resilient', 'load_ks_weekly_checker', 'distinctive_match_tokens', '_cached_distinctive_match_tokens', 'nh_records_from_snapshot_bytes', 'nh_download_live_pdf_records',
           'nh_live_pdf_records', 'run_state_lookup', 'search_la_downloaded_export'}

def restore_parsing_optimization(tree):
    strip_or_snapshot_index_optimization(tree)
    strip_nj_public_detail_optimization(tree)
    if not any(isinstance(n, ast.FunctionDef) and n.name == 'nh_records_from_snapshot_bytes' for n in tree.body):
        return
    old = ast.parse(subprocess.check_output(['git', 'show', '433927e:registry_snapshot_server.py'],
                   cwd=Path(__file__).resolve().parents[2]).decode('utf-8'))
    originals = {n.name: n for n in old.body if isinstance(n, ast.FunctionDef)}
    tree.body = [n for n in tree.body if not (isinstance(n, ast.ClassDef) and n.name == 'WestVirginiaPublicLookup')]
    tree.body = [originals.get(n.name, n) if isinstance(n, ast.FunctionDef) and n.name in CHANGED else n
                 for n in tree.body if not (isinstance(n, ast.FunctionDef) and n.name in {'fl_completed_search_form_available', 'search_wv_public_details', 'registry_table_text_snapshot', 'oh_ein_search_source', 'oh_result_from_detail_text', 'search_oh_direct_details', 'hi_direct_details_from_source', 'search_hi_direct_details', 'nh_records_from_snapshot_bytes', '_cached_distinctive_match_tokens', 'sales_identity_evidence', 'sales_names_from_evidence', 'sales_result_with_identity'})]


def strip_nj_public_detail_optimization(tree):
    """Remove only the tested response/cache statements, preserving scoring/rules."""
    strip_nj_query_optimization(tree)
    if not any(getattr(n, 'name', '') == 'nj_selected_public_detail' for n in tree.body):
        return
    tree.body = [n for n in tree.body if getattr(n, 'name', '') != 'nj_selected_public_detail']
    for fn in tree.body:
        if getattr(fn, 'name', '') == 'nj_detail_body':
            assert [ast.unparse(n.targets[0]) for n in fn.body[:2]] == ['cache_key', 'cached']
            assert isinstance(fn.body[2], ast.If) and 'cached[0] == cache_key' in ast.unparse(fn.body[2].test)
            fn.body = fn.body[3:]
            block = next(n for n in fn.body if isinstance(n, ast.If) and ast.unparse(n.test) == 'candidates')
            assert ast.unparse(block.body[1].targets[0]) == 'public_detail'
            assert ast.unparse(block.body[2].test) == 'public_detail'
            del block.body[1:3]
        elif getattr(fn, 'name', '') == 'search_nj_direct':
            assert ast.unparse(fn.body[2]) == 'page._cc_nj_selected_detail = None'
            del fn.body[2]


def strip_nj_query_optimization(tree):
    """Restore only the new acquisition prefix; classification remains compared."""
    if not any(getattr(n, 'name', '') == 'nj_search_body' for n in tree.body):
        return
    old = ast.parse(subprocess.check_output(['git', 'show', 'a3376d2:registry_snapshot_server.py'],
        cwd=Path(__file__).resolve().parents[2]).decode('utf-8'))
    original = next(n for n in old.body if getattr(n, 'name', '') == 'search_nj_direct')
    before = next(n for n in original.body if isinstance(n, ast.Try))
    after = next(n for n in next(n for n in tree.body if getattr(n, 'name', '') == 'search_nj_direct').body if isinstance(n, ast.Try))
    def boundary(body):
        return next(i for i, n in enumerate(body) if isinstance(n, ast.If)
                    and ast.unparse(n.test).startswith("re.search('no records found|no records|no matching|0 results'"))
    split = boundary(after.body)
    assert split == 3 and ast.dump(after.body[0]) == ast.dump(before.body[0])
    assert ast.unparse(after.body[1]) == 'body = nj_search_body(page, ein_digits or org.organization_name)'
    assert ast.unparse(after.body[2].test) == 'body is None'
    after.body = before.body[:boundary(before.body)] + after.body[split:]
    detail = next(n for n in tree.body if getattr(n, 'name', '') == 'nj_detail_body')
    assert ast.unparse(detail.body[0].test) == "getattr(page, '_cc_nj_query_incomplete', False) is True"
    assert len(detail.body[0].body) == 1 and ast.unparse(detail.body[0].body[0]) == "return ''"
    del detail.body[0]
    fallback = next(n for n in tree.body if getattr(n, 'name', '') == 'search_nj_with_name_fallback')
    guards = [n for n in ast.walk(fallback) if isinstance(n, ast.If)
              and 'NJ_INCOMPLETE_QUERY_RESPONSE' in ast.unparse(n.test)]
    assert len(guards) == 1 and isinstance(guards[0].test, ast.BoolOp) and isinstance(guards[0].test.op, ast.Or)
    assert len(guards[0].test.values) == 2
    assert ast.unparse(guards[0].test.values[1]) == "getattr(fallback, 'reason_code', '') == 'NJ_INCOMPLETE_QUERY_RESPONSE'"
    guards[0].test = guards[0].test.values[0]
    tree.body = [n for n in tree.body if getattr(n, 'name', '') not in {'nj_search_body', 'nj_completed_query_rows'}]


def strip_or_snapshot_index_optimization(tree):
    strip_sales_profile_reuse(tree)
    if not any(getattr(n, 'name', '') == 'or_snapshot_index_from_bytes' for n in tree.body):
        return
    old = ast.parse(subprocess.check_output(['git', 'show', 'bd13982:registry_snapshot_server.py'],
        cwd=Path(__file__).resolve().parents[2]).decode('utf-8'))
    allowed = {'fiscal_period_for_ein', 'organization_name_for_ein', 'or_snapshot_row_for_ein'}
    originals = {n.name:n for n in old.body if isinstance(n, ast.FunctionDef) and n.name in allowed}
    tree.body = [originals.get(getattr(n, 'name', ''), n) for n in tree.body
                 if getattr(n, 'name', '') not in {'or_snapshot_index_from_bytes', 'validated_or_snapshot_index'}]


def strip_sales_profile_reuse(tree):
    strip_browser_startup_reuse(tree)
    if not any(getattr(n, 'name', '') == 'run_sales_lookups_with_source_evidence' for n in tree.body):
        return
    old = ast.parse(subprocess.check_output(['git', 'show', 'e3b09d5a3cc031374925a17fe0211ff4398273f2:registry_snapshot_server.py'],
        cwd=Path(__file__).resolve().parents[2]).decode('utf-8'))
    allowed = {'public_profile_for_ein', 'sales_identity_evidence'}
    originals = {n.name:n for n in old.body if isinstance(n, ast.FunctionDef) and n.name in allowed}
    tree.body = [originals.get(getattr(n, 'name', ''), n) for n in tree.body
                 if getattr(n, 'name', '') != 'run_sales_lookups_with_source_evidence'
                 and not (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id=='SALES_PROFILE_CONTEXT' for t in n.targets))]


def strip_browser_startup_reuse(tree):
    strip_nj_query_optimization(tree)
    tree.body = [n for n in tree.body if getattr(n, 'name', '') != 'launch_lookup_browser']
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id=='launch_lookup_browser':
            assert node.args and isinstance(node.args[0], ast.Name)
            node.func=ast.Attribute(value=ast.Attribute(value=node.args.pop(0),attr='chromium',ctx=ast.Load()),attr='launch',ctx=ast.Load())


def strip_browser_pool_metric(tree):
    for fn in tree.body:
        if getattr(fn, 'name', '')=='run_job':
            fn.body=[n for n in fn.body if not (isinstance(n, ast.Assign) and any("['pooled_browser_used']" in ast.unparse(t) for t in n.targets))]


def strip_browser_pool_worker(tree):
    """Remove only the separately tested browser ownership integration."""
    strip_launch_pacing_threshold(tree)
    class Restore(ast.NodeTransformer):
        def visit_Assign(self, node):
            targets={ast.unparse(t) for t in node.targets}
            if targets & {'self.browser_pool','self.browser_pool_temp','owner'}:
                return None
            return self.generic_visit(node)
        def visit_If(self, node):
            condition=ast.unparse(node.test)
            if 'self.browser_pool' in condition or "settings.get('CE_LAB_BROWSER_POOL_SIZE'" in condition:
                return None
            return self.generic_visit(node)
        def visit_Call(self, node):
            if ast.unparse(node.func)=='dict':
                node.keywords=[k for k in node.keywords if k.arg!='owner']
            return self.generic_visit(node)
    return Restore().visit(tree)


def strip_launch_pacing_threshold(tree):
    for cls in tree.body:
        if getattr(cls,'name','')!='ResourceAdmission':continue
        for node in ast.walk(cls):
            if isinstance(node,ast.Compare) and ast.unparse(node.left)=='self.cpu_fraction' and len(node.ops)==1 and isinstance(node.ops[0],ast.Lt) and len(node.comparators)==1 and isinstance(node.comparators[0],ast.Constant) and node.comparators[0].value==.7:
                node.comparators[0].value=.5
