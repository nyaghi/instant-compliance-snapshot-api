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
    strip_pa_reset_and_ny_http_diagnostic(tree)
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


def strip_pa_reset_and_ny_http_diagnostic(tree):
    strip_fl_verified_first_trial(tree)
    expected = ast.parse('page.get_by_role("button", name=re.compile(r"^Clear$", re.I)).first.click(timeout=1500)').body[0]
    for fn in tree.body:
        if getattr(fn, 'name', '') == 'search_pa':
            body = next(n for n in fn.body if isinstance(n, ast.Try)).body
            nodes = [n for n in body if ast.dump(n) == ast.dump(expected)]
            assert len(nodes) <= 1
            for n in nodes: body.remove(n)
        elif getattr(fn, 'name', '') == 'search_ny_verified':
            for branch in ast.walk(fn):
                if isinstance(branch, ast.If) and ast.unparse(branch.test) == 'response is not None and response.status >= 400':
                    if isinstance(branch.body[0], ast.Expr):
                        diagnostic = ast.parse('attempts.append(f"NY page navigation: HTTP {response.status}")').body[0]
                        assert ast.dump(branch.body[0]) == ast.dump(diagnostic)
                        branch.body.pop(0)


def strip_checker_pa_ein_wait(tree):
    strip_pa_reset_and_ny_http_diagnostic(tree)
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
    strip_warm_ready_and_failure_trace_engine(tree)
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
    strip_warm_ready_and_failure_trace_worker(tree)
    for cls in tree.body:
        if getattr(cls,'name','')!='ResourceAdmission':continue
        for node in ast.walk(cls):
            if isinstance(node,ast.Compare) and ast.unparse(node.left)=='self.cpu_fraction' and len(node.ops)==1 and isinstance(node.ops[0],ast.Lt) and len(node.comparators)==1 and isinstance(node.comparators[0],ast.Constant) and node.comparators[0].value==.7:
                node.comparators[0].value=.5


def strip_warm_ready_and_failure_trace_worker(tree):
    """Undo only readiness and passive trace hooks, retaining every scheduler rule."""
    strip_transport_trace_worker(tree)
    strip_empty_claim_backoff(tree)
    tree.body=[n for n in tree.body if getattr(n,'name','') not in
        {'task_environment','warm_task_engine','log_failure_trace'} and not
        (isinstance(n,ast.Import) and [a.name for a in n.names]==['re'])]
    class Restore(ast.NodeTransformer):
        def visit_Assign(self,node):
            target=ast.unparse(node.targets[0])
            if target=='self.warm_ready':
                assert ast.unparse(node.value)=='None'
                return None
            if target=='child_env' and ast.unparse(node.value).startswith('task_environment('):
                assert ast.unparse(node.value)=='task_environment(os.environ if self.env is None else self.env)'
                return ast.parse("""child_env = dict(os.environ if self.env is None else self.env)
child_env.pop('CE_LAB_DATABASE_URL', None)
child_env.pop('CE_TEST_DATABASE_URL', None)
child_env.pop('RENDER_API_KEY', None)
child_env['CE_LAB_DURABLE_QUEUE'] = '0'
""").body
            return self.generic_visit(node)
        def visit_Try(self,node):
            if len(node.body)==2 and isinstance(node.body[0],ast.If) and 'self.warm_ready = warm_task_engine' in ast.unparse(node.body[0]):
                assert ast.unparse(node.body[0].test)=="settings.get('CE_LAB_WARM_ENGINE') == '1' and sys.platform.startswith('linux') and (self.command == [sys.executable, str(ROOT / 'deployment/queue_engine.py')])"
                assert ast.unparse(node.body[0].body[0])=='self.warm_ready = warm_task_engine(version, settings)'
                assert ast.unparse(node.body[1])=='self.queue.register_worker(self.id, version, slots)'
                assert len(node.handlers)==1 and ast.unparse(node.handlers[0].type)=='BaseException'
                assert not node.orelse and not node.finalbody
                return node.body[1]
            return self.generic_visit(node)
        def visit_Expr(self,node):
            if ast.unparse(node)=='log_failure_trace(r, error)':return None
            return self.generic_visit(node)
    return Restore().visit(tree)


