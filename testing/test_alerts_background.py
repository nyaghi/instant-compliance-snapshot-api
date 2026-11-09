from types import SimpleNamespace
from unittest import TestCase
from testing import test_alerts_pilot as fixtures

from deployment.alerts_browser import SCHEMA, claim, enable, lease, merge, retain
from deployment.alerts_matches import correct
from testing.test_alerts_pilot import ACCOUNT, OTHER, EIN, NOW, URL, run


class AlertsBackgroundTests(TestCase):
    setUp = fixtures.AlertsTests.setUp
    check = fixtures.AlertsTests.check

    def test_browser_claim_is_account_bound_and_never_queues_browser_states_on_server(self):
        self.c.db.executescript(SCHEMA)
        self.a.states=frozenset(('CO','AL'))
        profile=enable(self.a,self.c,ACCOUNT)['profile']
        with self.assertRaises(ValueError):
            claim(self.a,self.c,OTHER,profile)
        job=claim(self.a,self.c,ACCOUNT,profile)
        self.assertEqual(job['states'],['AL'])
        self.assertEqual(self.q.submissions[0][2]['states'],['CO'])
        self.assertIsNone(lease(self.a,self.c,OTHER,job['lease']))
        owned=lease(self.a,self.c,ACCOUNT,job['lease'])
        self.assertIsNotNone(owned)
        self.assertTrue(claim(self.a,self.c,ACCOUNT,profile)['retry'])
        base=run('scheduled',NOW,'Current')
        self.assertIsNone(merge(self.a,self.c,base))
        retain(self.a,owned,'AL',{**base['jobs'][0]['result'],'state':'AL'})
        self.c.execute('UPDATE cc_alert_browser_runs SET finished=true')
        combined=merge(self.a,self.c,base)
        self.assertEqual([job['state'] for job in combined['jobs']],['CO','AL'])
        self.assertEqual(combined['jobs'][1]['result']['status'],'Current')
        self.assertIsNone(lease(self.a,self.c,ACCOUNT,job['lease']))

    def test_browser_expiry_preserves_existing_confirmed_status(self):
        self.c.db.executescript(SCHEMA)
        self.a.states=frozenset(('CO','AL'))
        profile=enable(self.a,self.c,ACCOUNT)['profile']
        job=claim(self.a,self.c,ACCOUNT,profile)
        self.assertIsNotNone(job['lease'])
        base=run('scheduled',NOW,'Current')
        self.a.clock+=450
        combined=merge(self.a,self.c,base)
        self.a.apply(self.c,self.org,combined)
        data=self.a.dashboard(self.c,ACCOUNT,2**63-1)
        self.assertEqual(data['unseen'],0)
        self.assertEqual([row['state'] for row in data['failures']],['AL'])

    def test_exact_signed_match_can_be_corrected_and_is_not_reaccepted(self):
        record={'base':{'state':'CO','ein':EIN},'records':[
            {'ein':EIN,'id':'candidate','identifier':'license','name':'Example Organization',
             'reviewable':True,'evidence_url':URL}]}
        self.a.master=SimpleNamespace(canonical_ein_digits=lambda s:s.replace('-',''),
            identity_review_unpack=lambda *a:record,
            resolve_identity_review=lambda *a:{**run('resolve',NOW,'Delinquent')['jobs'][0]['result'],
                'matched_registry_identifier':'license'})
        self.check('base',0,'Current')
        data=self.check('auto',1,'Needs Review',identity_review={'token':'signed'})
        self.assertEqual(data['matches'][0]['identifier'],'license')
        self.assertTrue(data['changes'][0]['automatic'])
        self.assertEqual(data['unseen'],1)
        choice={'ein':EIN,'state':'CO','workflow':'auto','identifier':'license'}
        self.assertFalse(correct(self.a,self.c,OTHER,choice))
        self.assertTrue(correct(self.a,self.c,ACCOUNT,choice))
        data=self.a.dashboard(self.c,ACCOUNT,2**63-1)
        self.assertTrue(data['changes'][0]['corrected'])
        self.assertEqual(data['unseen'],0)
        after=self.check('later',2,'Delinquent',matched_registry_identifier='license')
        self.assertEqual(after['unseen'],0)
        self.assertEqual(self.c.execute('SELECT status FROM cc_alert_confirmed WHERE account=%s',
                         (ACCOUNT,)).fetchone()['status'],'Current')
        self.assertEqual(after['matches'],[])

    def test_sole_signed_match_without_ein_or_snapshot_records_what_was_accepted(self):
        selected={'ein':'','id':'candidate','identifier':'state-license','name':'Registry Name',
                  'reviewable':True}
        record={'base':{'state':'CO','ein':EIN},'records':[selected]}
        decisions=[]
        def resolve(payload, *_):
            decisions.append(payload)
            return {**run('resolved',NOW,'Delinquent',evidence_url='')['jobs'][0]['result'],
                    'matched_registry_identifier':'state-license'}
        self.a.master=SimpleNamespace(canonical_ein_digits=lambda s:s,
            identity_review_unpack=lambda *a:record,resolve_identity_review=resolve)
        self.check('baseline',0,'Current',evidence_url='')
        dashboard=self.check('auto',1,'Needs Review',evidence_url='',identity_review={'token':'signed'})
        self.assertEqual((decisions[0]['action'],decisions[0]['candidate_id']),('accept','candidate'))
        match,=dashboard['matches']
        self.assertEqual((match['name'],match['identifier'],match['has_evidence']),
                         ('Registry Name','state-license',False))
        change,=dashboard['changes']
        self.assertEqual((change['match_name'],change['match_identifier']),('Registry Name','state-license'))
        record['records'].append({**selected,'identifier':'another','id':'other'})
        self.check('competing',2,'Needs Review',identity_review={'token':'signed'})
        self.assertEqual(len(decisions),1)

    def test_conflicting_candidate_stays_unconfirmed(self):
        self.a.master=SimpleNamespace(canonical_ein_digits=lambda s:s,
            identity_review_unpack=lambda *a:{'base':{'state':'CO','ein':EIN},
                'records':[{'ein':'876543210','reviewable':True,'evidence_url':URL}]})
        data=self.check('conflicting',0,'Needs Review',identity_review={'token':'signed'})
        self.assertEqual(data['matches'],[])
        self.assertEqual(data['unseen'],0)
        self.assertEqual(data['organizations'][0]['confirmed'],0)
