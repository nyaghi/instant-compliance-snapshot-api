"""Generic group relationship retrieval, original evidence, and signed choices."""
import copy
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from pypdf import PdfReader
import registry_snapshot_server as m
from deployment import group_identity_review as g, state_snapshots as s, identity_evidence
from testing.test_gates22_23_capture_budget import fixture_image


class GroupIdentity(unittest.TestCase):
    def setUp(self):
        self.member = {'ein':123456789,'name':'Example Research Center','exemption_number':1234,
                       'affiliation_code':6,'city':'Example City','state':'NY','sort_name':None}
        self.group = {**self.member,'ein':987654321,'affiliation_code':9,'sort_name':'Group Return'}
        self.name=self.member['name'];self.ein='123456789'

    def proof(self):
        return g.proof_from_profiles(m,self.name,self.ein,self.member,self.group)

    def base(self,state='CA'):
        return {'state':state,'ein':self.ein,'organization_name':self.name,'status':'Not Registered',
                'success':True,'comments':'Completed exact-EIN search.','lookup_seconds':1}

    def test_profiles_require_full_name_both_eins_same_group_and_explicit_return(self):
        self.assertTrue(self.proof())
        for changes in [{'ein':123456789},{'exemption_number':5678},{'sort_name':'Local Chapter'},
                        {'affiliation_code':3},{'city':'Another City'},{'name':'Example Research Center Foundation'}]:
            with self.subTest(changes=changes):
                self.assertIsNone(g.proof_from_profiles(m,self.name,self.ein,self.member,{**self.group,**changes}))
        for changes in [{'ein':111111111},{'exemption_number':0},{'sort_name':'Different Subordinate'},
                        {'name':'Another Research Center'},{'affiliation_code':3}]:
            self.assertIsNone(g.proof_from_profiles(m,self.name,self.ein,{**self.member,**changes},self.group))

    def test_metadata_search_fetches_only_one_exact_group_candidate(self):
        calls=[]
        def fetch(url,deadline):
            calls.append((url,deadline))
            if 'search.json' in url:return json.dumps({'organizations':[
                {'ein':987654321,'name':self.name,'sub_name':self.name+' Group Return'},
                {'ein':111111111,'name':self.name+' Foundation','sub_name':self.name+' Foundation Group Return'}]}).encode()
            return json.dumps({'organization':self.group if '987654321.json' in url else self.member}).encode()
        with patch.dict(m.PUBLIC_PROFILE_CACHE,{},clear=True),patch.object(m,'identity_fetch',side_effect=fetch):
            self.assertTrue(g.find_relationship(m,self.name,self.ein,time.monotonic()+4))
        self.assertEqual(len(calls),3);self.assertEqual(len({d for _,d in calls}),1)

    def test_normal_success_outage_and_unrelated_negative_do_not_run_group_registry(self):
        lookup=lambda *a:self.fail('Unexpected related registry query')
        with patch.object(g,'find_relationship',return_value=None) as discover:
            for changes in [{'status':'Current'},{'status':'Site Not Reachable','success':False},
                            {'state':'NC'},{'identity_review':{'candidates':[{}]}}]:
                base={**self.base(),**changes};self.assertIs(g.recover(m,base,lookup),base)
            discover.assert_not_called()
            base=self.base();self.assertIs(g.recover(m,base,lookup),base)
            discover.assert_called_once()

    def test_one_related_lookup_keeps_original_ein_and_existing_deadline(self):
        base=self.base();calls=[]
        token=s.DEADLINE.set(time.monotonic()+30);self.addCleanup(s.DEADLINE.reset,token)
        before=s.DEADLINE.get()
        def lookup(name,ein,state):
            from deployment.search_history import SourceQueryReceipt
            calls.append((name,ein,state,s.DEADLINE.get()))
            self.assertEqual(s.CURRENT.get().ein,ein)
            SourceQueryReceipt(s.CURRENT.get(),{'state':state,'operation':'search','ein':ein,
                'url':'https://ca-rcf.evokeplatform.com/','source_kind':'state_portal','filter_label':'Exact FEIN'}).complete(1)
            text=name+' EIN '+ein+' Exempt 54321'
            s.CURRENT.get().document('https://ca-rcf.evokeplatform.com/app/publicPortal/entityDetails/54321',fixture_image(text),'image',text)
            return {**base,'ein':ein,'status':'Exempt','success':True,'matched_registry_name':name,
                    'matched_registry_identifier':'54321','raw_status_text':'Exempt',
                    'source_url':'https://ca-rcf.evokeplatform.com/app/publicPortal/entityDetails/54321'}
        with patch.object(g,'find_relationship',return_value=self.proof()):
            out=g.recover(m,base,lookup)
        self.assertEqual(len(calls),1);self.assertLessEqual(calls[0][3],before)
        self.assertEqual(out['status'],'Needs Review');self.assertEqual(out['ein'],self.ein)
        self.assertEqual(out['_worker_identity_review']['records'][0]['ein'],'987654321')
        self.assertEqual(out['_worker_source_archives'][0]['ein'],self.ein)
        self.assertIn('987654321',out['_worker_source_archives'][0]['capture_note'])
        self.assertEqual(out['_worker_search_history']['ein'],self.ein)
        self.assertEqual(out['_worker_search_history']['completed'][0]['query']['ein'],'987654321')
        with tempfile.TemporaryDirectory() as folder:
            store=s.SQLiteStore(Path(folder)/'group-history.sqlite')
            public=s.persist_worker_result(None,out,{'state':'CA','payload':{'ein':self.ein}},store=store)
            self.assertTrue(public.get('review_evidence_context'),public)

    def test_known_group_failure_cannot_remain_not_registered(self):
        with patch.object(g,'find_relationship',return_value=self.proof()):
            out=g.recover(m,self.base(),lambda *a:(_ for _ in ()).throw(TimeoutError()))
        self.assertEqual(out['status'],'Unable to Confirm');self.assertFalse(out['success'])
        self.assertEqual(out['reason_code'],'GROUP_RECORD_LOOKUP_INCOMPLETE')
        self.assertEqual(out['group_lookup_diagnostics']['error_type'],'TimeoutError')
        self.assertEqual(out['source_note'],out['comments'])
        self.assertNotIn('Confirm whether this record applies',out['comments'])

    def test_incomplete_related_result_retains_reason_without_claiming_a_candidate(self):
        related={**self.base('WA'),'ein':'987654321','status':'Unable to Confirm','success':False,
                 'status_reason':'WA_DETAIL_EIN_UNCONFIRMED','source_note':'The source detail did not expose its EIN.'}
        with patch.object(g,'find_relationship',return_value=self.proof()):
            out=g.recover(m,self.base('WA'),lambda *a:related)
        self.assertEqual(out['group_lookup_diagnostics']['status_reason'],'WA_DETAIL_EIN_UNCONFIRMED')
        self.assertIn(related['source_note'],out['source_note'])
        self.assertFalse(out.get('_worker_identity_review'));self.assertFalse(out['success'])

    def test_signed_accept_reject_undo_keep_originals_and_state_status(self):
        base=self.base();proof=self.proof();url='https://ca-rcf.evokeplatform.com/app/publicPortal/entityDetails/54321'
        text=self.name+' EIN 987654321 Exempt 54321';raw=fixture_image(text)
        asset=s.asset_for(raw,kind='image',state='CA',ein='987654321',run_id='group-fixture-12345678',
            source_url=url,identifier='54321',record_name=self.name,public_text=text,organization_name=self.name)
        related={**base,'ein':'987654321','status':'Exempt','success':True,'matched_registry_name':self.name,
            'matched_registry_identifier':'54321','raw_status_text':'Exempt','source_url':url,
            '_worker_source_archives':[asset]}
        converted=g.convert(m,base,related,proof)
        self.assertEqual(converted['_worker_source_archives'][0]['content'],asset['content'])
        with tempfile.TemporaryDirectory() as folder:
            store=s.SQLiteStore(Path(folder)/'group.sqlite')
            with patch.object(s,'STORE',store),patch.object(m,'APP_VERSION','fixture-staging'), \
                 patch.object(m,'trial_identity',return_value=False),patch.object(m,'NY_CONNECTOR_SIGNING_KEY','fixture-signing-key-'*3):
                data=s.persist_worker_result(None,converted,{'state':'CA','payload':{'ein':self.ein}},store=store)
                m.attach_identity_review(data,data['_worker_identity_review'])
                card=data['identity_review']['candidates'][0]
                self.assertEqual(card['ein'],'987654321');self.assertEqual(card['group_identity']['requested_ein'],self.ein)
                ref=card['evidence_url'];self.assertTrue(ref)
                meta,pdf=s.saved_pdf(ref.split('/')[-1][:-4],store)
                self.assertEqual(len(PdfReader(io.BytesIO(pdf)).pages),1)
                self.assertIn('987654321',meta['capture_note']);self.assertIn(self.ein,meta['capture_note'])
                def decide(current,action):
                    return m.resolve_identity_review({'token':current['identity_review']['token'],'ein':self.ein,'state':'CA',
                        'candidate_id':card['id'],'action':action},'qa@example.test','device')
                accepted=decide(data,'accept')
                self.assertEqual(accepted['status'],'Exempt');self.assertEqual(accepted['ein'],self.ein)
                self.assertEqual(accepted['verified_registry_ein'],'987654321');self.assertEqual(accepted['evidence_url'],ref)
                rejected=decide(accepted,'reject')
                self.assertEqual(rejected['status'],'Unable to Confirm');self.assertNotEqual(rejected.get('evidence_url'),ref)
                undone=decide(rejected,'clear')
                self.assertEqual(undone['status'],'Unable to Confirm');self.assertTrue(undone['confirmation_required'])
                self.assertFalse(undone.get('evidence_url'))

    def test_other_ein_unrelated_record_or_uncertain_status_cannot_convert(self):
        related={**self.base(),'ein':'987654321','status':'Exempt','matched_registry_name':self.name,
                 'matched_registry_identifier':'54321','source_url':'https://ca-rcf.evokeplatform.com/app/publicPortal/entityDetails/54321'}
        for changes in [{'ein':'111111111'},{'matched_registry_name':self.name+' Foundation'},
                        {'status':'Unable to Confirm'},{'success':False},{'state':'MA'},
                        {'_worker_identity_review':{'records':[{}]}}]:
            self.assertIsNone(g.convert(m,self.base(),{**related,**changes},self.proof()))

    def test_group_review_interpretation_is_retained_for_all_seven_states(self):
        with patch.object(m,'APP_VERSION','fixture-staging'),patch.object(m,'trial_identity',return_value=False), \
             patch.object(m,'NY_CONNECTOR_SIGNING_KEY','fixture-signing-key-'*3):
            for state,status in zip(sorted(g.STATES),['Exempt','Delinquent','Current','Upcoming Filing','Current','Exempt','Current']):
                base=self.base(state);base.update(status='Needs Review',success=False)
                row={'name':self.name,'identifier':'12345','ein':'987654321','raw_status':'Source-specific standing',
                     'status':status,'group_identity':self.proof(),'_identity_outcome':'possible'}
                m.attach_identity_review(base,{'records':[row],'search_complete':False})
                card=base['identity_review']['candidates'][0]
                out=m.resolve_identity_review({'token':base['identity_review']['token'],'ein':self.ein,'state':state,
                    'candidate_id':card['id'],'action':'accept'},'qa@example.test','device')
                self.assertEqual(out['status'],status)

if __name__=='__main__':unittest.main(verbosity=2)
