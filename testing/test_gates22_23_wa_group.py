"""Washington detail provenance through signed group review and evidence."""
import io
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from pypdf import PdfReader
import registry_snapshot_server as m
from deployment import group_identity_review as g, state_snapshots as s
from deployment.search_history import SourceQueryReceipt
from testing.test_gates22_23_capture_budget import fixture_image


class WashingtonGroup(unittest.TestCase):
    def setUp(self):
        self.name='Example Research Center';self.member='123456789';self.group='987654321'
        self.url='https://ccfs.sos.wa.gov/#/organization'
        self.body=('ORGANIZATION INFORMATION\nOrganization Name:\n'+self.name+
            '\nRegistration Number:\u00a0\n1102928\nFEIN Number:\n'+self.group+
            '\nStatus:\nActive\nRenewal Date:\n11/30/2026\nCONTACT INFORMATION')
        self.module=m.load_wa_nm_module()

    def interpret(self,body,ein=None):
        result=self.module.SearchResult(organization_name=self.name,ein=ein or self.group,state='WA',
            status=self.module.STATUS_UNKNOWN,raw_status_text='',source_url=self.url,source_note='',matched_registry_name=self.name)
        result.matched_registry_identifier='stale'
        return m.wa_apply_detail_master(result,body)

    def test_registration_is_from_exact_fein_detail_only(self):
        result=self.interpret(self.body)
        self.assertEqual(result.matched_registry_identifier,'1102928')
        self.assertEqual(result.verified_registry_ein,self.group)
        self.assertEqual(result.status,self.module.classify_by_renewal(self.module.parse_date('11/30/2026'),'Active'))
        for body,ein in [(self.body,self.member),(self.body.replace('1102928',''),None),
                         (self.body.replace('1102928','CONTACT INFORMATION'),None),
                         (self.body.replace('1102928','1102928 / 22'),None)]:
            self.assertFalse(self.interpret(body,ein).matched_registry_identifier)

    def test_numbered_detail_group_review_original_pdf_and_reject_history(self):
        def receipt(run,rows):
            SourceQueryReceipt(run,{'state':'WA','operation':'search','ein':run.ein,
                'url':'https://ccfs-api.prod.sos.wa.gov/api/CFTPublicSearch/GetCFPublicSearchList',
                'source_kind':'state_portal','filter_label':'FEIN'}).complete(rows)
        base_run=s.CaptureRun(self.name,self.member,'WA');receipt(base_run,0)
        base=base_run.finish({'state':'WA','ein':self.member,'organization_name':self.name,'status':'Not Registered','success':True})
        result=self.interpret(self.body)
        copied=m.copy_external_result(m.checker.Organization(self.name,self.group),'WA',result)
        related={**m.checker.asdict(copied),'status':m.public_status(copied),'_worker_identity_review':{'records':[]}}
        group_run=s.CaptureRun(self.name,self.group,'WA');receipt(group_run,1)
        group_run.document(self.url,fixture_image(self.body),'image',self.body)
        related=group_run.finish(related);related.pop('_worker_identity_review')
        proof={'kind':'same_name_irs_group_return','requested_ein':self.member,'registry_ein':self.group,
            'name':self.name,'group_exemption_number':'1234','observed_at':int(time.time()),
            'member_source_url':g.API.replace('/api/v2/','/')+'organizations/'+self.member,
            'group_source_url':g.API.replace('/api/v2/','/')+'organizations/'+self.group}
        converted=g.convert(m,base,related,proof)
        self.assertIsNotNone(converted)
        self.assertEqual(converted['_worker_identity_review']['records'][0]['identifier'],'1102928')
        self.assertEqual([x['search_receipt']['source_order'] for x in converted['_worker_search_history']['completed']],[1,2])
        with tempfile.TemporaryDirectory() as folder:
            store=s.SQLiteStore(Path(folder)/'wa.sqlite')
            with patch.object(s,'STORE',store),patch.object(m,'APP_VERSION','fixture-staging'),patch.object(m,'trial_identity',return_value=False),patch.object(m,'NY_CONNECTOR_SIGNING_KEY','fixture-signing-key-'*3):
                public=s.persist_worker_result(None,converted,{'state':'WA','payload':{'ein':self.member}},store=store)
                m.attach_identity_review(public,public['_worker_identity_review'])
                card=public['identity_review']['candidates'][0]
                self.assertEqual(card['identifier'],'1102928');self.assertEqual(card['ein'],self.group)
                ref=card['evidence_url'];self.assertTrue(ref)
                _,pdf=s.saved_pdf(ref.split('/')[-1][:-4],store)
                self.assertEqual(len(PdfReader(io.BytesIO(pdf)).pages),1)
                def decide(action):
                    return m.resolve_identity_review({'token':public['identity_review']['token'],'ein':self.member,'state':'WA','candidate_id':card['id'],'action':action},'qa@example.test','device')
                accepted=decide('accept');self.assertEqual(accepted['status'],related['status']);self.assertEqual(accepted['evidence_url'],ref)
                rejected=decide('reject');self.assertNotEqual(rejected.get('evidence_url'),ref)
                self.assertTrue(rejected.get('search_history_url'),rejected)
                self.assertEqual(base['_worker_search_history']['completed'][0]['search_receipt']['source_order'],1)


if __name__=='__main__':unittest.main()
