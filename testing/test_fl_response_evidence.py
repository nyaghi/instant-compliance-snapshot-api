"""Private retained-source bindings and unchanged public result formatting."""
import ast,copy,hashlib,time,unittest
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as master
from deployment import fl_response_evidence as fl,state_snapshots as ss
from testing.capacity_lab.test_fl_business_lookup import source,card


class RetainedFloridaResponse(unittest.TestCase):
    def subject(self,index=0):
        name='Example Relief '+str(index);ein=str(100000000+index);identifier='CH'+str(50000+index)
        run=ss.CaptureRun(name,ein,'FL')
        raw=master.checker.StateResult(name,ein[:2]+'-'+ein[2:],'FL','Current',fl.URL)
        body=source(card(name=name,identifier=identifier))
        row=master.fl_business_candidate_rows(body)[0]
        raw.success=True;raw.matched_registry_name=name;raw.matched_registry_identifier=identifier
        raw.raw_status_text='Expiration Date 12/31/2027'
        raw._cc_registration_date_evidence=row['business_evidence'];raw._cc_fl_business_source_verified=True
        master.PUBLIC_PROFILE_CACHE[ein]={}
        inline={key:getattr(raw,key)for key in fl.FIELDS[:6]};inline['status']=master.public_status(raw)
        return run,raw,body,inline

    def test_thirty_identity_contexts_reject_changed_capture_and_archive_bindings(self):
        count=0
        for index in range(30):
            with self.subTest(identity=index):
                run,raw,body,inline=self.subject(index);token=ss.CURRENT.set(run)
                try:
                    self.assertTrue(fl.remember_response(master,body,run.name))
                    self.assertTrue(fl.bind_lookup(master,raw));self.assertIsNotNone(fl.capture_bound(run,inline))
                    for key,value in [('state','GA'),('ein','99-9999999'),('success',False),('source_url',fl.URL+'?other=1'),
                                      ('matched_registry_name','Another Relief'),('matched_registry_identifier','CH999999'),('status','Delinquent')]:
                        changed={**inline,key:value};self.assertIsNone(fl.capture_bound(run,changed));count+=1
                    proof=copy.deepcopy(run.fl_response_proof)
                    run.fl_response_proof['run_id']='0'*32;self.assertIsNone(fl.capture_bound(run,inline));count+=1
                    run.fl_response_proof=copy.deepcopy(proof);run.fl_response_proof['html']+=' '
                    self.assertIsNone(fl.capture_bound(run,inline));count+=1
                    run.fl_response_proof=copy.deepcopy(proof)
                    with patch.object(master,'fl_business_lookup_enabled',return_value=True):
                        data=master.response_data_for_lookup(raw,raw.raw_status_text,master.checker.Organization(run.name,raw.ein),run.name,raw.ein,'FL',time.perf_counter())
                    self.assertEqual(run.fl_response_proof['public_binding'],fl.binding(data))
                    self.assertFalse(fl.seal_public_result(raw,data));count+=1
                    image=b'guard fixture bytes';run.fl_response_images={hashlib.sha256(image).hexdigest():(proof['sha256'],proof['lookup_binding'])}
                    self.assertTrue(fl.image_bound(run,data,fl.URL,image,'image'))
                    for key,value in [('state','GA'),('ein','99-9999999'),('success',False),('source_url',fl.URL+'?other=1'),
                                      ('matched_registry_name','Another Relief'),('matched_registry_identifier','CH999999'),
                                      ('status','Delinquent'),('raw_status_text','changed')]:
                        self.assertFalse(fl.image_bound(run,{**data,key:value},fl.URL,image,'image'));count+=1
                    self.assertFalse(fl.image_bound(run,data,fl.URL,image+b'x','image'));count+=1
                    self.assertFalse(fl.image_bound(run,data,fl.URL,image,'source_pdf'));count+=1
                    self.assertFalse(fl.remember_response(master,body,run.name+' other'));self.assertIsNone(run.fl_response_proof);count+=1
                finally:ss.CURRENT.reset(token)
        self.assertEqual(count,630)

    def test_missing_unverified_duplicate_and_other_state_responses_are_refused(self):
        for index in range(30):
            run,raw,body,inline=self.subject(index);token=ss.CURRENT.set(run)
            try:
                self.assertFalse(fl.remember_response(master,body[:-7],run.name))
                self.assertTrue(fl.remember_response(master,body,run.name))
                duplicate=source(card(name=run.name,identifier=raw.matched_registry_identifier,index=0)
                                 +card(name=run.name,identifier=raw.matched_registry_identifier,index=1),count=2)
                self.assertTrue(fl.remember_response(master,duplicate,run.name));self.assertFalse(fl.bind_lookup(master,raw))
                self.assertTrue(fl.remember_response(master,body,run.name))
                raw._cc_fl_business_source_verified=False;self.assertFalse(fl.bind_lookup(master,raw))
                raw._cc_fl_business_source_verified=True;raw._cc_registration_date_evidence={};self.assertFalse(fl.bind_lookup(master,raw))
                for state in ['GA','NY','CO','WI','NC','TN','MS','IL']:
                    run.state=state;self.assertFalse(fl.remember_response(master,body,run.name));self.assertIsNone(fl.capture_bound(run,inline))
                run.state='FL'
            finally:ss.CURRENT.reset(token)

    def test_public_serializer_output_is_identical_with_or_without_retention(self):
        for index in range(30):
            run,raw,body,inline=self.subject(index);token=ss.CURRENT.set(run)
            try:
                with patch.object(master,'fl_business_lookup_enabled',return_value=True),patch.object(master.time,'time',return_value=1793440000),patch.object(master.time,'perf_counter',return_value=1000):
                    without=master.response_data_for_lookup(raw,raw.raw_status_text,master.checker.Organization(run.name,raw.ein),run.name,raw.ein,'FL',1000)
                    self.assertTrue(fl.remember_response(master,body,run.name));self.assertTrue(fl.bind_lookup(master,raw))
                    retained=master.response_data_for_lookup(raw,raw.raw_status_text,master.checker.Organization(run.name,raw.ein),run.name,raw.ein,'FL',1000)
                self.assertEqual(without,retained)
                self.assertNotIn('html',retained);self.assertNotIn('fl_response_proof',retained)
            finally:ss.CURRENT.reset(token)


if __name__=='__main__':unittest.main()
