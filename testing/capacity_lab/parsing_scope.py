"""Scope normalization for independently tested public-table reuse."""
import ast
from pathlib import Path
import subprocess

CHANGED = {'search_fl_with_transport', 'search_wv_public_details', 'search_wv_precise', 'registry_table_text_snapshot', 'identity_oh_names', 'search_oh', 'oh_ein_search_source', 'oh_result_from_detail_text', 'search_oh_direct_details', 'hi_direct_details_from_source', 'search_hi_direct_details', 'identity_irs_names', 'sales_identity_evidence', 'sales_names_from_evidence', 'sales_result_with_identity', 'search_sc_resilient', 'load_ks_weekly_checker', 'distinctive_match_tokens', '_cached_distinctive_match_tokens', 'nh_records_from_snapshot_bytes', 'nh_download_live_pdf_records',
           'nh_live_pdf_records', 'run_state_lookup', 'search_la_downloaded_export'}

def restore_parsing_optimization(tree):
    if not any(isinstance(n, ast.FunctionDef) and n.name == 'nh_records_from_snapshot_bytes' for n in tree.body):
        return
    old = ast.parse(subprocess.check_output(['git', 'show', '433927e:registry_snapshot_server.py'],
                   cwd=Path(__file__).resolve().parents[2]).decode('utf-8'))
    originals = {n.name: n for n in old.body if isinstance(n, ast.FunctionDef)}
    tree.body = [n for n in tree.body if not (isinstance(n, ast.ClassDef) and n.name == 'WestVirginiaPublicLookup')]
    tree.body = [originals.get(n.name, n) if isinstance(n, ast.FunctionDef) and n.name in CHANGED else n
                 for n in tree.body if not (isinstance(n, ast.FunctionDef) and n.name in {'fl_completed_search_form_available', 'search_wv_public_details', 'registry_table_text_snapshot', 'oh_ein_search_source', 'oh_result_from_detail_text', 'search_oh_direct_details', 'hi_direct_details_from_source', 'search_hi_direct_details', 'nh_records_from_snapshot_bytes', '_cached_distinctive_match_tokens', 'sales_identity_evidence', 'sales_names_from_evidence', 'sales_result_with_identity'})]
