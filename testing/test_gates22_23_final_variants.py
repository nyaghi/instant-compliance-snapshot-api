"""Observed source wording and generated possessive fragments; no live requests."""
import ast
import copy
from functools import lru_cache
from pathlib import Path
import unittest
from unittest.mock import patch
import registry_snapshot_server as m


@lru_cache(maxsize=2)
def compiled_fl_plan(source):
    """Compile the actual planner slice, stopping before any transport action."""
    outer=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='search_fl_with_transport')
    useful=next(n for n in outer.body if isinstance(n,ast.FunctionDef) and n.name=='useful_fl_search_variant')
    start=next(i for i,n in enumerate(outer.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='generated_variants' for t in n.targets))
    end=next(i for i,n in enumerate(outer.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='search_variants' for t in n.targets))
    body=ast.parse('original_name=org.organization_name').body+[copy.deepcopy(useful)]+copy.deepcopy(outer.body[start:end+1])+ast.parse('return search_variants').body
    fn=ast.FunctionDef(name='plan',args=ast.arguments(posonlyargs=[],args=[ast.arg(arg='org')],kwonlyargs=[],kw_defaults=[],defaults=[]),body=body,decorator_list=[],type_params=[])
    namespace=dict(m.__dict__)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'actual-fl-plan','exec'),namespace)
    return namespace['plan']


def fl_plan(source, org):
    return compiled_fl_plan(source)(org)


class FinalVariants(unittest.TestCase):
    def test_fl_actual_hospital_plan_keeps_identity_terms_and_removes_orphan(self):
        source=Path(m.__file__).read_text(encoding='utf-8')
        for apostrophe in ["'",'\u2019']:
            name='The Children'+apostrophe+'s Hospital of Philadelphia';ein='231352166'
            token=m.REVIEWED_NAME_CONTEXT.set({ein:['The Childrens Hospital Of Philadelphia']})
            try:
                plan=fl_plan(source,m.checker.Organization(name,ein))
                self.assertNotIn('s hospital',[q.lower() for q in plan])
                self.assertTrue(any('philadelphia' in q.lower() for q in plan))
                self.assertLessEqual(len(plan),9)  # One reviewed identity + existing eight fallbacks.
            finally:m.REVIEWED_NAME_CONTEXT.reset(token)

    def test_fl_literal_initial_and_reviewed_names_are_not_filtered(self):
        source=Path(m.__file__).read_text(encoding='utf-8')
        ein='123456789'
        token=m.REVIEWED_NAME_CONTEXT.set({ein:['S Hospital']})
        try:
            plan=fl_plan(source,m.checker.Organization("Children's Regional Hospital",ein))
            self.assertIn('s hospital',[q.lower() for q in plan])
        finally:m.REVIEWED_NAME_CONTEXT.reset(token)
        self.assertEqual(fl_plan(source,m.checker.Organization('S Hospital',ein))[0].casefold(),'s hospital')

    def test_ca_exact_observed_retired_label_and_adverse_controls(self):
        entity={'id':'5055738','entityStatus':'Exempt','entityName':'THE SCRIPPS RESEARCH INSTITUTE','fein':'330435954'}
        reg={'registrationType':'Charitable Organization','registrationStatus':'Not Registered Merged Out','registrationNumber':'CT0183736','currentExpirationDate':'2019-02-15','renewalEvaluationDate':'2020-02-15'}
        status,raw,identifier,due=m.checker.ca_evoke_status_from_record(entity,[reg])
        self.assertEqual((status,identifier,due),('Exempt','5055738',None))
        self.assertIn('Not Registered Merged Out',raw)
        for value,expected in [('Suspended','Suspended'),('Revoked','Revoked'),('Closed','Closed / Withdrawn / Canceled'),('Registered','Closed / Withdrawn / Canceled')]:
            self.assertEqual(m.checker.ca_evoke_status_from_record({**entity,'entityStatus':value},[reg])[0],expected)
        for value,expected in [('Enforcement','Suspended'),('Revoked','Revoked')]:
            self.assertEqual(m.checker.ca_evoke_status_from_record(entity,[{**reg,'reportingStatus':value}])[0],expected)
        for value in ['Not Registered','Merged Out Pending','Not Registered Merged Out Closed']:
            result=m.checker.ca_evoke_status_from_record(entity,[{**reg,'registrationStatus':value}])
            self.assertNotEqual(result[2],'5055738')


if __name__=='__main__':unittest.main()
