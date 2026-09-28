"""Normalize the explicitly tested timing functions for earlier scope checks."""
import ast,subprocess
from pathlib import Path

def strip_workload_timing(tree):
    from testing.capacity_lab.identity_grace_scope import strip_identity_grace_queue
    strip_identity_grace_queue(tree)
    root=Path(__file__).resolve().parents[2]
    original=ast.parse(subprocess.check_output(['git','show','1f0cc4f:deployment/durable_queue.py'],cwd=root).decode())
    names={'DurationEstimates','sales_tail_scores','cohort_timing_estimates','claim_candidates'}
    old={n.name:n for n in original.body if getattr(n,'name',None) in names}
    for i,n in enumerate(tree.body):
        if getattr(n,'name',None) in names:tree.body[i]=old[n.name]
