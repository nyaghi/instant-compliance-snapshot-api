"""Reported RedRover failure: generated supplied names, never discovery.

No live registry calls. These controls exercise the shared matching paths,
including geographic scope and different-EIN negatives.
"""
import unittest
import ast
import subprocess
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as cc


class EnteredSeparatorControls(unittest.TestCase):
    def test_patch_changes_only_component_matching_and_completed_nc_review(self):
        root=Path(__file__).resolve().parents[1]
        baseline=subprocess.check_output(['git','show','0ef56372c5a893bebdb0ead19f4cd12103431145:registry_snapshot_server.py'],cwd=root).decode('utf-8')
        before=ast.parse(baseline)
        after=ast.parse((root/'registry_snapshot_server.py').read_text(encoding='utf-8-sig'))
        after.body=[node for node in after.body if not isinstance(node,ast.FunctionDef) or node.name not in {'supplied_separator_component_match','nc_completed_candidates_for_review','licensed_same_legal_dba_records'}]
        selector=next(node for node in after.body if isinstance(node,ast.FunctionDef) and node.name=='select_licensed_charity')
        duplicate_hooks=[node for node in ast.walk(selector) if isinstance(node,ast.BoolOp) and any(isinstance(value,ast.UnaryOp) and isinstance(value.operand,ast.Call) and isinstance(value.operand.func,ast.Name) and value.operand.func.id=='licensed_same_legal_dba_records' for value in node.values)]
        self.assertEqual(len(duplicate_hooks),1)
        duplicate_hooks[0].values=duplicate_hooks[0].values[:-1]
        fn=next(node for node in after.body if isinstance(node,ast.FunctionDef) and node.name=='registry_name_is_safe_for_org')
        hooks=[node for node in fn.body if isinstance(node,ast.If) and isinstance(node.test,ast.Call) and isinstance(node.test.func,ast.Name) and node.test.func.id=='supplied_separator_component_match']
        self.assertEqual(len(hooks),1)
        fn.body.remove(hooks[0])
        old_failure=next(node for node in before.body if isinstance(node,ast.FunctionDef) and node.name=='final_four_connector_failure')
        new_failure=next(node for node in after.body if isinstance(node,ast.FunctionDef) and node.name=='final_four_connector_failure')
        new_failure.body=[node for node in new_failure.body if not (isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='candidates' for t in node.targets)) and not (isinstance(node,ast.If) and isinstance(node.test,ast.Name) and node.test.id=='candidates')]
        self.assertEqual(ast.dump(old_failure),ast.dump(new_failure))
        self.assertEqual(ast.dump(before),ast.dump(after))

    def setUp(self):
        token=cc.REVIEWED_NAME_CONTEXT.set({})
        self.addCleanup(cc.REVIEWED_NAME_CONTEXT.reset,token)

    def test_supplied_components_survive_clean_and_damaged_separators(self):
        for mark in [' - ', ' -- ', ' \u2013 ', ' \u2014 ', ' / ', ' '+chr(0xe2)+chr(0x20ac)+chr(0x201d)+' ']:
            with self.subTest(separator=repr(mark)):
                name='United Animal Nations'+mark+'RedRover'
                targets=cc.organization_match_target_variants(name,'680124097')
                self.assertIn('United Animal Nations',cc.licensed_compound_retrieval_names(name))
                self.assertIn('RedRover',cc.licensed_compound_retrieval_names(name))
                self.assertTrue(cc.ar_registry_name_is_safe('United Animal Nations',name,targets,''))
                score=cc.score_candidate(name,'680124097',{'name':'United Animal Nations'})
                self.assertEqual(score['decision'],'accepted')

    def test_no_discovery_or_automatic_nickname_acceptance(self):
        with patch.object(cc,'known_names_for_ein',return_value=[]),patch.object(cc,'discover_organization_names',side_effect=AssertionError('Discovery forbidden')):
            name='United Animal Nations \u2014 RedRover'
            self.assertEqual(cc.score_candidate(name,'680124097',{'name':'United Animal Nations','ein':'123456789'})['reason'],'REJECT_DIFFERENT_EIN')
            self.assertEqual(cc.score_candidate(name,'680124097',{'name':'United Animal Nations'})['decision'],'accepted')
            self.assertNotEqual(cc.score_candidate(name,'680124097',{'name':'RedRover'})['decision'],'accepted')

    def test_rule_generalizes_without_organization_or_ein_exceptions(self):
        for name,component in [('Beacon Literacy Network - ReadTogether','Beacon Literacy Network'),('Harbor Animal Rescue / RescueBridge','Harbor Animal Rescue, Inc.'),('River Habitat Alliance — GreenFuture','GreenFuture')]:
            with self.subTest(name=name):
                self.assertTrue(cc.supplied_separator_component_match(name,component))
                self.assertEqual(cc.score_candidate(name,'123456789',{'name':component})['decision'],
                                 'accepted' if len(cc.distinctive_match_tokens(component))>=2 else 'possible')
                self.assertFalse(cc.supplied_separator_component_match(name,component+' Foundation'))

    def test_complete_supplied_legal_name_uses_normal_full_name_identity(self):
        import time
        name='Beacon Literacy Network - ReadTogether'
        org=cc.checker.Organization(name,'123456789')
        for address,expected in [({'decision':'unavailable'},'accepted'),({'decision':'corroborated'},'accepted')]:
            with patch.object(cc,'reconciled_registry_address',return_value=address):
                row={'name':'Beacon Literacy Network','ein':'','location':'Example, NY'}
                self.assertEqual(cc.licensed_charity_identity(org,row,'NC',time.monotonic()+1),expected)

    def test_location_and_related_entity_negatives(self):
        for name,candidate in [('University of California - Los Angeles','University of California'),('Beacon Learning - Youth Network','Beacon Learning - Another Chapter'),('Wild Ones - Natural Landscapers','Wild Ones Milwaukee Chapter'),('United Animal Nations - RedRover','United Animal Nations Foundation')]:
            with self.subTest(name=name,candidate=candidate):
                self.assertEqual(cc.score_candidate(name,'680124097',{'name':candidate})['decision'],'rejected')

    def test_ordinary_hyphenated_words_remain_whole(self):
        for name,fragment in [('Make-A-Wish Foundation','Make'),('Warrior-Scholar Project Foundation','Warrior'),('Health-Alliance, Inc.','Health')]:
            self.assertNotIn(fragment,cc.organization_match_target_variants(name,''))


if __name__=='__main__':unittest.main()
