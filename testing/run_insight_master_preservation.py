"""Whole-function parity for registry logic against the current lab baseline."""
import ast
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
BASE='00426759be4124702f4267b6df3def980bbb326a'
class MasterPreservation(unittest.TestCase):
    def test_all_existing_registry_functions_are_unchanged(self):
        old=subprocess.check_output(['git','show',BASE+':registry_snapshot_server.py'],cwd=ROOT).decode('utf-8')
        current=(ROOT/'registry_snapshot_server.py').read_text(encoding='utf-8')
        nodes=lambda text:{n.name:ast.dump(n,include_attributes=False) for n in ast.parse(text).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        self.assertEqual(nodes(old),nodes(current))
        classes=lambda text:next(n for n in ast.parse(text).body if isinstance(n,ast.ClassDef) and n.name=='RegistrySnapshotHandler')
        before={n.name:ast.dump(n,include_attributes=False) for n in classes(old).body if isinstance(n,ast.FunctionDef)}
        after={n.name:ast.dump(n,include_attributes=False) for n in classes(current).body if isinstance(n,ast.FunctionDef)}
        self.assertEqual(set(after)-set(before),{'_send_head_start_handoff'})
        for name in before:
            if name!='do_POST':self.assertEqual(before[name],after[name],name)
if __name__=='__main__':unittest.main(verbosity=2)
