"""Saved official CA record, negative controls, and signed evidence lifecycle."""
import copy
import json
import socket
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock, patch
import registry_snapshot_server as m
from deployment import ca_nonregistration as ca, source_visual_adapters as v
from deployment import state_snapshots as s, identity_evidence, compliance_package
from testing.test_gates22_23_capture_budget import fixture_image


class California(unittest.TestCase):
    def setUp(self):
        f = json.loads((Path(__file__).parent/'fixtures/gate24/pbs-ca-public-record.json').read_text(encoding='utf-8'))[0]
        self.entity, self.regs = f['entity'], f['registrations']
        self.name, self.ein = self.entity['entityName'], '520899215'
        self.org = m.checker.Organization(self.name, self.ein)
        p = patch.object(socket, 'create_connection', side_effect=AssertionError('No live traffic in local tests'))
        p.start(); self.addCleanup(p.stop)

    def classify(self, entity=None, regs=None):
        return m.checker.ca_evoke_status_from_record(entity or self.entity, self.regs if regs is None else regs)

    def test_actual_source_and_generic_names(self):
        for name in [self.name, 'Independent Museum', 'Community Research Institute']:
            for corporate in ['Withdrawn', 'Listed', 'Registered']:
                result = self.classify({**self.entity, 'entityName':name, 'entityStatus':corporate})
                self.assertEqual((result[0], result[2], result[3]), ('Not Registered', '5905917', None))
                self.assertIn('Entity Status: '+corporate, result[1])

    def test_enforcement_and_real_credentials_are_not_absence(self):
        for status in ['Suspended', 'Revoked']:
            self.assertEqual(self.classify({**self.entity,'entityStatus':status})[0], status)
        for field, value in [('registrationNumber','CT123'), ('currentExpirationDate','2030-12-31'),
                ('registrationStatus','Registered'), ('registrationType','Commercial Fundraiser'),
                ('reportingStatus','Enforcement'), ('complianceStatus',['Enforcement'])]:
            changed=[{**self.regs[0],field:value}]
            self.assertFalse(ca.explicit_absence(self.entity, changed))
        active={**self.regs[0], 'registrationNumber':'CT123', 'registrationStatus':'Registered',
                'currentExpirationDate':'2030-12-31'}
        for records in [[self.regs[0],active],[active,self.regs[0]]]:
            self.assertEqual(self.classify({**self.entity,'entityStatus':'Listed'},records)[0], 'Current')
        self.assertFalse(ca.explicit_absence(self.entity, []))
        self.assertNotEqual(self.classify({**self.entity,'entityStatus':'Listed'},
            [{**self.regs[0],'registrationNumber':'CT123'}])[0], 'Current')

    def result(self, *, review=False):
        status, raw, identifier, _ = self.classify()
        return SimpleNamespace(state='CA', success=True, status=status, raw_status_text=raw,
            matched_registry_name=self.name, matched_registry_identifier=identifier,
            _cc_selected_entity=copy.deepcopy(self.entity), _cc_registration_records=copy.deepcopy(self.regs))

    def test_hint_requires_original_entity_record_and_ein(self):
        result=self.result();run=s.CaptureRun(self.name,self.ein,'CA')
        v.remember_ca_selected(run,result)
        hint=run.source_detail_hints['5905917']
        self.assertEqual(hint['url'],'https://ca-rcf.evokeplatform.com/app/publicPortal/registrationDetails/1452545')
        self.assertEqual(hint['ca_explicit_nonregistration']['entity_id'],'5905917')
        for mutate in [lambda r:r._cc_selected_entity.update(fein='987654321'),
                lambda r:r._cc_selected_entity.update(id='999'),
                lambda r:r._cc_registration_records[0]['entityRelated'].update(id='999'),
                lambda r:r._cc_registration_records[0].update(registrationNumber='CT123')]:
            changed=copy.deepcopy(result);mutate(changed);run=s.CaptureRun(self.name,self.ein,'CA')
            v.remember_ca_selected(run,changed)
            self.assertFalse(run.source_detail_hints)

    def test_exact_ein_record_does_not_add_name_search(self):
        entity={**self.entity,'fein':self.ein}
        with patch.object(m.checker,'ca_evoke_entity_search_by_ein',return_value=[entity]), \
             patch.object(m.checker,'ca_evoke_registrations_for_entity',return_value=self.regs), \
             patch.object(m.checker,'ca_evoke_entity_search_by_name',side_effect=AssertionError('Redundant query')):
            result=m.search_ca_master(Mock(),self.org)
        self.assertEqual(result.status,'Not Registered');self.assertTrue(result.success)
        public=m.response_data_for_lookup(result,result.raw_status_text,self.org,self.name,self.ein,'CA',time.perf_counter())
        self.assertEqual(public['status'],'Not Registered')
        self.assertEqual(public['matched_registry_identifier'],'5905917')
        self.assertIn('explicitly lists',public['comments'])

    def test_full_identity_accept_reject_undo_and_package(self):
        run=s.CaptureRun(self.name,self.ein,'CA');result=self.result()
        status,raw,identifier,_=self.classify()
        row=dict(name=self.name,identifier=identifier,ein='',raw_status=raw,status=status,
            expiration=None,url=m.checker.CA_EVOKE_PUBLIC_PORTAL_URL,location='',_identity_outcome='possible')
        result._cc_identity_review=dict(records=[row],search_complete=False)
        result._cc_ca_name_sources={identifier:dict(entity=self.entity,registrations=self.regs)}
        result.success=False;result.status='Needs Review'
        with patch('deployment.lab_identity.trial_identity',return_value=True):
            v.remember_ca_selected(run,result)
        self.assertEqual(len(run.ca_review_candidates),1)
        hint=run.source_detail_hints[identifier]
        text=('Entity Related '+self.name+' - '+identifier+' Registration Number Registration Type Charitable Organization '
              'Registration Status Not Registered Initial Registration Date Current Expiration Date CHARITABLE ORGANIZATION DETAILS')
        self.assertTrue(ca.bound_core(text,hint['ca_explicit_nonregistration']))
        actual=(Path(__file__).parent/'fixtures/gate24/pbs-ca-registration.txt').read_text(encoding='utf-8')
        self.assertTrue(ca.bound_core(actual,hint['ca_explicit_nonregistration']))
        for bad in [text.replace(identifier,'9999999'),text.replace(self.name,'OTHER ORGANIZATION'),
                text.replace('Not Registered','Registered'),text.replace('Registration Number Registration','Registration Number CT123 Registration'),
                text.replace('Current Expiration Date','Current Expiration Date 12/31/2030')]:
            self.assertIsNone(ca.bound_core(bad,hint['ca_explicit_nonregistration']))
        run.document(hint['url'],fixture_image(text),'image',text)
        data=dict(state='CA',ein=self.ein,organization_name=self.name,status='Needs Review',success=False,
            comments='Confirm the exact name record with blank source EIN.',_worker_identity_review=result._cc_identity_review)
        with tempfile.TemporaryDirectory() as folder:
            store=s.SQLiteStore(Path(folder)/'ca.sqlite')
            with patch.object(s,'STORE',store),patch.object(m,'APP_VERSION','fixture-staging'), \
                 patch.object(m,'trial_identity',return_value=False),patch.object(m,'NY_CONNECTOR_SIGNING_KEY','offline-fixture-signing-key-'*3):
                data=s.persist_worker_result(None,run.finish(data),{'state':'CA','payload':{'ein':self.ein}},store=store)
                m.attach_identity_review(data,data['_worker_identity_review']);data=identity_evidence.bind(m,data)
                card=data['identity_review']['candidates'][0]
                self.assertTrue(card.get('evidence_url'))
                def decide(current,action):
                    return m.resolve_identity_review(dict(token=current['identity_review']['token'],ein=self.ein,
                        state='CA',candidate_id=card['id'],action=action),'qa@example.test','fixture-device')
                accepted=decide(data,'accept')
                self.assertEqual(accepted['status'],'Not Registered')
                self.assertEqual(accepted['evidence_url'],card['evidence_url'])
                self.assertFalse(s.completed_negative_result(accepted))
                pdf,kind=compliance_package.evidence(accepted,store)
                self.assertTrue(pdf.startswith(b'%PDF'));self.assertIn('snapshot',kind.lower())
                rejected=decide(accepted,'reject')
                self.assertFalse(rejected.get('evidence_url'))
                undone=decide(rejected,'clear')
                self.assertFalse(undone.get('success'))
                again=decide(undone,'accept')
                self.assertEqual(again['evidence_url'],card['evidence_url'])

    def test_actual_capture_path_uses_one_bound_original_and_no_empty_search(self):
        run=s.CaptureRun(self.name,self.ein,'CA');result=self.result()
        v.remember_ca_selected(run,result)
        hint=run.source_detail_hints['5905917']
        text=('Entity Related '+self.name+' - 5905917 Registration Number Registration Type Charitable Organization '
              'Registration Status Not Registered Initial Registration Date Current Expiration Date CHARITABLE ORGANIZATION DETAILS')
        page=Mock(url=hint['url']);page.goto.return_value=SimpleNamespace(status=200)
        page.inner_text.return_value=text;page.screenshot.return_value=fixture_image(text)
        panel=page.locator.return_value.filter.return_value
        panel.count.return_value=1;panel.bounding_box.return_value=dict(x=0,y=100,width=1400,height=500)
        context=Mock();context.new_page.return_value=page
        browser=Mock();browser.new_context.return_value=context
        pw=MagicMock();master=Mock();master.checker.sync_playwright.return_value=pw
        master.launch_lookup_browser.return_value=browser;master.BROWSER_USER_AGENT='test-only'
        data={**vars(result), 'ein':self.ein,'organization_name':self.name}
        v.capture_result_visuals(master,data,run,time.monotonic()+35)
        self.assertEqual(run.visual_adapter_facts[-1]['outcome'],'captured',run.visual_adapter_facts)
        self.assertEqual(len(run.documents),1)
        self.assertEqual(master.launch_lookup_browser.call_count,1)
        self.assertEqual(page.goto.call_count,1)
        self.assertFalse(hasattr(run,'negative_visual_attempted'))
        assets=run.finish(data)['_worker_source_archives']
        self.assertEqual(assets[0]['identifier'],'5905917')
        self.assertEqual(assets[0]['source_url'],hint['url'])


if __name__=='__main__':unittest.main()
