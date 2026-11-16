import copy,json,socket,time,threading,unittest
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as c

P=Path(__file__).parent/'fixtures/fresh-five'
BOSTON=json.loads((P/'NC-BOSTON-PUBLIC.json').read_text())
CASES=json.loads((P/'LOCAL-70.json').read_text())

class NCIdentityReuse(unittest.TestCase):
    def replay(self,legacy=False,fail=False):
        record=copy.deepcopy(BOSTON);record['issued']=time.time();record['expires']=time.time()+60
        calls=[];active=0;peak=0;lock=threading.Lock()
        def fetch(url,*args,**kwargs):
            nonlocal active,peak
            with lock: calls.append(url);active+=1;peak=max(peak,active)
            try:
                time.sleep(.025)
                if fail:raise TimeoutError('simulated source timeout')
                return b'[]'
            finally:
                with lock:active-=1
        token=c.REVIEWED_NAME_CONTEXT.set({record['ein']:record['alternate_names']})
        try:
            with patch.object(c,'trial_identity',return_value=True),patch.object(c,'public_profile_for_ein',return_value={}),patch.object(c,'identity_fetch',side_effect=fetch),patch.object(socket.socket,'connect',side_effect=AssertionError('offline test')):
                if legacy:
                    with patch.object(c,'nc_prepare_foreign_evidence'),patch.object(c,'nc_connector_foreign_ein',side_effect=lambda o,r,d:c.licensed_charity_foreign_ein(o,r,d,exact_name=True)):
                        result=c.final_four_connector_advance(record)
                else:result=c.final_four_connector_advance(record)
                first=len(calls)
                if not legacy:
                    again=c.final_four_connector_advance(record)
                    self.assertEqual(again['result']['matched_registry_identifier'],result['result']['matched_registry_identifier'])
                    self.assertEqual(len(calls),first)
        finally:c.REVIEWED_NAME_CONTEXT.reset(token)
        return result,calls,peak

    def test_saved_public_case_same_result_without_duplicate_reads(self):
        before,bq,_=self.replay(True);after,aq,peak=self.replay()
        for field in ('status','matched_registry_identifier','matched_registry_name','confirmation_required'):
            self.assertEqual(before['result'][field],after['result'][field])
        self.assertEqual(after['result']['matched_registry_identifier'],'SL017506')
        self.assertEqual(len(bq),24);self.assertEqual(len(aq),8)
        self.assertEqual(len(aq),len(set(aq)));self.assertGreater(peak,1);self.assertLessEqual(peak,3)

    def test_unavailable_corroboration_is_not_fabricated_or_retried(self):
        before,_,_=self.replay(True,True);after,calls,_=self.replay(False,True)
        self.assertEqual(before['result']['status'],after['result']['status'])
        self.assertEqual(before['result']['matched_registry_identifier'],after['result']['matched_registry_identifier'])
        self.assertEqual(len(calls),8)

    def test_seventy_exact_and_conflicting_ein_candidates(self):
        self.assertEqual(len(CASES),70)
        with patch.object(c,'reconciled_registry_address',return_value={'decision':'corroborated'}),patch.object(c,'trial_identity',return_value=True),patch.object(c,'identity_fetch',side_effect=AssertionError('no foreign query required')):
            for case in CASES:
                with self.subTest(org=case['name']):
                    org=c.checker.Organization(case['name'],case['ein'])
                    rows=[{'name':case['name'],'identifier':'SL001','ein':case['ein'],'status':'Current','raw_status':'Current Active','location':'Boston, MA'},
                          {'name':case['name'],'identifier':'SL002','ein':'999999999','status':'Current','raw_status':'Current Active','location':'Boston, MA'}]
                    before=c.select_licensed_charity(org,copy.deepcopy(rows),'NC',time.monotonic()+10)
                    token=c.NC_FOREIGN_EIN_CONTEXT.set({'checks':{},'pending':None})
                    try:after=c.select_licensed_charity(org,copy.deepcopy(rows),'NC',time.monotonic()+10)
                    finally:c.NC_FOREIGN_EIN_CONTEXT.reset(token)
                    self.assertEqual(before[0]['identifier'],after[0]['identifier']);self.assertEqual(after[0]['identifier'],'SL001')
                    self.assertEqual(before[1],after[1])

    def test_cache_bound_to_exact_identity_and_not_shared_between_checks(self):
        org=c.checker.Organization('Hospital','123456789')
        row={'name':'Hospital Foundation','identifier':'SL001','street':'123 Main St','postal_code':'12345','region':'MA'}
        token=c.NC_FOREIGN_EIN_CONTEXT.set({'checks':{},'pending':{}})
        try:
            for item in [row,dict(row,name='Other'),dict(row,identifier='SL002'),dict(row,street='124 Main St'),dict(row,postal_code='23456'),dict(row,region='NY')]:
                with self.assertRaises(c.NCForeignEvidencePending):c.nc_connector_foreign_ein(org,item,time.monotonic()+10)
            self.assertEqual(len(c.NC_FOREIGN_EIN_CONTEXT.get()['pending']),6)
            with self.assertRaises(c.NCForeignEvidencePending):c.nc_connector_foreign_ein(c.checker.Organization('Hospital','987654321'),row,time.monotonic()+10)
            self.assertEqual(len(c.NC_FOREIGN_EIN_CONTEXT.get()['pending']),7)
        finally:c.NC_FOREIGN_EIN_CONTEXT.reset(token)
        self.assertIsNone(c.NC_FOREIGN_EIN_CONTEXT.get())

    def test_deadline_prevents_additional_reads(self):
        token=c.NC_FOREIGN_EIN_CONTEXT.set({'checks':{},'pending':None})
        try:
            with self.assertRaises(TimeoutError),patch.object(c,'licensed_charity_identity',side_effect=AssertionError('no read after deadline')):
                c.nc_prepare_foreign_evidence(c.checker.Organization('Hospital','123456789'),[{}],time.monotonic()-1)
        finally:c.NC_FOREIGN_EIN_CONTEXT.reset(token)

if __name__=='__main__':unittest.main()