def strip_warm_ready_and_failure_trace_engine(tree):
    strip_transport_trace_engine(tree)
    tree.body=[n for n in tree.body if getattr(n,'name','')!='warm_ready_main']
    for fn in tree.body:
        if getattr(fn,'name','')=='FloridaTrace':
            init=next(n for n in fn.body if getattr(n,'name','')=='__init__')
            if init.args.args[-1].arg=='sink':
                assert ast.literal_eval(init.args.defaults[-1]) is None
                init.args.args.pop();init.args.defaults.pop()
                assert ast.unparse(init.body[-1])=='self.sink = Path(sink) if sink else None'
                init.body.pop()
                record=next(n for n in fn.body if getattr(n,'name','')=='record')
                outer=record.body[0]
                assert ast.unparse(outer.body[-1].test)=='self.sink is not None'
                outer.body.pop()
        if getattr(fn,'name','')=='execute' and fn.args.args[-1].arg=='trace_path':
            assert ast.literal_eval(fn.args.defaults[-1]) is None
            fn.args.args.pop();fn.args.defaults.pop()
            trace=next(n for n in fn.body if isinstance(n,ast.Assign) and ast.unparse(n.targets[0])=='trace')
            assert ast.unparse(trace.value.body)=='FloridaTrace(trace_path)'
            trace.value.body.args=[]
        if getattr(fn,'name','')=='run_job':
            result=next(n for n in fn.body if isinstance(n,ast.Assign) and ast.unparse(n.targets[0])=='result')
            if len(result.value.args)==4:
                assert ast.unparse(result.value.args[-1])=="Path(output).with_suffix('.trace.json')"
                result.value.args.pop()


def strip_transport_trace_engine(tree):
    from testing.capacity_lab.ny_trace_scope import strip_browser_trace_engine
    strip_browser_trace_engine(tree)
    tree.body = [n for n in tree.body if getattr(n, 'name', '') not in {'transport_route', 'observe_transport'}
                 and not (isinstance(n, ast.ImportFrom) and n.module == 'contextlib'
                          and [a.name for a in n.names] == ['contextmanager'])]
    fn = next(n for n in tree.body if getattr(n, 'name', '') == 'execute')
    body = []
    for node in fn.body:
        if isinstance(node, ast.With) and len(node.items) == 1 and ast.unparse(node.items[0].context_expr) == "observe_transport(master, job['state'], trace_path)":
            assert ast.unparse(node.items[0].optional_vars) == 'transport_trace'
            assert len(node.body) == 1 and isinstance(node.body[0], ast.Try)
            body.extend(node.body)
        elif isinstance(node, ast.If) and ast.unparse(node.test) == 'transport_trace':
            assert ast.unparse(node.body[0]) == "results[0]['lab_transport_trace'] = transport_trace.events"
            assert len(node.body) == 1 and not node.orelse
        else: body.append(node)
    fn.body = body


def strip_transport_trace_worker(tree):
    from testing.capacity_lab.ny_trace_scope import strip_browser_trace_worker
    strip_browser_trace_worker(tree)
    tree.body = [n for n in tree.body if getattr(n, 'name', '') != 'log_transport_failure']
    fn = next((n for n in tree.body if getattr(n, 'name', '') == 'log_failure_trace'), None)
    if fn:
        fn.body = [n for n in fn.body if not (isinstance(n, ast.Expr) and ast.unparse(n) == 'log_transport_failure(r, error)')]


