"""The actual public serializer must hand off the exact selected source proof."""
import copy,time,unittest
from unittest.mock import patch
from datetime import date,timedelta
from pathlib import Path
import registry_snapshot_server as master
from deployment import state_snapshots as snapshots,co_dataset_evidence as evidence

class DatasetSerialization(unittest.TestCase):
    def setUp(self):
        guard=patch.object(master.urllib.request,'urlopen',side_effect=AssertionError('No external HTTP in serialization fixture'))
        guard.start();self.addCleanup(guard.stop)

    def fixture(self,name='Man in the Mirror, Inc.',ein='593178628'):
        # Explicitly empty profile fixture: this tests CO source serialization,
        # never a live public-profile fallback for these modeled identities.
        master.PUBLIC_PROFILE_CACHE[ein]={}
        source_url=("https://data.colorado.gov/resource/37wu-kn3g.json?%24limit=10&%24where=fein%3D%27"
                    +ein[:2]+'-'+ein[2:]+"%27&%24order=registrationapproveddate+DESC")
        due=date.today()+timedelta(days=30)
        row={'name':name.upper(),'fein':ein[:2]+'-'+ein[2:],'entityid':'20023003254',
             'currentstatus':'GOOD','expirationdate':due.isoformat()+'T00:00:00.000'}
        result=master.checker.StateResult(name,row['fein'],'CO',master.checker.status_from_due_date(due),source_url)
        result.matched_registry_name=row['name'];result.matched_registry_identifier=row['entityid']
        result.raw_status_text='Current Status: GOOD | Expiration Date: '+due.strftime('%m/%d/%Y')
        result.success=True
        return result,master.checker.Organization(name,ein),row,snapshots.CaptureRun(name,ein,'CO')

    def serialize(self,result,org,run):
        token=snapshots.CURRENT.set(run)
        try:return master.response_data_for_lookup(result,result.raw_status_text,org,org.organization_name,org.ein,'CO',time.perf_counter())
        finally:snapshots.CURRENT.reset(token)

    def test_internal_current_binds_only_after_actual_public_upcoming_serialization(self):
        result,org,row,run=self.fixture()
        token=snapshots.CURRENT.set(run)
        try:self.assertTrue(evidence.remember_lookup(result,[row],row))
        finally:snapshots.CURRENT.reset(token)
        self.assertEqual(result.status,'Current')
        self.assertIsNone(evidence.bound_proof(run,{**vars(result),'status':'Upcoming Filing'}))
        data=self.serialize(result,org,run)
        self.assertEqual(data['status'],'Upcoming Filing')
        self.assertIsNotNone(evidence.bound_proof(run,data))
        self.assertIsNone(evidence.bound_proof(run,{**data,'status':'Current'}))

    def test_changed_source_identity_cannot_be_resealed_by_public_serialization(self):
        for field,value in [('raw_status_text','Current Status: DIFFERENT'),('matched_registry_identifier','different'),
                            ('matched_registry_name','DIFFERENT ORGANIZATION'),('source_url','https://www.coloradosos.gov/')]:
            result,org,row,run=self.fixture();token=snapshots.CURRENT.set(run)
            try:self.assertTrue(evidence.remember_lookup(result,[row],row))
            finally:snapshots.CURRENT.reset(token)
            setattr(result,field,value)
            self.serialize(result,org,run)
            self.assertIsNone(run.co_dataset_proof['serialized_binding'])

    def test_thirty_retained_names_preserve_source_fields_through_actual_formatter(self):
        import json
        cohort=json.loads((Path(master.__file__).parent/'testing/fixtures/oct19-cohort.json').read_text())[:30]
        for item in cohort:
            ein=snapshots.digits(item['ein']);result,org,row,run=self.fixture(item['name'],ein)
            token=snapshots.CURRENT.set(run)
            try:self.assertTrue(evidence.remember_lookup(result,[row],row))
            finally:snapshots.CURRENT.reset(token)
            data=self.serialize(result,org,run)
            with self.subTest(name=item['name']):
                self.assertEqual(data['status'],'Upcoming Filing')
                self.assertIsNotNone(evidence.bound_proof(run,data))
                self.assertEqual(data['matched_registry_identifier'],row['entityid'])
                self.assertEqual(data['matched_registry_name'],row['name'])

if __name__=='__main__':unittest.main()
