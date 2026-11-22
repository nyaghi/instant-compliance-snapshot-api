import base64,copy,json,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import registry_snapshot_server as c
from deployment.nc_selected_history import enrich,CORE
ROOT=Path(__file__).resolve().parents[1]
ROSTER=json.loads((ROOT/'testing/fixtures/gate55/LOCAL-70.json').read_text(encoding='utf-8'))
RESULTS=[]

def fixture(org,n=0,raw='Current Active'):
    identifier='SL'+str(300000+n);url='https://www.sosnc.gov/online_services/search/charities_profile/'+str(400000+n)
    expiry='06/30/2027'if raw=='Current Active'else'06/30/2025'
    card=c.nc_charity_record_evidence({'CSL Legal Name':org['name'],'CSL Type':'Charitable Organization','Status':raw,'License':identifier,'Expiration Date':expiry,'profile_url':url})
    fields={'Name':org['name'],'Registration #':identifier,'Status':raw,'Expiration Date':expiry,'Last Application Date':'11/01/2026','Street':'123 MAIN ST','City':'BOSTON','State':'MA','Zip':'02115','profile_url':url}
    row=c.nc_charity_profile_evidence(card,fields)
    result=NS(state='NC',success=True,status=row['status'],matched_registry_identifier=identifier,_cc_license_record=row,source_note='Confirmed source.',evidence_url='original-profile.pdf')
    return result,fields