def strip_fl_verified_first_trial(tree):
    """The opt-in lab changes only which verified transport sends the same page."""
    strip_nj_public_query(tree)
    expected_error=ast.parse('if fl_verified_transport_first() and not isinstance(self.error, FloridaCertificateError):\n    self.error = None\n').body[0]
    expected_asset=ast.parse('if fl_verified_transport_first() and request.resource_type != "document":\n    return route.fallback()\n').body[0]
    for cls in tree.body:
        if getattr(cls,'name','')=='FloridaVerifiedTransport':
            route=next(n for n in cls.body if getattr(n,'name','')=='route')
            route.body=[n for n in route.body if ast.dump(n) not in {ast.dump(expected_asset),ast.dump(expected_error)}]
    tree.body=[n for n in tree.body if getattr(n,'name','')!='fl_verified_transport_first']
    fn=next((n for n in tree.body if getattr(n,'name','')=='search_fl_with_transport'),None)
    if fn is None:return
    loader=next(n for n in fn.body if getattr(n,'name','')=='load_fl_search_page')
    expected=ast.parse("if fl_verified_transport_first():\n    transport.enable()\n").body[0]
    for n in ast.walk(loader):
        if isinstance(n,ast.Try) and n.body and ast.dump(n.body[0])==ast.dump(expected):
            n.body.pop(0)


def strip_empty_claim_backoff(tree):
    """Strip only the claim timer; process polling, leases and deadlines stay compared."""
    strip_transport_trace_worker(tree)
    tree.body=[n for n in tree.body if getattr(n,'name','')!='EmptyClaimBackoff']
    class Restore(ast.NodeTransformer):
        def visit_Assign(self,node):
            if ast.unparse(node.targets[0])=='self.claim_backoff':
                assert ast.unparse(node.value)=='EmptyClaimBackoff(int(self.id[-8:], 16) / 4294967295)'
                return None
            return self.generic_visit(node)
        def visit_If(self,node):
            text=ast.unparse(node)
            if text=="if used < ceiling and (not self.claim_backoff.ready(time.monotonic())):\n    reason = 'claim_backoff'":return None
            if text=='if ready:\n    self.claim_backoff.reset()':return None
            if isinstance(node.test,ast.BoolOp) and ast.unparse(node.test.values[-1])=='self.claim_backoff.ready(time.monotonic())':
                assert ast.unparse(node.test)=='used < ceiling and time.monotonic() - last_heartbeat < 8 and self.claim_backoff.ready(time.monotonic())'
                node.test.values.pop()
            return self.generic_visit(node)
        def visit_Expr(self,node):
            if ast.unparse(node)=='self.claim_backoff.observe(bool(job), time.monotonic())':return None
            return self.generic_visit(node)
    Restore().visit(tree)


def strip_nj_public_query(tree):
    strip_fl_business_lookup(tree)
    strip_ny_verification_timeout(tree)
    """Restore the browser-only acquisition and inline verbatim classification."""
    helper=next((n for n in tree.body if getattr(n,'name','')=='nj_result_from_body'),None)
    if helper is None:return
    fn=next(n for n in tree.body if getattr(n,'name','')=='search_nj_direct')
    body=next(n for n in fn.body if isinstance(n,ast.Try)).body
    assert ast.unparse(body[-1])=='return nj_result_from_body(page, org, result, body, ein_digits)'
    body[-1:]=helper.body
    runtime=next(n for n in tree.body if getattr(n,'name','')=='run_state_lookup')
    expected=ast.parse('''if state == "NJ" and not capture_source_snapshot:
    direct = search_nj_public_details(org)
    if direct is not None:
        result, body = direct
        return response_data_for_lookup(result, body, org, organization_name, ein, state, lookup_started)
''').body[0]
    matches=[n for n in runtime.body if ast.dump(n)==ast.dump(expected)]
    assert len(matches)==1
    runtime.body.remove(matches[0])
    tree.body=[n for n in tree.body if getattr(n,'name','') not in
        {'nj_public_query_enabled','search_nj_public_details','nj_result_from_body'}]


