"""Offline ownership controls for original Colorado dataset page images."""
import copy,hashlib,unittest
from deployment import state_snapshots as snapshots
from deployment import co_dataset_evidence as evidence

URL='https://data.colorado.gov/resource/37wu-kn3g.json?%24limit=10&%24where=fein%3D%2712-3456789%27&%24order=registrationapproveddate+DESC'

class DatasetEvidence(unittest.TestCase):
    def setUp(self):
        self.run=snapshots.CaptureRun('Example Relief','123456789','CO')
        self.rows=[{'name':'EXAMPLE RELIEF','entityid':'20023000001','fein':'12-3456789',
                    'currentstatus':'GOOD','expirationdate':'2026-11-15T00:00:00.000'}]
        self.result=dict(state='CO',ein='12-3456789',success=True,source_url=URL,
                         matched_registry_name='EXAMPLE RELIEF',matched_registry_identifier='20023000001',
                         status='Upcoming Filing',raw_status_text='Current Status: GOOD')

    def remember(self,rows=None):
        token=snapshots.CURRENT.set(self.run)
        try:return evidence.remember_lookup(self.result,self.rows if rows is None else rows,self.rows[0])
        finally:snapshots.CURRENT.reset(token)

    def test_only_exact_official_fein_dataset_url_is_accepted(self):
        self.assertEqual(evidence.dataset_ein(URL),'123456789')
        for url in [URL+'&%24limit=10',URL+'&other=1',URL+'#fragment',URL.replace('DESC','ASC'),
                    URL.replace('https:','http:'),URL.replace('37wu-kn3g','different'),
                    URL.replace('data.colorado.gov','data.colorado.gov.example.test')]:
            with self.subTest(url=url):self.assertIsNone(evidence.dataset_ein(url))

    def test_matching_complete_response_is_private_to_its_lookup(self):
        self.assertTrue(self.remember())
        self.assertIsNotNone(evidence.bound_proof(self.run,self.result))
        self.assertNotIn('co_dataset_proof',self.result)
        changed=copy.deepcopy(self.result);changed['status']='Delinquent'
        self.assertIsNone(evidence.bound_proof(self.run,changed))
        other=snapshots.CaptureRun(self.run.name,self.run.ein,'CO')
        other.co_dataset_proof=self.run.co_dataset_proof
        self.assertIsNone(evidence.bound_proof(other,self.result))

    def test_mixed_ein_or_absent_selected_row_is_not_bound(self):
        mixed=self.rows+[dict(self.rows[0],fein='98-7654321')]
        self.assertFalse(self.remember(mixed))
        self.assertFalse(self.remember([]))

    def test_only_recorded_native_image_hash_and_source_can_finish(self):
        self.assertTrue(self.remember())
        raw=b'OFFLINE IMAGE HASH OWNERSHIP FIXTURE; NOT A PUBLISHABLE IMAGE'
        proof=self.run.co_dataset_proof
        self.run.co_dataset_image_bindings={hashlib.sha256(raw).hexdigest():
            (proof['response'],proof['selected'],proof['binding'])}
        self.assertTrue(evidence.image_bound(self.run,self.result,URL,raw,'image'))
        for url,data,kind in [(URL,raw+b'changed','image'),(URL,raw,'source_text'),
                              ('https://www.coloradosos.gov/',raw,'image')]:
            self.assertFalse(evidence.image_bound(self.run,self.result,url,data,kind))

if __name__=='__main__':unittest.main()
