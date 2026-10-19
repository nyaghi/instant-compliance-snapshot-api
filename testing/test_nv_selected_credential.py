"""Signed local source-context controls; never submit real identity decisions."""
import ast,copy,json,socket,subprocess,sys,unittest
from pathlib import Path
from datetime import date
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import registry_snapshot_server as c
COHORT=json.loads((ROOT/'testing/fixtures/oct19-cohort.json').read_text())[:30]
GC=subprocess.check_output(['git','show','c511aede52579f0e82b953e113fd7165d918205f:registry_snapshot_server.py'],cwd=ROOT,text=True,encoding='utf-8')
node=next(n for n in ast.parse(GC).body if isinstance(n,ast.FunctionDef) and n.name=='resolve_identity_review')
scope=dict(c.__dict__);exec(compile(ast.Module(body=[node],type_ignores=[]),'<exact-GC-resolver>','exec'),scope);BASELINE=scope['resolve_identity_review']
class Selection(unittest.TestCase):
 def setUp(self):
  for key,value in [('APP_VERSION','local-nv-selection-staging'),('NY_CONNECTOR_SIGNING_KEY','LOCAL-ONLY-KEY-'*8)]:
   p=patch.object(c,key,value);p.start();self.addCleanup(p.stop)
  for key,value in [('known_names_for_ein',[]),('performance_origin_enabled',False),('log_event',None)]:
   p=patch.object(c,key,return_value=value);p.start();self.addCleanup(p.stop)
  p=patch.object(socket,'create_connection',side_effect=AssertionError('No source requests in local replay'));p.start();self.addCleanup(p.stop)
 def initial(self,org=COHORT[0],state='NV',pending_extra=False):
  heart=dict(name=org['name'],identifier='NV19981324771',url='https://orion.nv.gov/heart',ein='',status='Current',raw_status='Active',expiration=date(2027,9,30),_identity_outcome='accepted',evidence_url='/state-snapshots/'+'a'*64+'.pdf')
  stroke=dict(name='AMERICAN STROKE ASSOCIATION',identifier='NV19951158753',url='https://orion.nv.gov/stroke',ein='',status='Revoked',raw_status='Permanently Revoked',expiration=date(1996,11,30),_identity_outcome='possible',evidence_url='/state-snapshots/'+'b'*64+'.pdf')
  rows=[heart,stroke]
  if pending_extra:rows.append({**stroke,'name':'ANOTHER PLAUSIBLE REGISTRATION','identifier':'NV99999999','url':'https://orion.nv.gov/third'})
  data=dict(organization_name=org['name'],ein=org['ein'],state=state,status='Needs Review',success=False,comments='LOCAL fixture',reviewed_alternate_names=[stroke['name']])
  c.attach_identity_review(data,dict(records=rows,search_complete=True));return data
 def action(self,data,action='accept',identifier='NV19951158753',resolver=None,**changes):
  candidate=next(r for r in data['identity_review']['candidates'] if r['identifier']==identifier)
  payload=dict(token=data['identity_review']['token'],candidate_id=candidate['id'],ein=data['ein'],state=data['state'],action=action);payload.update(changes)
  return (resolver or c.resolve_identity_review)(payload,'reviewer@example.test','local-device')
 def test_actual_heart_stroke_retained_fields_baseline_reproduces_candidate_binds(self):
  org=dict(name='American Heart Association Inc.',ein='135613797');initial=self.initial(org)
  old=self.action(initial,resolver=BASELINE);self.assertEqual(old['matched_registry_identifier'],'NV19981324771');self.assertEqual(old['status'],'Current')
  new=self.action(initial);self.assertEqual(new['matched_registry_identifier'],'NV19951158753');self.assertEqual(new['status'],'Revoked');self.assertEqual(new['raw_status_text'],'Permanently Revoked');self.assertEqual(new['evidence_url'],'/state-snapshots/'+'b'*64+'.pdf')
  self.assertEqual(new['identity_review_history'][0]['identifier'],'NV19951158753')
 def test_thirty_contexts_accept_reject_undo_keep_exact_status_id_and_evidence(self):
  for org in COHORT:
   initial=self.initial(org);out=self.action(initial)
   self.assertEqual(out['status'],'Revoked');self.assertEqual(out['matched_registry_identifier'],'NV19951158753');self.assertTrue(out['evidence_url'].endswith('b'*64+'.pdf'))
   undo=self.action(out,'clear');self.assertEqual(undo['status'],'Unable to Confirm');self.assertEqual(undo['evidence_url'],'')
   reject=self.action(out,'reject');self.assertEqual(reject['status'],'Current');self.assertEqual(reject['matched_registry_identifier'],'NV19981324771')
 def test_other_pending_choices_do_not_replace_explicit_nevada_selection(self):
  out=self.action(self.initial(pending_extra=True));self.assertEqual(out['status'],'Revoked');self.assertEqual(len(out['identity_review']['candidates']),2)
  undo=self.action(out,'clear');self.assertEqual(undo['status'],'Unable to Confirm')
 def test_last_explicit_accept_then_undo_restores_prior_choice(self):
  initial=self.initial(pending_extra=True);first=self.action(initial)
  second=self.action(first,identifier='NV99999999');self.assertEqual(second['matched_registry_identifier'],'NV99999999')
  undone=self.action(second,'clear',identifier='NV99999999');self.assertEqual(undone['matched_registry_identifier'],'NV19951158753')
 def test_other_states_have_identical_signed_results_for_thirty_contexts(self):
  for org in COHORT:
   for state in ['AL','NC','TN','DC']:
    initial=self.initial(org,state=state)
    old=self.action(initial,resolver=BASELINE);new=self.action(initial)
    for k in ['status','matched_registry_identifier','matched_registry_name','raw_status_text','evidence_url']:self.assertEqual(new.get(k),old.get(k),(org['ein'],state,k))
 def test_binding_expiry_and_unsigned_status_guards(self):
  initial=self.initial();out=self.action(initial,status='Current',interpreted_status='Current');self.assertEqual(out['status'],'Revoked')
  for changes in [dict(ein='999999999'),dict(state='PA'),dict(token=initial['identity_review']['token']+'x')]:
   with self.assertRaises(ValueError):self.action(initial,**changes)
  record=c.identity_review_unpack(initial['identity_review']['token'],'reviewer@example.test','local-device');record['expires']=record['issued']-1;initial['identity_review']=c.identity_review_view(record)
  with self.assertRaises(ValueError):self.action(initial)
if __name__=='__main__':unittest.main(verbosity=2)