def strip_ny_verification_timeout(tree):
    """Remove only the typed rethrow; retry budget and denial rules stay compared."""
    fn=next((n for n in tree.body if getattr(n,'name','')=='ny_browser_registry_response'),None)
    if fn is None:
        return
    expected=ast.parse('''try:
    pass
except (TimeoutError, checker.PlaywrightTimeoutError):
    raise
''').body[0].handlers[0]
    found=[(n,h) for n in ast.walk(fn) if isinstance(n,ast.Try)
           for h in n.handlers if ast.dump(h)==ast.dump(expected)]
    assert len(found)<=1
    if found:found[0][0].handlers.remove(found[0][1])


def strip_fl_business_lookup(tree):
    """Verify the exact relocation of FL rules before restoring the prior AST."""
    strip_mi_name_transport(tree)
    if not any(getattr(n,'name','')=='fl_business_public_rows' for n in tree.body):
        return
    from testing.capacity_lab.fl_business_recipe import expected_fl_business_function
    source=subprocess.check_output(['git','show','3ad7d63:registry_snapshot_server.py'],
        cwd=Path(__file__).resolve().parents[2]).decode('utf-8')
    start=source.index('def search_fl_with_transport(')
    end=source.index('\ndef mn_latest_fiscal_year_end_from_text',start)
    expected=ast.parse(expected_fl_business_function(source[start:end])).body[0]
    fn=next(n for n in tree.body if getattr(n,'name','')=='search_fl_with_transport')
    assert ast.dump(fn)==ast.dump(expected), 'FL shared matcher/classifier changed beyond the exact source recipe'
    tree.body[tree.body.index(fn)]=ast.parse(source[start:end]).body[0]
    enrich=next(n for n in tree.body if getattr(n,'name','')=='enrich_registration_date_sources')
    guard=ast.parse('if fl_business_lookup_enabled() and getattr(result, "_cc_fl_business_source_verified", False):\n    return\n').body[0]
    found=[n for n in enrich.body if ast.dump(n)==ast.dump(guard)]
    assert len(found)==1
    enrich.body.remove(found[0])
    tree.body=[n for n in tree.body if getattr(n,'name','') not in {
        'fl_business_lookup_enabled','fl_business_candidate_rows','fl_business_public_rows'}]


