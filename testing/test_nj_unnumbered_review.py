"""Unnumbered exemption remains a signed identity question, never name-only acceptance."""
import copy,json,time,unittest
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as c
from deployment.nj_unnumbered_review import REASON
F=json.loads((Path(__file__).parent/'fixtures/nj-christian-unnumbered.json').read_text())
class UnnumberedReview(unittest.TestCase):
    def setUp(self):
        self.org=c.checker.Organization('Christian Research Institute Inc.','226063412')
        self.data=copy.deepcopy(F['modeled_response'])
    def read(self,*,decision='unavailable',data=None,trial=True,mode='standard'):
        token=c.LAB_LOOKUP_MODE_CONTEXT.set(mode)
        try:
            with patch.object(c,'trial_identity',return_value={'origin':'local'}if trial else None),patch.object(c,'known_names_for_ein',return_value=[]),patch.object(c,'reconciled_registry_address',return_value={'decision':decision,'basis':'Modeled EIN-linked location check'}),patch.object(c,'licensed_charity_street_evidence',return_value=None):
                return c.nj_name_exemption_result(self.data if data is None else data,self.org,time.monotonic()+2)
        finally:c.LAB_LOOKUP_MODE_CONTEXT.reset(token)
    def test_observed_unnumbered_row_is_retained_for_review_without_applying_exemption(self):
        for decision in ['unavailable','conflict']:
            result=self.read(decision=decision);self.assertEqual(result.status,'Needs Review');self.assertFalse(result.success);self.assertEqual(result.reason_code,REASON)
            context=result._cc_identity_review;self.assertFalse(context['search_complete']);row=context['records'][0]
            self.assertEqual(row['name'],'CHRISTIAN RESEARCH INSTITUTE');self.assertEqual(row['identifier'],'');self.assertEqual(row['ein'],'');self.assertEqual(row['status'],'Exempt');self.assertEqual(row['location'],'IRVINE, CA')
    def test_existing_corroborated_exemption_and_nontrial_sales_paths_are_preserved(self):
        result=self.read(decision='corroborated');self.assertEqual(result.status,'Exempt');self.assertTrue(result.success);self.assertEqual(result.reason_code,'NJ_COMPLETE_UNNUMBERED_EXEMPTION')
        self.assertIsNone(self.read(trial=False));self.assertIsNone(self.read(mode='sales'))
    def test_explicit_other_ein_other_name_and_different_ein_proof_cannot_be_reviewed(self):
        for key,value in [('crsm_federalein','987654321'),('name','Entirely Different Charity'),('crsm_filestanding','Compliant'),('accountnumber','CH12345')]:
            data=copy.deepcopy(self.data);next(a for a in data['Records'][0]['Attributes']if a['Name']==key)['DisplayValue']=value
            self.assertIsNone(self.read(data=data))
        self.assertIsNone(self.read(decision='different_ein'))
    def test_partial_error_multiple_or_duplicate_rows_never_inherit_review(self):
        for change in [{'ItemCount':2},{'ItemCount':True},{'PageNumber':2},{'MoreRecords':True},{'Success':False},{'Error':'blocked'},{'Records':self.data['Records']*2}]:self.assertIsNone(self.read(data={**self.data,**change}))
        data=copy.deepcopy(self.data);data['Records'][0]['Attributes'].append({'Name':'name','DisplayValue':'Other'});self.assertIsNone(self.read(data=data))
    def test_signed_user_choice_applies_status_only_after_accept_and_reject_is_not_negative(self):
        result=self.read();base={'state':'NJ','ein':'22-6063412','organization_name':self.org.organization_name,'status':'Needs Review','success':False,'comments':'Identity unresolved.','source_url':result.source_url}
        with patch.object(c,'trial_identity',return_value={'origin':'local'}),patch.object(c,'NY_CONNECTOR_SIGNING_KEY','test-only-key-not-a-real-secret-'*3):
            c.attach_identity_review(base,result._cc_identity_review);view=base['identity_review'];candidate=view['candidates'][0]
            common={'token':view['token'],'state':'NJ','ein':base['ein'],'candidate_id':candidate['id']}
            accepted=c.resolve_identity_review({**common,'action':'accept'},'fixture@example.com','fixture-device')
            self.assertEqual(accepted['status'],'Exempt');self.assertTrue(accepted['success'])
            rejected=c.resolve_identity_review({**common,'action':'reject'},'fixture@example.com','fixture-device')
            self.assertNotEqual(rejected['status'],'Not Registered')
            with self.assertRaises(ValueError):c.resolve_identity_review({**common,'action':'accept','ein':'99-9999999'},'fixture@example.com','fixture-device')
    def test_named_review_does_not_fall_through_to_detail_or_drop_its_context(self):
        result=self.read();initial=c.checker.StateResult(self.org.organization_name,self.org.ein,'NJ','Not Registered','https://state');initial.success=True
        with patch.object(c,'trial_identity',return_value={'origin':'local'}),patch.object(c,'nj_same_lookup_zero_queries',return_value={self.org.ein}),patch.object(c,'nj_name_fallback_queries',return_value=['Christian Research Institute']),patch.object(c,'search_nj_direct',return_value=result)as source:
            final=c.search_nj_with_name_fallback(None,self.org)
        self.assertEqual(final.reason_code,REASON);self.assertEqual(source.call_count,1);self.assertTrue(final._cc_identity_review['records'])
if __name__=='__main__':unittest.main()
