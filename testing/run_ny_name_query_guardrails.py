"""NY apostrophe-rejected search controls; identity and failures stay conservative."""
import sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class NYNameQueryTests(unittest.TestCase):
 def response(self,data,status=200):
  r=Mock(status_code=status);r.json.return_value={'success':True,'statusCode':200,'data':data}
  if status!=200:r.raise_for_status.side_effect=RuntimeError('HTTP '+str(status))
  return r
 def run_lookup(self,name,queries,rows=None,fail_on=None,ein='872999231'):
  calls=[];session=Mock();session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False)
  detail={'orgName':name,'ein':ein,'orgID':'10-20-30','regType':'NFP','regStatute':'EXEMPT','documents':{}}
  session.get.return_value=self.response(detail)
  def provider(query):
   calls.append(dict(query));text=query.get('orgName','')
   if any(p in text for p in ["'",'\u2019','\u2018','\u02bc','\uff07']) or (fail_on and fail_on(query)):
    return self.response(None,400)
   return self.response(rows if text and rows is not None else [])
  org=c.checker.Organization(name,ein)
  with patch.object(c.curl_requests,'Session',return_value=session),patch.object(c,'build_search_queries',return_value=queries),patch.object(c,'public_profile_for_ein',return_value={}):
   result=c.search_ny_direct(org,registry_search_provider=provider)
  self.assertEqual(org.organization_name,name)
  return result,calls,session
 def test_apostrophe_variants_finish_without_submitting_rejected_punctuation(self):
  for punctuation in ["'",'\u2019','\u2018','\u02bc','\uff07']:
   name=f'American Farrier{punctuation}s Association Foundation Inc.'
   r,calls,_=self.run_lookup(name,['American Farrier','American Farriers Association Foundation Inc.',name,'American Farrier s'])
   self.assertEqual(c.public_status(r),'Not Registered')
   self.assertEqual(calls,[{'ein':'872999231'},{'orgName':'American Farrier'},{'orgName':'American Farriers Association Foundation Inc.'},{'orgName':'American Farrier s'}])
 def test_original_identity_retained_for_punctuation_name_match(self):
  name="O'Connell Arts Foundation";row={'orgName':name,'ein':'','orgID':'10-20-30'}
  r,calls,_=self.run_lookup(name,[name],[row],ein='')
  self.assertEqual(r.status,'Exempt');self.assertEqual(r.matched_registry_name,name)
  self.assertEqual(calls,[{'orgName':'OConnell Arts Foundation'}])
 def test_related_association_does_not_become_foundation(self):
  name="Farrier's Association Foundation";row={'orgName':'Farriers Association','ein':'','orgID':'99-99-99'}
  r,_,session=self.run_lookup(name,[name],[row],ein='')
  self.assertNotIn(r.status,['Current','Upcoming Filing','Exempt']);session.get.assert_not_called()
 def test_conflicting_ein_is_not_accepted_after_query_normalization(self):
  name="Farrier's Association Foundation";row={'orgName':name,'ein':'999999999','orgID':'99-99-99'}
  r,_,session=self.run_lookup(name,[name],[row])
  self.assertNotIn(r.status,['Current','Upcoming Filing','Exempt']);session.get.assert_not_called()
 def test_unpunctuated_queries_and_ein_priority_are_unchanged(self):
  names=['Example National Foundation','Example National','Example']
  r,calls,_=self.run_lookup(names[0],names)
  self.assertEqual(c.public_status(r),'Not Registered')
  self.assertEqual(calls,[{'ein':'872999231'}]+[{'orgName':n} for n in names])
 def test_other_search_failure_after_completed_empty_response_stays_inconclusive(self):
  r,calls,_=self.run_lookup("Farrier's Foundation",["Farrier's Foundation"],fail_on=lambda q:'orgName' in q)
  self.assertEqual(r.status,'Unable to Confirm');self.assertFalse(r.success)
  self.assertEqual(calls,[{'ein':'872999231'},{'orgName':'Farriers Foundation'}])

if __name__=='__main__':unittest.main(verbosity=2)