def strip_mi_name_transport(tree):
    strip_transport_budget_and_redundancy(tree)
    """Prove query planning/classification unchanged, restoring only transport hooks."""
    import copy
    strip_fl_patient_public(tree)
    if not any(getattr(n,'name','')=='mi_name_http_empty_queries' for n in tree.body):return
    old=ast.parse(subprocess.check_output(['git','show','e57e4c7:registry_snapshot_server.py'],cwd=Path(__file__).resolve().parents[2]).decode('utf-8'))
    originals={n.name:n for n in old.body if isinstance(n,ast.FunctionDef)}
    functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
    fallback=copy.deepcopy(originals['search_mi_name_fallback'])
    start=next(i for i,n in enumerate(fallback.body) if getattr(n,'name','')=='portal_query')
    end=next(i for i,n in enumerate(fallback.body) if isinstance(n,ast.Assign) and ast.unparse(n.targets[0])=='progress')
    plan=copy.deepcopy(fallback.body[start:end])
    empty=next(n for n in plan if isinstance(n,ast.If) and ast.unparse(n.test)=='not variants')
    empty.body=ast.parse('return []').body
    expected=ast.parse('def mi_name_fallback_queries(org):\n    pass\n').body[0]
    expected.body=plan+ast.parse('return variants[:4]').body
    assert ast.dump(functions[expected.name])==ast.dump(expected)
    fallback.body[start:end]=ast.parse('''variants = mi_name_fallback_queries(org)
if not variants:
    return incomplete("No usable organization-name query was available after the EIN search.")
''').body
    at=next(i for i,n in enumerate(fallback.body) if isinstance(n,ast.Assign) and ast.unparse(n.targets[0])=='completed_empty_queries')+1
    fallback.body[at:at]=ast.parse('''result.source_attempts.extend(f"Completed Michigan name query via the same-session public form: {query}"
    for query in progress.get("http_completed_empty_name_queries", []))
''').body
    assert ast.dump(functions[fallback.name])==ast.dump(fallback)
    probe=copy.deepcopy(functions['search_mi_http_completion_probe'])
    matches=[(n,x) for n in ast.walk(probe) if isinstance(n,ast.Try) for x in n.body
             if isinstance(x,ast.If) and 'mi_http_names_enabled(org)' in ast.unparse(x.test)]
    assert len(matches)==1
    parent,node=matches[0]
    expected=ast.parse('''if (mi_http_names_enabled(org) and lookup_deadline is not None
        and re.search(r"\b0\s+record\(s\)\s+found\b|\bno\s+records?\s+found\b|\bno\s+results?\s+found\b", submitted_text, re.I)):
    result._cc_mi_completed_empty_names = mi_name_http_empty_queries(session, org, headers, lookup_deadline)
'''.replace('\x08','\\b')).body[0]
    assert ast.dump(node)==ast.dump(expected)
    parent.body.remove(node)
    assert ast.dump(probe)==ast.dump(originals[probe.name])
    runtime=copy.deepcopy(functions['run_state_lookup'])
    expected=ast.parse('''completed_names = getattr(mi_probe_result, "_cc_mi_completed_empty_names", [])
if completed_names:
    progress["identity"] = (org.organization_name, canonical_ein_digits(org.ein))
    progress["http_completed_empty_name_queries"] = list(completed_names)
    progress["completed_empty_name_queries"] = list(dict.fromkeys([
        *progress.get("completed_empty_name_queries", []), *completed_names]))
''').body
    hits=0
    for parent in ast.walk(runtime):
        if isinstance(getattr(parent,'body',None),list):
            for n in list(parent.body):
                if any(ast.dump(n)==ast.dump(e) for e in expected):parent.body.remove(n);hits+=1
    assert hits==2 and ast.dump(runtime)==ast.dump(originals[runtime.name])
    changed={'search_mi_name_fallback','search_mi_http_completion_probe','run_state_lookup'}
    tree.body=[originals.get(n.name,n) if isinstance(n,ast.FunctionDef) and n.name in changed else n
               for n in tree.body if getattr(n,'name','') not in {'mi_name_fallback_queries','mi_http_names_enabled','mi_name_http_empty_queries'}]


def strip_fl_request_allowance(tree):
    """Restore only the lab-gated HTTP allowance, not TLS/body/deadline rules."""
    cls = next((n for n in tree.body if getattr(n, 'name', '') == 'FloridaVerifiedTransport'), None)
    if cls is None:
        return
    route = next(n for n in cls.body if getattr(n, 'name', '') == 'route')
    calls = [n for n in ast.walk(route) if isinstance(n, ast.Call) and ast.unparse(n.func) == 'self.opener.open']
    assert len(calls) == 1
    timeout = next(k for k in calls[0].keywords if k.arg == 'timeout')
    if ast.unparse(timeout.value) == 'min(8.0, remaining)':
        return
    assert ast.unparse(timeout.value) == 'min(12.0 if fl_verified_transport_first() else 8.0, remaining)'
    timeout.value = ast.parse('min(8.0, remaining)', mode='eval').body


