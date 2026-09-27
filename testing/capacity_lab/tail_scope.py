"""Exact allowance for source-wide tail timing; no queue fences may change."""
import ast
from pathlib import Path
import subprocess


def strip_tail_latency(tree):
    root = Path(__file__).resolve().parents[2]
    original = subprocess.check_output(['git', 'show', 'e05c18d:deployment/durable_queue.py'], cwd=root).decode()
    expected = original.replace(
        'count * estimates.get(state, 10.0) / max(1, limits.get(state, 4))',
        "count * getattr(estimates, 'tails', estimates).get(state, 10.0) / max(1, limits.get(state, 4))")
    expected = expected.replace("return {r['state']: r['seconds'] for r in c.execute(", 'return DurationEstimates(c.execute(')
    expected = expected.replace('AS seconds "\n            "FROM unnest',
        'AS seconds, "\n            "percentile_cont(0.95) WITHIN GROUP (ORDER BY recent.seconds) AS tail_seconds "\n            "FROM unnest')
    expected = expected.replace('(sorted(states), now-86400))}', '(sorted(states), now-86400)))')
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DurationEstimates')
    assert len(cls.body) == 2 and isinstance(cls.body[0], ast.Expr)
    expected_init = ast.parse('''def __init__(self, rows):
    rows = list(rows)
    super().__init__((r['state'], r['seconds']) for r in rows)
    self.tails = {r['state']: r['tail_seconds'] for r in rows}
''').body[0]
    assert ast.dump(cls.bases[0]) == ast.dump(ast.Name(id='dict', ctx=ast.Load()))
    assert ast.dump(cls.body[1]) == ast.dump(expected_init)
    tree.body.remove(cls)
    assert ast.dump(tree) == ast.dump(ast.parse(expected)), 'Change beyond exact elapsed-time priority recipe'
    tree.body = ast.parse(original).body

