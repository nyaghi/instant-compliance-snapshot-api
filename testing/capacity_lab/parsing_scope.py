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
    strip_pa_form_optimization(tree)
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


def strip_pa_form_optimization(tree):
    """Only PA's redundant ready-form navigation/idle wait is replaced."""
    strip_pa_ein_wait_and_ny_browser_timeout(tree)
    strip_fl_date_post_allowance(tree)
    if not any(getattr(n, 'name', '') == 'pa_prepare_name_fallback_form' for n in tree.body):
        return
    old = ast.parse(subprocess.check_output(['git', 'show', '88e5f17:registry_snapshot_server.py'],
        cwd=Path(__file__).resolve().parents[2]).decode('utf-8'))
    before = next(n for n in old.body if getattr(n, 'name', '') == 'search_pa_with_name_fallback_core')
    original = next(n for n in ast.walk(before) if isinstance(n, ast.Try)
                    and ast.unparse(n.body[0]).startswith('page.goto(url,'))
    after = next(n for n in tree.body if getattr(n, 'name', '') == 'search_pa_with_name_fallback_core')
    target = next(n for n in ast.walk(after) if isinstance(n, ast.Try)
                  and ast.unparse(n.body[0]) == 'pa_prepare_name_fallback_form(page, url)')
    target.body = original.body[:3] + target.body[1:]
    tree.body = [n for n in tree.body if getattr(n, 'name', '') != 'pa_prepare_name_fallback_form']


def strip_pa_ein_wait_and_ny_browser_timeout(tree):
    old = ast.parse(subprocess.check_output(['git', 'show', 'e9d6b9a:registry_snapshot_server.py'],
        cwd=Path(__file__).resolve().parents[2]).decode('utf-8'))
    function = lambda t, name: next(n for n in t.body if getattr(n, 'name', '') == name)
    core = function(tree, 'search_pa_with_name_fallback_core')
    if ast.unparse(core.body[0]) == 'initial_offset = request_offset()':
        assert ast.unparse(core.body[1]) == "result = checker.search_pa(page, org, wait_for_ein=lambda ein: completion_wait('', initial_offset, time.monotonic() + 12.0, ein=ein))"
        core.body[:2] = function(old, core.name).body[:1]
        outer = function(tree, 'search_pa_with_name_fallback')
        wait = next(n for n in outer.body if getattr(n, 'name', '') == 'wait_for_search')
        before = next(n for n in function(old, outer.name).body if getattr(n, 'name', '') == 'wait_for_search')
        assert wait.args.args[-1].arg == 'ein' and ast.literal_eval(wait.args.defaults[-1]) == ''
        wait.args.args.pop();wait.args.defaults.pop()
        comp = next(n for n in ast.walk(wait) if isinstance(n, ast.ListComp))
        old_comp = next(n for n in ast.walk(before) if isinstance(n, ast.ListComp))
        assert ast.unparse(comp.generators[0].ifs[0]) == "row['step'] == 'search' and (canonical_ein_digits(row.get('ein', '')) == canonical_ein_digits(ein) and (not row.get('name')) if ein else not row.get('ein') and key(row.get('name')) == key(query))"
        comp.generators[0].ifs = old_comp.generators[0].ifs
        assert ast.dump(wait) == ast.dump(before)
    ny = function(tree, 'search_ny_direct')
    for node in ast.walk(ny):
        if isinstance(node, ast.Call) and ast.unparse(node.func) == 'isinstance' and len(node.args)==2:
            types = node.args[1]
            if isinstance(types, ast.Tuple) and any(ast.unparse(t)=='checker.PlaywrightTimeoutError' for t in types.elts):
                assert ast.unparse(types) in {'(TimeoutError, checker.PlaywrightTimeoutError, OSError)', '(TimeoutError, checker.PlaywrightTimeoutError)'}
                types.elts = [t for t in types.elts if ast.unparse(t)!='checker.PlaywrightTimeoutError']
                if len(types.elts)==1:node.args[1]=types.elts[0]


def strip_checker_pa_ein_wait(tree):
    fn=next(n for n in tree.body if getattr(n,'name','')=='search_pa')
    if fn.args.args[-1].arg != 'wait_for_ein':return
    assert ast.literal_eval(fn.args.defaults[-1]) is None
    fn.args.args.pop();fn.args.defaults.pop()
    body=next(n for n in fn.body if isinstance(n,ast.Try)).body
    block=next(n for n in body if isinstance(n,ast.If) and 'wait_for_ein is not None' in ast.unparse(n.test))
    expected=ast.parse('''if wait_for_ein is not None and not wait_for_ein(ein):
    result.raw_status_text = "Pennsylvania EIN search did not complete"
    result.source_note = "Pennsylvania did not finish the submitted EIN search; registration status remains unconfirmed."
    result.reason_code = "PA_INCOMPLETE_SEARCH"
    return result
''').body[0]
    assert ast.dump(block)==ast.dump(expected)
    body.remove(block)


def strip_fl_date_post_allowance(tree):
    fn = next((n for n in tree.body if getattr(n, 'name', '') == 'enrich_registration_date_sources'), None)
    if fn is None:
        return
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and ast.unparse(node.func) in {'session.get', 'session.post'}:
            timeout = next(k.value for k in node.keywords if k.arg == 'timeout')
            assert ast.unparse(timeout.func) == 'min' and len(timeout.args) == 2
            assert ast.unparse(timeout.args[1]) == ('max(0.001, date_deadline - time.monotonic())'
                if ast.unparse(node.func) == 'session.get' else 'date_deadline - time.monotonic()')
            assert timeout.args[0].value in (3.0, 6.0)
            timeout.args[0].value = 3.0


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