class SelectedHistory(unittest.TestCase):
    def test_70_full_adapter_pairs_keep_status_identity_and_renewal_with_legacy_protocol(self):
        for n,org in enumerate(ROSTER):
            seeded,fields=fixture(org,n)
            card={'CSL Legal Name':org['name'],'CSL Type':'Charitable Organization','Status':fields['Status'],'License':fields['Registration #'],'Expiration Date':fields['Expiration Date'],'profile_url':fields['profile_url']}
            results=[]
            for enabled in [False,True]:
                calls=[]
                def collect(q):
                    calls.append(q)
                    if q['operation']=='search':return dict(state='NC',query=q,complete=True,verification_pending=False,total=1,rows=[card])
                    out=dict(query=q,complete=True,fields=fields)
                    if q.get('history')!='profile':out['filings']=dict(url=fields['profile_url'].replace('/charities_profile/','/charities_filings/'),complete=True,rows=[dict(type='Renewal Charity',date='10/01/2026')])
                    return out
                with patch.object(c,'trial_identity',return_value=True),patch.object(c,'licensed_charity_names',return_value=([org['name']],[])),patch.object(c,'licensed_charity_identity',return_value='accepted'),patch.object(c,'licensed_charity_foreign_ein',return_value=None),patch.object(c,'reconciled_registry_address',return_value={'decision':'corroborated'}),patch.object(c,'identity_irs_names',return_value={}):
                    r=c.final_four_browser_lookup(c.checker.Organization(org['name'],org['ein']),'NC',collect,nc_selected_history=enabled)
                results.append((r.status,r.success,r.matched_registry_identifier,r.matched_registry_name,r._cc_license_record.get('renewal')))
                self.assertEqual(len([q for q in calls if q.get('history')=='selected']),int(enabled))
            self.assertEqual(results[0],results[1],org)

    def test_signed_feature_negotiation_keeps_old_clients_on_existing_protocol(self):
        from testing import run_final_four_continuation_guardrails as signed
        t=signed.ContinuationControls();t.setUp()
        try:
            for enabled in [False,True]:
                opts={'evidence_protocol':'nc-selected-history-v1'}if enabled else {}
                code,response=t.start('NC',**opts);queries=[]
                for _ in range(8):
                    if response['phase']=='complete':break
                    q=response['query'];queries.append(q);e=t.provider(q)
                    if q.get('history')=='profile':e.pop('filings',None)
                    code,response=t.advance(response,evidence=e)
                self.assertEqual((code,response['phase']),(200,'complete'))
                self.assertTrue(response['result']['success'])
                self.assertEqual([q.get('history')for q in queries if q['operation']=='detail'],['profile','selected']if enabled else[None])
        finally:t.doCleanups()

    def test_selected_history_without_pixels_preserves_original_profile_archive(self):
        from testing import run_final_four_continuation_guardrails as signed
        from testing.test_state_snapshots import image
        from deployment import state_snapshots
        t=signed.ContinuationControls();t.setUp()
        try:
            with tempfile.TemporaryDirectory()as folder:
                store=state_snapshots.SQLiteStore(Path(folder)/'snapshots.sqlite')
                with patch.object(state_snapshots,'STORE',store):
                    code,response=t.start('NC',evidence_protocol='nc-selected-history-v1');profile_snapshot=None
                    for _ in range(8):
                        if response['phase']=='complete':break
                        q=response['query'];e=t.provider(q);extra={}
                        if q.get('history')=='profile':
                            e.pop('filings',None)
                            extra['state_snapshot']=dict(query=q,source_url=q['url'],captured_at=time.time(),public_text="America's Charities SL000448 Current Active Filing Extension Granted 11/15/2026",image=base64.b64encode(image("America's Charities",'SL000448')).decode())
                        code,response=t.advance(response,evidence=e,**extra)
                    self.assertEqual((code,response['phase']),(200,'complete'))
                    result=response['result'];self.assertTrue(result['evidence_url'])
                    ident=result['evidence_url'].rsplit('/',1)[-1].removesuffix('.pdf')
                    meta,_,_=store.load(ident)
                    self.assertEqual((meta['ein'],meta['identifier']),('541517707','SL000448'))
                    self.assertEqual(result['renewal_date'],'2025-11-17')
        finally:t.doCleanups()

    def test_70_same_core_status_identity_and_original_evidence_only_one_selected_history(self):
        for n,org in enumerate(ROSTER):
            for raw in ['Current Active','Cancelled','Expired Inactive']:
                result,fields=fixture(org,n,raw);before=copy.deepcopy(result);calls=[]
                def collect(q):
                    calls.append(q);return dict(query=q,complete=True,fields=fields,filings=dict(url=q['url'].replace('/charities_profile/','/charities_filings/'),complete=True,rows=[dict(type='Renewal Charity',date='10/01/2026'),dict(type='Extension',date='11/01/2026')]))
                self.assertIs(enrich(c,result,collect),result)
                self.assertEqual(len(calls),1);self.assertEqual(calls[0]['history'],'selected')
                self.assertEqual(result.status,before.status);self.assertEqual(result.matched_registry_identifier,before.matched_registry_identifier)
                self.assertEqual(result.evidence_url,before.evidence_url)
                self.assertEqual({k:result._cc_license_record.get(k)for k in CORE},{k:before._cc_license_record.get(k)for k in CORE})
                self.assertEqual(str(result._cc_license_record['renewal']),'2026-10-01')
            RESULTS.append(dict(**org,passed=True,scenario='same confirmed identity/status/profile evidence; selected renewal only'))

    def test_70_unavailable_mismatched_and_uncertain_never_change_confirmed_status(self):
        for n,org in enumerate(ROSTER):
            for mode in ['incomplete','different_id','different_office','different_status','future_date','timeout']:
                result,fields=fixture(org,n);before=copy.deepcopy(result)
                def collect(q):
                    if mode=='timeout':raise TimeoutError('fixture')
                    f=dict(fields)
                    if mode=='different_id':f['Registration #']='SL999999'
                    if mode=='different_office':f['Street']='999 WRONG ROAD'
                    if mode=='different_status':f['Status']='Cancelled'
                    return dict(query=q,complete=True,fields=f,filings=dict(url=q['url'].replace('/charities_profile/','/charities_filings/'),complete=mode!='incomplete',rows=[dict(type='Renewal Charity',date='10/01/2099'if mode=='future_date'else'10/01/2026')]))
                enrich(c,result,collect)
                self.assertEqual(result.status,before.status);self.assertEqual(result.evidence_url,before.evidence_url)
                self.assertFalse(result._cc_license_record.get('renewal'))
            for change in [dict(success=False),dict(_cc_identity_review={'records':[]}),dict(state='TN'),dict(matched_registry_identifier='SLWRONG')]:
                result,_=fixture(org,n);vars(result).update(change)
                enrich(c,result,lambda q:self.fail('Unconfirmed or other state must not request selected history'))

    def test_signed_continuation_propagates_and_application_has_no_history_request(self):
        result,_=fixture(ROSTER[0])
        pending=c.NYConnectorQueryNeeded({'fixture':True})
        with self.assertRaises(c.NYConnectorQueryNeeded):enrich(c,result,lambda q:(_ for _ in ()).throw(pending))
        result._cc_license_record['identifier']=result.matched_registry_identifier='NCAPP-123'
        enrich(c,result,lambda q:self.fail('Unissued application has no renewal history'))

if __name__=='__main__':
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SelectedHistory))
    (ROOT/'testing/nc-selected-history-results.json').write_text(json.dumps(dict(passed=r.wasSuccessful(),methods=r.testsRun,cases=RESULTS,kind='70 distinct recorded organization identities / offline synthetic source conditions; no live claims'),indent=2),encoding='utf-8')
    raise SystemExit(not r.wasSuccessful())
