"""Scope normalization for independently tested public-table reuse."""
import ast
from pathlib import Path
import subprocess

CHANGED = {'nh_records_from_snapshot_bytes', 'nh_download_live_pdf_records',
           'nh_live_pdf_records', 'run_state_lookup', 'search_la_downloaded_export'}

def restore_parsing_optimization(tree):
    if not any(isinstance(n, ast.FunctionDef) and n.name == 'nh_records_from_snapshot_bytes' for n in tree.body):
        return
    old = ast.parse(subprocess.check_output(['git', 'show', '433927e:registry_snapshot_server.py'],
                   cwd=Path(__file__).resolve().parents[2]).decode('utf-8'))
    originals = {n.name: n for n in old.body if isinstance(n, ast.FunctionDef)}
    tree.body = [originals.get(n.name, n) if isinstance(n, ast.FunctionDef) and n.name in CHANGED else n
                 for n in tree.body if not (isinstance(n, ast.FunctionDef) and n.name == 'nh_records_from_snapshot_bytes')]
