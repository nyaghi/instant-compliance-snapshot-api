"""Real PostgreSQL in disposable cc_test schemas. No public registry calls."""
import json,os,statistics,time,unittest,uuid
from unittest.mock import patch
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from deployment import storage_retention as r,state_snapshots as s
from deployment.durable_queue import Queue,Conflict,normalize_submission
from deployment.alerts import SCHEMA as ALERT_SCHEMA
RESULTS={}

@unittest.skipUnless(os.environ.get('CE_TEST_DATABASE_URL'),'Disposable PostgreSQL test database required')
class Tests(unittest.TestCase):
 def setUp(self):
  self.dsn=os.environ['CE_TEST_DATABASE_URL'];self.schema='cc_test_'+uuid.uuid4().hex
  with psycopg.connect(self.dsn,autocommit=True) as c:c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
  self.q=Queue(self.dsn,test_schema=self.schema);self.q.initialize('storage-test-performance-lab',{'TN':4,'IRS':4})
  with self.q.pool.connection() as c:
   c.execute(ALERT_SCHEMA);c.execute(r.SCHEMA)
   c.execute("INSERT INTO cc_alert_accounts(account) VALUES('fixture')")
   c.execute("INSERT INTO cc_alert_orgs(account,ein,name,aliases,enrolled,due) VALUES('fixture','012345678','Fixture','[]',0,0)")
  self.now=time.time();self.m=r.Maintenance(self.q.pool);self.seq=0
 def tearDown(self):
  self.q.close()
  with psycopg.connect(self.dsn,autocommit=True) as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
 def fetch(self,q,p=()):
  with self.q.pool.connection() as c:return c.execute(q,p).fetchall()
 def execute(self,q,p=()):
  with self.q.pool.connection() as c:return c.execute(q,p).rowcount
 def archive(self,age=2*r.DAY,**kw):
  self.seq+=1;identifier=f'{self.seq:064x}';meta={'captured_at':self.now-age}|kw
  self.execute('INSERT INTO cc_state_snapshots VALUES(%s,%s,%s,%s)',(identifier,Jsonb(meta),b'original-source',b'cached-pdf'));return identifier
 def workflow(self,identifier,age=20*r.DAY,active=False):
  self.execute("INSERT INTO cc_lab_workflows(id,scope,ein,fingerprint,payload,kind,mode,source_version,phase,submitted,deadline,finished) VALUES(%s,'test','012345678','hash','{}','registration','standard','fixture',%s,%s,%s,%s)",(identifier,'active' if active else 'completed',self.now-age,self.now+900,None if active else self.now-age))
 def test_70_real_sql_retention_contexts(self):
  deleted=[];retained=[]
  for i in range(70):
   mode=i%7;identifier=self.archive(age=3600 if mode==1 else 2*r.DAY,alerts_owned=mode==6);url='/state-snapshots/'+identifier+'.pdf'
   if mode==0:deleted.append(identifier)
   else:retained.append(identifier)
   if mode==2:self.execute('INSERT INTO cc_alert_artifacts VALUES(%s,%s,%s,%s)',(identifier,'alerts-'+str(i),'TN',self.now-2*r.DAY))
   if mode==3:self.execute("INSERT INTO cc_alert_confirmed VALUES('fixture','012345678',%s,'Current',%s,%s)",('S'+str(i),url,self.now))
   if mode==4:self.execute("INSERT INTO cc_alert_changes(account,ein,state,workflow,previous,status,evidence,direction,checked) VALUES('fixture','012345678',%s,%s,'Delinquent','Current',%s,'favorable',%s)",('S'+str(i),'flow'+str(i),url,self.now))
   if mode==5:self.execute("INSERT INTO cc_alert_auto_matches(account,ein,state,workflow,identifier,name,checked,previous) VALUES('fixture','012345678',%s,%s,'id','Fixture',%s,%s)",('S'+str(i),'flow'+str(i),self.now,Jsonb({'evidence':url})))
  result=self.m.batch(enroll=128,snapshots=128,jobs=0,events=0);self.assertEqual(result['deleted_snapshots'],10)
  remain={x['id'] for x in self.fetch('SELECT id FROM cc_state_snapshots')};self.assertEqual(remain,set(retained));self.assertFalse(remain&set(deleted))
  self.assertTrue(all(bytes(x['source'])==b'original-source' and bytes(x['pdf'])==b'cached-pdf' for x in self.fetch('SELECT source,pdf FROM cc_state_snapshots')))
  RESULTS['70_sql_contexts']=dict(deleted=10,retained=60,all_original_and_cached_bytes_preserved_for_controls=True)
 def test_new_ordinary_worker_archive_and_publish_keep_deadline(self):
  store=s.PostgresStore(self.q.pool,retention_enabled=True);identifier=store.save({'captured_at':self.now},b'fixture')
  row=self.fetch('SELECT discard_after FROM cc_state_snapshot_scratch WHERE id=%s',(identifier,))[0];self.assertGreater(row['discard_after'].timestamp(),self.now+86300)
  self.assertEqual(store.protect([identifier]),{identifier});self.assertEqual(len(self.fetch('SELECT id FROM cc_state_snapshot_scratch WHERE id=%s',(identifier,))),1)
  self.assertEqual(self.m.batch(jobs=0,events=0)['deleted_snapshots'],0)
 def test_alert_save_is_owned_and_exempt_from_aurora_expiry(self):
  store=s.PostgresStore(self.q.pool,alerts_owner=('alert-flow','TN'),retention_enabled=True);identifier=store.save({'captured_at':self.now-20*r.DAY},b'fixture')
  self.assertEqual(len(self.fetch('SELECT * FROM cc_alert_artifacts WHERE id=%s',(identifier,))),1);self.assertEqual(self.m.batch(jobs=0,events=0)['deleted_snapshots'],0)
 def test_active_workflow_defers_entire_batch(self):
  self.archive();self.workflow('active',active=True);self.assertEqual(self.m.batch()['deferred'],'active_check');self.assertEqual(len(self.fetch('SELECT * FROM cc_state_snapshots')),1)
 def test_quarantined_work_defers_batch(self):
  self.workflow('old');self.execute("INSERT INTO cc_lab_jobs(id,workflow_id,state,resources,weight,phase) VALUES('held','old','TN','[]',1,'quarantined')");self.archive();self.assertEqual(self.m.batch()['deferred'],'active_check')
 def test_pending_alert_reconciliation_defers_batch(self):
  self.execute("UPDATE cc_alert_orgs SET workflow='awaiting-reconcile'");self.archive();self.assertEqual(self.m.batch()['deferred'],'active_check')
 def test_invalid_missing_and_future_capture_dates_not_purged(self):
  for value in [None,'invalid',-1,self.now+10000]:
   identifier=self.archive();self.execute('UPDATE cc_state_snapshots SET metadata=%s WHERE id=%s',(Jsonb({'captured_at':value}),identifier))
  self.assertEqual(self.m.batch(jobs=0,events=0)['deleted_snapshots'],0)
 def test_batches_and_second_pass_are_bounded_and_idempotent(self):
  for i in range(129):self.archive()
  self.assertEqual(self.m.batch(enroll=128,snapshots=128,jobs=0,events=0)['deleted_snapshots'],128)
  self.assertEqual(self.m.batch(enroll=128,snapshots=128,jobs=0,events=0)['deleted_snapshots'],1)
  self.assertEqual(self.m.batch(enroll=128,snapshots=128,jobs=0,events=0)['deleted_snapshots'],0)
  state=self.m.status();self.assertEqual(state['deleted_snapshots'],129);self.assertTrue(state['last_success']);self.assertIsNone(state['last_error'])
 def test_full_source_and_cached_pdf_removed_in_same_parent_delete(self):
  identifier=self.archive();report=self.m.batch(jobs=0,events=0);self.assertEqual(report['released_logical_bytes'],len(b'original-sourcecached-pdf'));self.assertFalse(self.fetch('SELECT * FROM cc_state_snapshot_scratch WHERE id=%s',(identifier,)))
 def test_old_job_payloads_compact_but_status_and_timing_remain(self):
  for name,age in [('old',20*r.DAY),('recent',3600),('protected',20*r.DAY)]:
   self.workflow(name,age);self.execute("INSERT INTO cc_lab_jobs(id,workflow_id,state,resources,weight,phase,attempt,claimed,finished,result) VALUES(%s,%s,'TN','[]',1,'done',1,%s,%s,%s)",(name,name,self.now-age-10,self.now-age,Jsonb({'status':'Current','state':'TN','success':True,'nested':{'large':'x'*10000}})))
  self.execute("INSERT INTO cc_alert_auto_matches(account,ein,state,workflow,identifier,name,checked,previous) VALUES('fixture','012345678','TN','protected','id','Fixture',%s,'{}')",(self.now,))
  self.execute("INSERT INTO cc_lab_events(event,at,detail) VALUES('old',%s,'{}'),('recent',%s,'{}')",(self.now-20*r.DAY,self.now))
  before={x['id']:(x['claimed'],x['finished'],x['attempt']) for x in self.fetch('SELECT * FROM cc_lab_jobs')}
  result=self.m.batch(snapshots=0,enroll=0);self.assertEqual(result['trimmed_jobs'],1);self.assertEqual(result['deleted_events'],1)
  rows={x['id']:x for x in self.fetch('SELECT * FROM cc_lab_jobs')};self.assertEqual(rows['old']['result']['status'],'Current');self.assertNotIn('nested',rows['old']['result']);self.assertIn('nested',rows['recent']['result']);self.assertIn('nested',rows['protected']['result'])
  self.assertEqual(before,{x['id']:(x['claimed'],x['finished'],x['attempt']) for x in rows.values()})
  self.assertEqual(self.m.batch(snapshots=0,enroll=0)['trimmed_jobs'],0)
 def test_maintenance_admission_blocks_only_during_reserved_window(self):
  with self.q.transaction() as (c,now):token=r.acquire_maintenance(c,now,queue_lock=self.q.lock)
  payload=normalize_submission({'organization_name':'Fixture Foundation','ein':'012345678','states':['TN']},['TN'])
  with self.assertRaises(Conflict):self.q.submit('fixture','key',payload,'storage-test-performance-lab')
  with self.q.pool.connection() as c:r.release_maintenance(c,'wrong-token')
  self.assertGreater(self.m.status()['busy_until'],self.now)
  self.assertEqual(self.m.batch()['deferred'],'maintenance_lease')
  with self.q.pool.connection() as c:r.release_maintenance(c,token)
  self.assertTrue(self.q.submit('fixture','key',payload,'storage-test-performance-lab')[1])
 def test_filing_documents_are_untouched(self):
  self.execute('CREATE TABLE cc_tn_extension_demo_documents(id text PRIMARY KEY,body bytea)');self.execute("INSERT INTO cc_tn_extension_demo_documents VALUES('filed',%s)",(b'immutable-filing',));self.archive();self.m.batch();self.assertEqual(bytes(self.fetch('SELECT body FROM cc_tn_extension_demo_documents')[0]['body']),b'immutable-filing')
 def test_save_latency_baseline_and_retention(self):
  baseline=s.PostgresStore(self.q.pool,retention_enabled=False);candidate=s.PostgresStore(self.q.pool,retention_enabled=True);times={'baseline':[],'candidate':[]}
  for i in range(40):
   for label,store in [('baseline',baseline),('candidate',candidate)]:
    started=time.perf_counter();store.save({'captured_at':self.now},b'small-test-source');times[label].append(1000*(time.perf_counter()-started))
  RESULTS['save_latency_ms']={key:{'median':round(statistics.median(values),3),'p95':round(sorted(values)[37],3)} for key,values in times.items()}
  self.assertLess(RESULTS['save_latency_ms']['candidate']['p95'],100)
if __name__=='__main__':unittest.main()
