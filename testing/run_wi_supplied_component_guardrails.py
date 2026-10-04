import ast
import subprocess
import unittest
from unittest.mock import patch
from pathlib import Path
import registry_snapshot_server as cc

class WisconsinSuppliedNames(unittest.TestCase):
    def match(self,entered,candidate):
        org=cc.checker.Organization(entered,'123456789')
        return cc.wi_snapshot_record_match({'registry_name':candidate,'full_name':candidate},org,cc.organization_match_target_variants(entered,org.ein))

    def test_full_entered_components_match_without_discovery(self):
        for entered,candidate in [('United Animal Nations — RedRover','UNITED ANIMAL NATIONS'),('Beacon Literacy Network / ReadTogether','Beacon Literacy Network, Inc.'),('Harbor Animal Rescue - RescueBridge','RescueBridge')]:
            with self.subTest(entered=entered):
                self.assertIsNotNone(self.match(entered,candidate))

    def test_related_entities_and_locations_still_rejected(self):
        for entered,candidate in [('United Animal Nations — RedRover','United Animal Nations Foundation'),('Wild Ones - Natural Landscapers','Wild Ones Milwaukee Chapter'),('Beacon Literacy - ReadTogether','Other Beacon Literacy')]:
            with self.subTest(entered=entered):self.assertIsNone(self.match(entered,candidate))

    def test_existing_institution_canonical_path_is_not_changed_by_new_hook(self):
        # This existing canonical path already has priority 5. The new hook
        # must not change it; broader institution matching is outside this fix.
        actual=self.match('University of California - Los Angeles','University of California')
        with patch.object(cc,'supplied_separator_component_match',return_value=False):
            baseline=self.match('University of California - Los Angeles','University of California')
        self.assertEqual(actual,baseline)

    def test_ordinary_exact_and_unrelated_names_unchanged(self):
        self.assertIsNotNone(self.match('United Animal Nations','UNITED ANIMAL NATIONS'))
        self.assertIsNone(self.match('Different Animal Foundation','UNITED ANIMAL NATIONS'))

    def test_only_wisconsin_priority_hook_changed_from_bz(self):
        root=Path(__file__).resolve().parents[1]
        old=ast.parse(subprocess.check_output(['git','show','13f9dc1780edaf1605fb4d1168d68182f694fc2d:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        new=ast.parse((root/'registry_snapshot_server.py').read_text(encoding='utf-8-sig'))
        fn=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name=='wi_snapshot_record_match')
        loop=next(n for n in fn.body if isinstance(n,ast.For))
        hooks=[n for n in loop.body if isinstance(n,ast.If) and isinstance(n.test,ast.Call) and isinstance(n.test.func,ast.Name) and n.test.func.id=='supplied_separator_component_match']
        self.assertEqual(len(hooks),1);loop.body.remove(hooks[0])
        self.assertEqual(ast.dump(old),ast.dump(new))

if __name__=='__main__':unittest.main()