def strip_transport_budget_and_redundancy(tree):
    """Allow only the measured lab transport adjustments, then compare all code."""
    strip_fl_request_allowance(tree)
    from testing.capacity_lab.or_completion_scope import strip_or_completion
    strip_or_completion(tree)
    helper = next((n for n in tree.body if getattr(n, 'name', '') == 'mi_completed_query_covers'), None)
    if helper is None: return
    tree.body.remove(helper)
    functions = {n.name:n for n in tree.body if isinstance(n, ast.FunctionDef)}
    http = functions['mi_name_http_empty_queries']
    request = next(n for n in ast.walk(http) if isinstance(n, ast.Call) and ast.unparse(n.func) == 'session.request')
    timeout = next(k.value for k in request.keywords if k.arg == 'timeout')
    assert ast.unparse(timeout) == "min(4.0 if method == 'GET' else 18.0, remaining)"
    timeout.args[0].orelse.value = 12.0
    deadline = next(n for n in http.body if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == 'deadline')
    assert ast.unparse(deadline.value) == 'time.monotonic() + min(24.0, max(0.0, lookup_deadline - time.perf_counter()))'
    deadline.value = ast.parse('time.monotonic() + min(12.0, max(0.0, lookup_deadline - time.perf_counter()))', mode='eval').body
    loop = next(n for n in ast.walk(http) if isinstance(n, ast.For) and ast.unparse(n.target) == 'query')
    assert ast.unparse(loop.iter) == 'mi_name_fallback_queries(org)'
    loop.iter = ast.parse('mi_name_fallback_queries(org)[:1]', mode='eval').body
    assert ast.unparse(loop.body[0].test) == 'any((mi_completed_query_covers(old, query) for old in completed))'
    loop.body[0].test = ast.parse('any(set(old.casefold().split()).issubset(set(query.casefold().split())) for old in completed)',mode='eval').body
    fallback = functions['search_mi_name_fallback']
    assignment = next(n for n in ast.walk(fallback) if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == 'covered')
    test = assignment.value.args[0].generators[0].ifs[0]
    assert ast.unparse(test) == 'set(query.casefold().split()).issubset(query_tokens) or (mi_http_names_enabled(org) and mi_completed_query_covers(query, variant))'
    assignment.value.args[0].generators[0].ifs[0] = test.values[0]
    nj = functions['search_nj_public_details']
    deadline = next(n for n in nj.body if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == 'deadline')
    assert ast.unparse(deadline.value) == 'time.monotonic() + 18.0'
    deadline.value = ast.parse('time.monotonic() + 12.0',mode='eval').body


def strip_fl_patient_public(tree):
    """Verify and remove only the opt-in public-form read allowance."""
    import copy
    from testing.capacity_lab.ny_body_scope import strip_ny_body_completion
    strip_ny_body_completion(tree)
    fn=next((n for n in tree.body if getattr(n,'name','')=='fl_business_public_rows'),None)
    if fn is None:return
    assignments=[n for n in fn.body if isinstance(n,ast.Assign)
                 and any(isinstance(t,ast.Name) and t.id=='http_seconds' for t in n.targets)]
    if not assignments:return
    assert len(assignments)==1
    expected=ast.parse('http_seconds = 8.0 if fl_business_lookup_enabled() and os.environ.get("CE_LAB_FL_HTTP_PATIENT") == "1" else 4.0').body[0]
    assert ast.dump(assignments[0])==ast.dump(expected)
    old=ast.parse(subprocess.check_output(['git','show','8f41320:registry_snapshot_server.py'],cwd=Path(__file__).resolve().parents[2]).decode('utf-8'))
    original=next(n for n in old.body if getattr(n,'name','')==fn.name)
    fn.body.remove(assignments[0])
    assert isinstance(fn.body[0],ast.Expr) and isinstance(fn.body[0].value,ast.Constant) and isinstance(fn.body[0].value.value,str)
    fn.body[0]=copy.deepcopy(original.body[0])
    restored=[]
    for n in ast.walk(fn):
        if isinstance(n,ast.BinOp) and isinstance(n.op,ast.Add) and ast.unparse(n.right)=='2 * http_seconds':
            n.right=ast.Constant(8.0);restored.append('total')
        if isinstance(n,ast.Call) and ast.unparse(n.func)=='min' and n.args and ast.unparse(n.args[0])=='http_seconds':
            n.args[0]=ast.Constant(4.0);restored.append('read')
    assert sorted(restored)==['read','total']
    assert ast.dump(fn)==ast.dump(original), 'FL change extends beyond the exact bounded transport allowance'
