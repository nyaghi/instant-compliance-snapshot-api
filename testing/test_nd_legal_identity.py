"""Full collector replay: explicit legal/DBA identity outranks a broad namesake."""
import json,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import registry_snapshot_server as c

class LegalIdentity(unittest.TestCase):
    def lookup(self,name,rows,aliases=()):
        page=MagicMock();kind=['search'];opened=[]
        class Pending:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            @property
            def value(self):
                return SimpleNamespace(status=200,json=lambda:({'rows':{r['ID']:r for r in rows},'template':[]} if kind[0]=='search' else {'DRAWER_DETAIL_LIST':[{'LABEL':'Status','VALUE':'Active'},{'LABEL':'Principal Address','VALUE':'300 Longwood Avenue Boston MA'}]}))
        page.expect_response.side_effect=lambda *a,**k:Pending()
        page.locator.return_value.click.side_effect=lambda **k:kind.__setitem__(0,'search')
        # Record the selected exact ID used by the real collector.
        def get_role(role,**kw):
            if role=='cell':opened.append(kw['name'])
            return locator
        locator=MagicMock();locator.filter.return_value=locator;locator.get_by_role.return_value=locator
        locator.click.side_effect=lambda **k:kind.__setitem__(0,'detail')
        page.get_by_role.side_effect=get_role
        with patch.object(c,'known_names_for_ein',return_value=list(aliases)),patch.object(c,'nd_search_queries',return_value=[name]),patch('deployment.nd_candidate_evidence.capture'):
            result=c.search_nd_completed(page,c.checker.Organization(name,'042774441'))
        return result,opened

    def row(self,name,ident):
        return {'ID':ident,'RECORD_NUM':ident,'TITLE':[name],'STATUS':'Active'}

    def test_actual_boston_names_choose_full_legal_record(self):
        name="CHILDREN'S HOSPITAL CORPORATION"
        records=[self.row("CHILDREN'S HOSPITAL MEDICAL CENTER",'0004016970'),self.row("THE CHILDREN'S HOSPITAL CORPORATION (dba Boston Children's Hospital)",'0007149369')]
        result,opened=self.lookup(name,records)
        self.assertEqual(result.matched_registry_identifier,'0007149369')
        self.assertEqual(opened,['0007149369'])
        self.assertEqual(result.status,'Active')

    def test_medical_center_without_legal_match_requires_identity_review(self):
        result,opened=self.lookup("CHILDREN'S HOSPITAL CORPORATION",[self.row("CHILDREN'S HOSPITAL MEDICAL CENTER",'0004016970')])
        self.assertEqual(result.status,'Needs Review')
        self.assertEqual(result._cc_identity_review['records'][0]['identifier'],'0004016970')

    def test_reviewed_medical_center_name_is_not_blocked(self):
        n="CHILDREN'S HOSPITAL MEDICAL CENTER"
        with patch.object(c,'known_names_for_ein',return_value=[n]):
            self.assertFalse(c.nd_added_medical_entity_review("CHILDREN'S HOSPITAL CORPORATION",n,'042774441'))

    def test_seventy_saved_names_keep_exact_identity(self):
        roster=json.loads((Path(__file__).parent/'fixtures/fresh-five/LOCAL-70.json').read_text())
        self.assertEqual(len(roster),70)
        for org in roster:
            with self.subTest(name=org['name']):
                result,opened=self.lookup(org['name'],[self.row(org['name'],'0000000001')])
                self.assertEqual(result.matched_registry_identifier,'0000000001')
                self.assertEqual(opened,['0000000001'])
                absent,empty=self.lookup(org['name'],[])
                self.assertEqual(absent.status,c.checker.STATUS_NOT_REGISTERED)
                self.assertEqual(empty,[])

    def test_explicit_dba_preserves_original_legal_identity(self):
        self.assertEqual(c.nd_full_legal_key('The Example Charity Inc. (dba Example Brand)'),c.nd_full_legal_key('Example Charity Inc.'))
        self.assertNotEqual(c.nd_full_legal_key('Example Charity Foundation'),c.nd_full_legal_key('Example Charity Hospital'))

if __name__=='__main__':unittest.main()
