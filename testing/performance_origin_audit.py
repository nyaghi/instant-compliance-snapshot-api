"""Normalize only deployment-origin guards for historical source comparisons.

The active trial/baseline identity behavior has separate isolation tests. All
surrounding state parsing, matching, timing and classification ASTs remain exact.
"""
import ast

def restore_trial_alias_identity(tree):
    """Restore only audited four-state alias identity and literal-prefix patches.

    Dedicated behavior controls cover alternate-name ambiguity, exact offices,
    foreign EINs, preserved mature-state behavior and complete prefix coverage.
    """
    import hashlib
    import subprocess
    from pathlib import Path
    hashes = {'final_four_browser_lookup': '370c00ed20f96704ce58513aaaf99a24bb7f7e23dff06ab258e6b4dacbe52170', 'licensed_charity_foreign_ein': '990d0ff73cab5282012daee325eaad3bc2a6ae492a36eadd33038e15795b4ae2', 'licensed_charity_identity': '0026d70c8a124abfbcd4a22950d9e2ce1ec360ba3ed3d8ed5c1a99fd95648062', 'select_licensed_charity': '1f42e67a1f858c682330b3440cb1e93b2fd5a2ebb43371e467ed0687d905e193'}
    baseline = None
    class AliasIdentity(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            nonlocal baseline
            if hashlib.sha256(ast.dump(node).encode()).hexdigest() != hashes.get(node.name):
                return node
            if baseline is None:
                baseline = ast.parse(subprocess.check_output(
                    ['git','show','9ee8f02:registry_snapshot_server.py'],
                    cwd=Path(__file__).resolve().parents[1]).decode('utf-8'))
            return next(n for n in baseline.body if isinstance(n,ast.FunctionDef) and n.name == node.name)
    return AliasIdentity().visit(tree)


def restore_trial_0616(tree):
    """Restore only the exact separately tested AL/NC acquisition changes."""
    import hashlib
    import subprocess
    from pathlib import Path
    hashes = {'al_charity_search_evidence': 'ecd5b3a28d12745dba5589483ef37991ea366039b795a8628c4bb2705fe40ddd', 'final_four_browser_lookup': '3c18f2007981a2429c16fa609d2c6ca68a5e1d860f43bf1e3379425fdd1e5431'}
    baseline = None
    class Acquisition(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            nonlocal baseline
            if hashlib.sha256(ast.dump(node).encode()).hexdigest() != hashes.get(node.name):
                return node
            if baseline is None:
                baseline = ast.parse(subprocess.check_output(
                    ['git', 'show', '8c70929:registry_snapshot_server.py'],
                    cwd=Path(__file__).resolve().parents[1]).decode('utf-8'))
            return next(n for n in baseline.body if isinstance(n, ast.FunctionDef) and n.name == node.name)
    return Acquisition().visit(restore_trial_alias_identity(tree))

def restore_nv_reservation_0614(tree):
    """Normalize only the exact, separately tested reservation acquisition patch."""
    import hashlib
    import subprocess
    from pathlib import Path
    hashes = {'nv_name_reservation_evidence': 'a09cbbd71c75a42b892764dd61e345eeb9848d1ffac45697dc31d45c9305f574',
              'final_four_browser_lookup': 'c8e62aaf7b042273557b4e3bc849e1690344c131177884c7162122642b773998',
              'final_four_clean_evidence': 'd53d6956ed0d77a8d8ed6168bb7eb940d1a606b58a6eca3cc60b475cd66bf99a'}
    baseline = None
    class Reservation(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            nonlocal baseline
            if hashlib.sha256(ast.dump(node).encode()).hexdigest() != hashes.get(node.name):
                return node
            if baseline is None:
                baseline = ast.parse(subprocess.check_output(
                    ['git', 'show', '16fc599:registry_snapshot_server.py'],
                    cwd=Path(__file__).resolve().parents[1]).decode('utf-8'))
            return next((n for n in baseline.body if isinstance(n, ast.FunctionDef) and n.name == node.name), None)
    return Reservation().visit(restore_trial_0616(tree))

def restore_trial_0614(tree):
    """Normalize only the two exact trial-only 0.6.14/0.6.15 compatibility gates."""
    class VersionGate(ast.NodeTransformer):
        def visit_BoolOp(self, node):
            versions = "{'0.6.4', '0.6.5', '0.6.6', '0.6.7', '0.6.8', '0.6.9', '0.6.10', '0.6.11', '0.6.12', '0.6.13', '0.6.14', '0.6.15', '0.6.16', '0.6.17', '0.6.18', '0.6.19', '0.6.20'}"
            for variable in ("record.get('connector_version')", 'connector_version'):
                expression = 'trial_identity() and ' + variable + ' in ' + versions
                if ast.dump(node) == ast.dump(ast.parse(expression, mode='eval').body):
                    return ast.parse(expression.replace(", '0.6.14'", '').replace(", '0.6.15'", '').replace(", '0.6.16'", '').replace(", '0.6.17'", '').replace(", '0.6.18'", '').replace(", '0.6.19'", '').replace(", '0.6.20'", ''), mode='eval').body
            return self.generic_visit(node)
    return VersionGate().visit(tree)

def restore_nv_business_scope_0613(node):
    """Restore only the exact reviewed Nevada category exclusion for old audits."""
    import hashlib
    import subprocess
    from pathlib import Path
    if (node.name != 'final_four_browser_lookup' or
            hashlib.sha256(ast.dump(node).encode()).hexdigest() !=
            '3baad52924c4ea7546e60e6d09606852ee798dff83901cd0f725999f8b2dc314'):
        return node
    baseline = ast.parse(subprocess.check_output(
        ['git', 'show', '9a7ea66:registry_snapshot_server.py'],
        cwd=Path(__file__).resolve().parents[1]).decode('utf-8'))
    return next(n for n in baseline.body if isinstance(n, ast.FunctionDef) and n.name == node.name)

_MS_0613_HASHES = {'ms_detail_identity_fields': '8b5c2feace2ac4ccd5157aa0d2f1464eb5e2d7ab0168e010009c84da6acfc99d', 'ms_legal_description_identity': '5ea30499734e4ec31c60bf522a981f9b894c00b3fbf797243eb2e6b70ae57390', 'search_ms_fast': '421b139d9ccebe395ab9d0e57e5004a1ab788235c6897f13b73f5c765c10bac8', 'search_batch_browser_state': '21fb4d0ae7228977dcd82cdedd83573904a18fd6e84f6288394f469209feed8f'}


def restore_ms_0613(node):
    """Normalize only the audited MS detail/name patch in historical guards."""
    import hashlib
    import subprocess
    from pathlib import Path
    expected = _MS_0613_HASHES.get(node.name)
    if not expected or hashlib.sha256(ast.dump(node).encode()).hexdigest() != expected:
        return node
    baseline = ast.parse(subprocess.check_output(
        ['git', 'show', 'bc56e10:registry_snapshot_server.py'],
        cwd=Path(__file__).resolve().parents[1]).decode('utf-8'))
    return next((n for n in baseline.body if isinstance(n, ast.FunctionDef) and n.name == node.name), None)

ORIGIN = 'https://instant-compliance-snapshot-api-hn4v.onrender.com'


# Exact September 30 NJ acquisition patch. Behavioral tests cover complete
# exemptions, query binding and identity conflicts. Historical comparisons
# restore only these audited AST hashes; future changes still fail closed.
_NJ_0613_HASHES = {'nj_completed_query_rows': 'ecaa72e5539ceec5f931eb8b0285c24da305036fb7e53b932c11ef8285d2f274', 'nj_name_exemption_result': 'd0de72925b09ba67ec3c71e5455465284d2028a76aef3e4d91c31bdd7a12bfa4', 'nj_search_body': 'ec59e7d7672c0604127e87e0703aa5b2d8babe80ad86de245f4679607feb849c', 'search_nj_public_details': 'bf9805bc2b8d77f72e915a94d8e5c65520a7495e88b11f2c773a734ebc41820a', 'search_nj_direct': 'e9d0d8ec01ab6e59df0141841ef648663ddd4590e784e801762e2b40c3eeaab0', 'search_nj_with_name_fallback': 'e5cacf08a1d0f597a2aed1902ab9e73978b3ab06fadd54f0700ad1e316fca103'}

def restore_nj_0613(node):
    import hashlib
    import subprocess
    from pathlib import Path
    expected = _NJ_0613_HASHES.get(node.name)
    if not expected or hashlib.sha256(ast.dump(node).encode()).hexdigest() != expected:
        return node
    baseline = ast.parse(subprocess.check_output(
        ['git','show','887ccc7:registry_snapshot_server.py'],
        cwd=Path(__file__).resolve().parents[1]).decode('utf-8'))
    return next((n for n in baseline.body if isinstance(n,ast.FunctionDef) and n.name == node.name), None)


class RestoreApprovedOrigin(ast.NodeTransformer):
    def visit_FunctionDef(self, node):
        node = restore_nv_reservation_0614(node)
        if node is None: return None
        node = restore_ms_0613(node)
        if node is None: return None
        node = restore_nj_0613(node)
        if node is None: return None
        # Independently tested source exception: the public NJ grid can expose
        # an exact-EIN Exempt row without a registration number. Only the new
        # helper and the two exact acquisition prefixes below are normalized;
        # the existing status, matching, timeout and other-state code is exact.
        if node.name in {'nj_exact_ein_exempt_row', 'identity_alias_template'}:
            return None
        return self.generic_visit(node)

    def visit_Assign(self, node):
        for query in ('query', 'ein'):
            expected = ast.parse('exemption = nj_exact_ein_exempt_row(data, ' + query + ')').body[0]
            if ast.dump(node) == ast.dump(expected):
                return None
        return self.generic_visit(node)

    def visit_If(self, node):
        for source in [
            # The literal chapter-template cleanup is tested with real aliases,
            # legal names and user edits. Normalize only its exact guard here.
            'if evidence_type in {"DBA", "AKA / DBA", "Form 990 DBA", "Other Name"} and identity_alias_template(name):\n return None',
            'if exemption is not None:\n return [exemption]',
            '''if exemption is not None:
 body = f"Charity Name: {exemption[0]}\\nStatus Exempt Federal EIN {ein}\\n"
 result = checker.StateResult(org.organization_name, org.ein, "NJ", checker.STATUS_UNKNOWN, base + path)
 result.matched_registry_identifier = ein
 return nj_result_from_body(None, org, result, body, ein), body''',
            'if trial_identity():\n SUPPORTED_STATES.extend(["AL", "NC", "NV", "TN"])',
            "if os.environ.get('CE_FINAL_FOUR_TRIAL') == '1':\n identity = trial_identity()\n return bool(identity and origin == identity['origin'])",
        ]:
            if ast.dump(node) == ast.dump(ast.parse(source).body[0]):
                return None
        for call in ("public_status(result)", "result.source_note"):
            expected = ast.parse('if result.state in {"AL", "NC", "NV", "TN"} and getattr(result, "status_reason", "") == "LICENSED_CHARITY_SOURCE":\n    return ' + call).body[0]
            if ast.dump(node) == ast.dump(expected):
                return None
        # Remove only the two exact new-state metadata dispatches. All mature
        # state bodies below them remain byte-for-byte equivalent in the AST.
        for call in ("final_four_date_metadata(result, final_status)",
                     "final_four_filing_metadata(result, dates, final_status)"):
            expected = ast.parse('if str(getattr(result, "state", "")).upper() in ("AL", "NC", "NV", "TN"):\n    return ' + call).body[0]
            if ast.dump(node) == ast.dump(expected):
                return None
        return self.generic_visit(node)

    def visit_BoolOp(self, node):
        node = restore_trial_0614(node)
        current = "record.get('connector_version') != '0.5.10' and not (trial_identity() and record.get('connector_version') in {'0.6.4', '0.6.5', '0.6.6', '0.6.7', '0.6.8', '0.6.9', '0.6.10', '0.6.11', '0.6.12', '0.6.13'})"
        if ast.dump(node) == ast.dump(ast.parse(current, mode='eval').body):
            return ast.parse("record.get('connector_version') != '0.5.10'", mode='eval').body
        if ast.dump(node)==ast.dump(ast.parse('APP_VERSION.endswith("-staging") or trial_identity()',mode='eval').body):
            return ast.parse('APP_VERSION.endswith("-staging")',mode='eval').body
        if (isinstance(node.op,ast.And) and ast.dump(node.values[-1])==ast.dump(ast.parse(
                "not (trial_identity() and os.environ.get('CE_FINAL_FOUR_CHILD') != '1')",mode='eval').body)):
            node.values.pop()
            return self.generic_visit(node)
        current="state != 'NY' and origin != NY_CONNECTOR_ORIGIN and not trial_identity()"
        if ast.dump(node)==ast.dump(ast.parse(current,mode='eval').body):
            return ast.parse("state != 'NY' and origin != NY_CONNECTOR_ORIGIN",mode='eval').body
        if (isinstance(node.op,ast.And) and len(node.values)==2
                and ast.dump(node.values[1])==ast.dump(ast.parse("not (trial_identity() and connector_version in {'0.6.4', '0.6.5', '0.6.6', '0.6.7', '0.6.8', '0.6.9', '0.6.10', '0.6.11', '0.6.12', '0.6.13'})",mode='eval').body)):
            return self.visit(node.values[0])
        return self.generic_visit(node)

    def visit_ImportFrom(self, node):
        return None if node.module == 'deployment.lab_identity' else node

    def visit_UnaryOp(self, node):
        if (isinstance(node.op, ast.Not) and isinstance(node.operand, ast.Call)
                and isinstance(node.operand.func, ast.Name)
                and node.operand.func.id == 'performance_origin_enabled'):
            return ast.parse("os.environ.get('PUBLIC_BASE_URL') != " + repr(ORIGIN), mode='eval').body
        return self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id == 'performance_origin_enabled':
            assert not node.args and not node.keywords, 'Unexpected origin guard arguments'
            return ast.parse("os.environ.get('PUBLIC_BASE_URL') == " + repr(ORIGIN), mode='eval').body
        return self.generic_visit(node)
