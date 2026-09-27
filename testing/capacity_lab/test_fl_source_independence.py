"""Exact scope against the deployed release, including all identity/status rules."""
import ast
from pathlib import Path
import subprocess
import unittest


def restore_source_gate(tree, reference):
    from testing.capacity_lab.test_fl_native_forms import strip_native_forms
    strip_native_forms(tree)
    old = next(n for n in reference.body if getattr(n, 'name', '') == 'fl_business_lookup_enabled')
    new = next(n for n in tree.body if getattr(n, 'name', '') == old.name)
    expected = ast.parse('''def fl_business_lookup_enabled() -> bool:
    """Isolated lab opt-in to the state's alternate public charity-license page."""
    return (APP_VERSION.endswith("-performance-lab")
            and os.environ.get("PUBLIC_BASE_URL") == "https://instant-compliance-snapshot-api-hn4v.onrender.com"
            and os.environ.get("CE_LAB_FL_BUSINESS_LOOKUP") == "1")
''').body[0]
    assert ast.dump(new) == ast.dump(expected)
    tree.body[tree.body.index(new)] = old


class Scope(unittest.TestCase):
    def test_only_source_enablement_changed_in_master(self):
        root = Path(__file__).resolve().parents[2]
        before = ast.parse(subprocess.check_output(
            ['git', 'show', '9de9c95:registry_snapshot_server.py'], cwd=root).decode('utf-8'))
        after = ast.parse((root/'registry_snapshot_server.py').read_text(encoding='utf-8'))
        from testing.capacity_lab.test_fl_native_forms import strip_native_forms
        strip_native_forms(after)
        old = next(n for n in before.body if getattr(n, 'name', '') == 'fl_business_lookup_enabled')
        new = next(n for n in after.body if getattr(n, 'name', '') == old.name)
        expected = ast.parse('''def fl_business_lookup_enabled() -> bool:
    """Isolated lab opt-in to the state's alternate public charity-license page."""
    return (APP_VERSION.endswith("-performance-lab")
            and os.environ.get("PUBLIC_BASE_URL") == "https://instant-compliance-snapshot-api-hn4v.onrender.com"
            and os.environ.get("CE_LAB_FL_BUSINESS_LOOKUP") == "1")
''').body[0]
        self.assertEqual(ast.dump(new), ast.dump(expected))
        after.body[after.body.index(new)] = old
        self.assertEqual(ast.dump(before), ast.dump(after))

    def test_scheduler_deadlines_workers_and_ui_unchanged(self):
        root = Path(__file__).resolve().parents[2]
        subprocess.run(['git', 'diff', '--exit-code', '9de9c95', '--',
            'deployment/durable_queue.py', 'deployment/queue_worker.py',
            'deployment/queue_engine.py', 'deployment/queue_schema.sql',
            'deployment/performance_lab.py', 'web-staging', 'browser-connector'],
            cwd=root, check=True, stdout=subprocess.DEVNULL)


if __name__ == '__main__':
    unittest.main()
