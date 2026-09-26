"""Identity decisions cannot supply status, change EIN, or erase search failures."""
import copy, json, sys, time, unittest
from pathlib import Path
from datetime import date, timedelta
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class DecisionTests(unittest.TestCase):
    def setUp(self):
        for key, value in [('APP_VERSION','2026.09.26.5-staging'),('NY_CONNECTOR_SIGNING_KEY','test-only-'*8)]:
            p=patch.object(c,key,value);p.start();self.addCleanup(p.stop)
        p=patch.object(c,'known_names_for_ein',return_value=[]);p.start();self.addCleanup(p.stop)
        p=patch.object(c,'log_event');p.start();self.addCleanup(p.stop)
        self.email,self.device='reviewer@example.test','test-device'
    def result(self,state='DC',complete=True,rows=None):
        result=dict(organization_name='Example National Charity',ein='12-3456789',state=state,
                    status='Needs Review',success=False,comments='The address could not be corroborated.',
                    reviewed_alternate_names=['Example Former Name'])
        row=dict(name='Example National Charity',identifier='REG123',location='Boston, MA',
                 url='https://registry.example/public/REG123',raw_status='Active',
                 expiration=date.today()+timedelta(days=200),_identity_outcome='conflict',license_category='Charity')
        c.attach_identity_review(result,dict(records=rows or [row],search_complete=complete,freshness='Source refreshed today.'))
        return result
    def decide(self,result,action='accept',index=0,**changes):
        view=result['identity_review']
        payload=dict(token=view['token'],candidate_id=view['candidates'][index]['id'],action=action,ein=result['ein'],state=result['state'])
        payload.update(changes)
        return c.resolve_identity_review(payload,self.email,self.device)
    def test_accept_identity_computes_status_ignores_client_status(self):
        r=self.decide(self.result(),status='Exempt')
        self.assertEqual(r['status'],'Current');self.assertEqual(r['matched_registry_identifier'],'REG123')
        self.assertIn('not overridden',r['comments']);self.assertIn('Source refreshed today.',r['comments'])
        self.assertEqual(r['identity_review_history'][0]['reviewed_by'],self.email)
    def test_reject_complete_can_return_negative(self):
        r=self.decide(self.result(),'reject');self.assertEqual(r['status'],'Not Registered')
        self.assertEqual(r['matched_registry_identifier'],'')
    def test_reject_incomplete_is_not_negative(self):
        self.assertEqual(self.decide(self.result(complete=False),'reject')['status'],'Unable to Confirm')
    def test_other_unresolved_candidate_prevents_negative(self):
        r=self.result();token=c.identity_review_unpack(r['identity_review']['token'],self.email,self.device)
        second={**token['records'][0],'id':'second','identifier':'REG456'};token['records'].append(second)
        r['identity_review']=c.identity_review_view(token)
        r=self.decide(r,'reject');self.assertEqual(r['status'],'Needs Review')
        r=self.decide(r,'accept',1);self.assertEqual(r['status'],'Current');self.assertEqual(r['matched_registry_identifier'],'REG456')
    def test_undo_restores_unresolved_match(self):
        r=self.decide(self.decide(self.result()),'clear')
        self.assertEqual(r['status'],'Needs Review');self.assertEqual(r['identity_review']['candidates'][0]['decision'],'')
    def test_wrong_ein_state_candidate_or_action_rejected(self):
        for values in [dict(ein='98-7654321'),dict(state='GA'),dict(candidate_id='unknown'),dict(action='current')]:
            with self.subTest(values=values),self.assertRaises(ValueError):self.decide(self.result(),**values)
    def test_tampered_token_rejected(self):
        r=self.result();token=r['identity_review']['token'];body,sig=token.rsplit('.',1)
        with self.assertRaises(ValueError):self.decide(r,token=body+'.'+('0' if sig[0]!='0' else '1')+sig[1:])
    def test_expired_wrong_version_and_session_rejected(self):
        r=self.decide(self.result());record=c.identity_review_unpack(r['identity_review']['token'],self.email,self.device)
        for changes in [dict(expires=0),dict(version='old-staging'),dict(owner=['other@example.test',self.device])]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.decide(r,token=c.identity_review_pack({**record,**changes}))
    def test_explicit_wrong_ein_has_no_accept_control(self):
        r=self.result(rows=[dict(name='Example National Charity',identifier='X',ein='999999999',_identity_outcome='conflict')])
        self.assertNotIn('identity_review',r)
    def test_failed_lookup_without_candidate_has_no_accept_control(self):
        r={};c.attach_identity_review(r,dict(records=[]));self.assertNotIn('identity_review',r)
    def test_wi_surrender_remains_closed_after_acceptance(self):
        r=self.result('WI',False);record=c.identity_review_unpack(r['identity_review']['token'],self.email,self.device)
        record['records'][0]['raw_status']='Voluntary Surrender';record['records'][0]['expiration']='2025-07-31'
        r['identity_review']=c.identity_review_view(record)
        self.assertEqual(self.decide(r)['status'],'Closed / Withdrawn / Canceled')
    def test_wi_unknown_status_is_not_invented(self):
        r=self.result('WI',False);record=c.identity_review_unpack(r['identity_review']['token'],self.email,self.device)
        record['records'][0]['raw_status']='';record['records'][0]['expiration']='';r['identity_review']=c.identity_review_view(record)
        with patch.object(c,'wi_http_detail_text',return_value='Loading'),patch.object(c,'wi_reader_text',return_value='Loading'):
            self.assertEqual(self.decide(r)['status'],'Unable to Confirm')
    def test_wi_rejection_resumes_search_with_scoped_exclusions(self):
        def lookup(name,ein,state):
            self.assertTrue(c.user_rejected_credential(ein,state,'REG123'))
            self.assertFalse(c.user_rejected_credential('98-7654321',state,'REG123'))
            self.assertEqual(c.REVIEWED_NAME_CONTEXT.get()['123456789'],['Example Former Name'])
            return dict(status='Site Not Reachable',success=False,comments='Search timed out.')
        with patch.object(c,'run_state_lookup',side_effect=lookup):
            r=self.decide(self.result('WI',False),'reject')
        self.assertEqual(r['status'],'Site Not Reachable');self.assertFalse(c.USER_IDENTITY_CONTEXT.get())
    def test_exclusions_are_not_sent_to_an_unaware_remote_adapter(self):
        token=c.USER_IDENTITY_CONTEXT.set(dict(ein='123456789',state='WI',rejected=['REG123']))
        try:
            with patch.object(c,'_search_wi_sidecar_unlocked') as remote:
                r=c.search_wi_sidecar(c.checker.Organization('Example','12-3456789'))
                self.assertEqual(r.status,'Site Not Reachable');remote.assert_not_called()
        finally:c.USER_IDENTITY_CONTEXT.reset(token)
    def test_state_specific_interpretation_is_preserved(self):
        for state,raw,kind,expiry,expected in [
            ('GA','Exempt','Exempt Charity','2018-01-01','Exempt'),
            ('GA','Active','Charity','','Delinquent'),
            ('GA','Revoked','Exempt Charity','2099-01-01','Revoked'),
            ('IL','Good Standing','','','Delinquent'),
            ('IL','Good Standing','','2099-01-01','Current'),
            ('DC','Active','Charitable Solicitation - Exempt','','Exempt'),
            ('DC','Active','Charitable Solicitation','2020-01-01','Delinquent'),
            ('RI','Active Pending Renewal','','2020-01-01','Pending')]:
            with self.subTest(state=state,raw=raw,expiry=expiry):
                self.assertEqual(c.identity_review_state_status(state,dict(raw_status=raw,license_category=kind,expiration=expiry)),expected)
    def test_historical_offices_stay_bound_to_ein_and_actual_principal_address(self):
        rows=[dict(fein='12-3456789',name='Example National Charity',entityid='1',principalcity='Boston',principalstate='MA',registrationapproveddate='2026-01-01'),
              dict(fein='12-3456789',name='Example Former Name',entityid='1',principalcity='Concord',principalstate='CA',registrationapproveddate='2010-01-01'),
              dict(fein='98-7654321',name='Example Former Name',entityid='2',principalcity='Miami',principalstate='FL')]
        rows.append(copy.deepcopy(rows[1]))
        with patch.object(c,'identity_fetch',return_value=json.dumps(rows).encode()):r=c.identity_co_names('123456789',time.monotonic()+2)
        self.assertEqual([x['city'] for x in r['organization_records']],['Boston','Concord'])
        self.assertEqual(r['organization_records'][1]['filing_date'],'2010-01-01')
    def test_general_page_notes_cannot_label_a_selected_current_record_closed(self):
        result=c.checker.StateResult('Example National Charity','12-3456789','OH','Current','https://state.example')
        result.source_note='Exemptions may be withdrawn. An older record was closed.'
        self.assertNotEqual(c.reason_code_for_result(result,'Current'),'STATUS_RAW_CLOSED')
        self.assertEqual(c.reason_code_for_result(result,'Closed / Withdrawn / Canceled'),'STATUS_RAW_CLOSED')
    def test_wi_acceptance_preserves_annual_renewal_calculation(self):
        expiry=date.today()+timedelta(days=700)
        expected=c.wi_effective_renewal_due_from_expiration(expiry)[0] or expiry
        self.assertEqual(c.identity_review_wi_status(dict(raw_status='License is current (Active)',expiration=expiry.isoformat())),c.status_from_calendar_date(expected))

if __name__=='__main__':unittest.main()
