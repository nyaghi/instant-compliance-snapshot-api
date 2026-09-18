"""Group parent metadata is not proof of a subordinate's name-only identity."""
import json,sys,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class GroupIdentityTests(unittest.TestCase):
    def lookup(self,**fields):
        record={'ein':123456789,'name':'National Example Association','sort_name':'Example Local Fund',
                'affiliation_code':9,'exemption_number':1234,**fields}
        with patch.object(c,'identity_fetch',return_value=json.dumps({'organization':record}).encode()):
            return c.identity_irs_names('123456789',time.monotonic()+20)

    def test_subordinate_uses_secondary_without_parent_alias(self):
        r=self.lookup()
        self.assertEqual([n['name'] for n in r['names']],['Example Local Fund'])
        self.assertIn('group_name_note',r)
        self.assertEqual(r['names'][0]['evidence'][0]['type'],'IRS group subordinate secondary name')

    def test_actual_parent_and_independent_records_keep_existing_name(self):
        for affiliation in [1,3,6,7,8]:
            with self.subTest(affiliation=affiliation):
                r=self.lookup(affiliation_code=affiliation)
                self.assertEqual([n['name'] for n in r['names']],['National Example Association'])
                self.assertNotIn('group_name_note',r)

    def test_absent_or_equivalent_secondary_keeps_existing_name(self):
        for value in [None,'','NATIONAL EXAMPLE ASSOCIATION']:
            with self.subTest(secondary=value):
                self.assertEqual(self.lookup(sort_name=value)['names'][0]['name'],'National Example Association')

    def test_wrong_ein_is_rejected_before_any_name(self):
        with self.assertRaises(ValueError):self.lookup(ein=987654321)

    def test_same_ein_return_can_still_establish_a_legal_or_former_name(self):
        header={'names':[c.identity_candidate('Example Previous Local Name','IRS','Form 990 filer legal name','https://irs.example/return')],
                'dba_disclosed':False}
        with patch.object(c,'irs_return_header',return_value=header), \
             patch.object(c,'identity_irs_historical_names',return_value={'names':[],'historical_complete':True}):
            r=self.lookup(latest_object_id='202612349349300001')
        self.assertEqual([n['name'] for n in r['names']],['Example Local Fund','Example Previous Local Name'])

if __name__=='__main__':unittest.main(verbosity=2)
