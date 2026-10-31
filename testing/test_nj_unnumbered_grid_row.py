"""A completed unrelated NJ row may lack a registration-number attribute."""
import copy,unittest
from unittest.mock import patch
import registry_snapshot_server as master
from testing.capacity_lab.test_nj_complete_grid import row,grid

class UnnumberedGrid(unittest.TestCase):
    def setUp(self):
        self.org=master.checker.Organization('Example Relief','123456789')
        self.record=row('Unrelated Animal Shelter','987654321')
        self.record['Id']='67088c94-a1a8-e411-80cf-00505690688c'
        self.record['Attributes']=[a for a in self.record['Attributes']if a['Name']!='accountnumber']

    def test_known_other_identity_without_number_can_be_excluded(self):
        self.assertTrue(master.nj_complete_grid_excludes_org(grid([self.record]),self.org))

    def test_uncertain_identity_or_partial_grid_keeps_original_path(self):
        variants=[]
        for field,value in [('crsm_federalein','123456789'),('crsm_federalein','000000000'),
                            ('crsm_federalein',''),('name','Example Relief')]:
            changed=copy.deepcopy(self.record)
            for attr in changed['Attributes']:
                if attr['Name']==field:attr['Value']=attr['DisplayValue']=value
            variants.append(grid([changed]))
        variants += [grid([{**self.record,'Id':'invalid'}]),grid([self.record,self.record]),
                     {**grid([self.record]),'MoreRecords':True}]
        for payload in variants:
            with self.subTest(payload=payload):
                self.assertFalse(master.nj_complete_grid_excludes_org(payload,self.org))

    def test_blank_number_and_known_alias_are_not_unrelated_absent_numbers(self):
        numbered=copy.deepcopy(self.record)
        numbered['Attributes'].append({'Name':'accountnumber','Value':'','DisplayValue':''})
        self.assertFalse(master.nj_complete_grid_excludes_org(grid([numbered]),self.org))
        with patch.object(master,'organization_match_target_variants',return_value=['Example Relief','Unrelated Animal Shelter']):
            self.assertFalse(master.nj_complete_grid_excludes_org(grid([self.record]),self.org))

if __name__=='__main__':unittest.main()
