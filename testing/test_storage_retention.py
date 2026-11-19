"""Offline retention guards; real PostgreSQL contracts live in the companion test."""
import copy,inspect,os,time,unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
from deployment import storage_retention as r,state_snapshots as s

class Result:
 def __init__(self,rows=(),rowcount=1):self.rows=rows;self.rowcount=rowcount
 def fetchone(self):return self.rows[0] if self.rows else None
 def fetchall(self):return list(self.rows)
class Fake:
 def __init__(self):self.calls=[]
 def execute(self,q,p=()):
  self.calls.append((q,p))
  if q.startswith('SELECT id FROM'):return Result([{'id':'a'*64}])
  return Result()
class Pool:
 def __init__(self):self.c=Fake()
 @contextmanager
 def connection(self,**kw):yield self.c
class Tests(unittest.TestCase):
 def test_70_expiry_inputs(self):
  now=1800000000
  for i in range(70):
   stamp=now-(i+1)*3600
   self.assertEqual(r.expiry_at({'captured_at':stamp},now),stamp+r.DAY)
  for stamp in [None,'old',True,0,-1,now+61,float('nan'),float('inf')]:self.assertEqual(r.expiry_at({'captured_at':stamp},now),now+r.DAY)
 def test_ordinary_and_provisional_both_receive_expiry_on_staging(self):
  pool=Pool();meta={};raw=b'fixture'
  store=s.PostgresStore(pool,retention_enabled=True)
  for provisional in [True,False]:
   store.save(meta,raw,provisional=provisional);q,args=pool.c.calls[-1];self.assertIn('cc_state_snapshot_scratch',q);self.assertIn("interval '1 day'",q)
 def test_worker_constructor_enables_staging_retention_without_provisional_flag(self):
  with patch.dict(os.environ,{'CE_PERMANENT_STAGING':'1'}):self.assertTrue(s.PostgresStore(Pool()).retention_enabled)
  with patch.dict(os.environ,{'CE_PERMANENT_STAGING':'0'}):self.assertFalse(s.PostgresStore(Pool()).retention_enabled)
 def test_alert_owned_save_is_separate(self):
  p=Pool();store=s.PostgresStore(p,retention_enabled=True,alerts_owner=('test-flow','TN'));store.save({},b'x')
  q,_=p.c.calls[-1];self.assertIn('cc_alert_artifacts',q);self.assertNotIn('cc_state_snapshot_scratch',q)
 def test_publish_retains_expiry_ledger(self):
  p=Pool();store=s.PostgresStore(p,retention_enabled=True);self.assertEqual(store.protect(['a'*64]),{'a'*64})
  queries=[q for q,_ in p.c.calls];self.assertTrue(any('UPDATE cc_state_snapshot_scratch' in q for q in queries));self.assertFalse(any('DELETE' in q for q in queries))
 def test_production_save_path_unchanged(self):
  p=Pool();store=s.PostgresStore(p,retention_enabled=False);store.save({},b'x');self.assertNotIn('scratch',p.c.calls[-1][0])
 def test_compaction_retains_status_and_timing_is_not_touched(self):
  original={'state':'TN','status':'Current','success':True,'comments':'x'*1200,'nested_evidence':{'content':'x'*10000},'identity_review':{'candidates':['large']},'source_url':'https://example.org'};before=copy.deepcopy(original)
  result=r.compact_result(original);self.assertEqual(result['status'],'Current');self.assertTrue(result['success']);self.assertEqual(len(result['comments']),600);self.assertNotIn('nested_evidence',result);self.assertEqual(original,before)
 def test_bounded_inputs(self):
  m=r.Maintenance(Pool())
  for x in [-1,1025,True,1.5]:
   with self.assertRaises(ValueError):m.batch(snapshots=x)
 def test_no_filing_tables_in_cleanup_sql(self):
  source=inspect.getsource(r)
  self.assertNotIn('DELETE FROM cc_tn_extension',source);self.assertNotIn('UPDATE cc_tn_extension',source)
  self.assertIn('cc_alert_confirmed',source);self.assertIn('cc_alert_changes',source);self.assertIn('cc_alert_auto_matches',source)
  self.assertIn('SKIP LOCKED',source);self.assertIn("statement_timeout='1500ms'",source)
if __name__=='__main__':unittest.main()
