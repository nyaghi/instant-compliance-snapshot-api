"""Regression for WV broad discovery queries accidentally becoming identity evidence."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import registry_snapshot_server as c
import run_wv_sc_selection_guardrails as wv_controls
import run_mi_name_fallback_guardrails as mi_controls
link=mi_controls.link

class MichiganPunctuationTests(unittest.TestCase):
 flow=mi_controls.MichiganNameTests.flow
 def test_typographic_dash_is_submitted_as_ascii_without_dropping_location(self):
  for dash in ['–','—','‑','-']:
   self.org=c.checker.Organization(f'Beth Israel Deaconess Hospital {dash} Milton, Inc.','04-2103604')
   r,page,_=self.flow([],text='0 record(s) found',variants=[self.org.organization_name])
   self.assertTrue(r.success)
   self.assertEqual(r.queries_attempted,['Beth Israel Deaconess Hospital - Milton, Inc.'])
   self.assertEqual(r.organization_name,self.org.organization_name)
 def test_dash_query_keeps_matching_identity_and_location(self):
  self.org=c.checker.Organization('Beth Israel Deaconess Hospital – Milton, Inc.','04-2103604')
  wrong=link('Beth Israel Deaconess Hospital - Needham, Inc.','22209')
  r,_,_=self.flow([wrong],variants=[self.org.organization_name])
  self.assertEqual(c.public_status(r),'Not Registered');self.assertFalse(r.matched_registry_name)
 def test_typographic_apostrophe_uses_existing_canonical_punctuation(self):
  self.org=c.checker.Organization('America’s Charities','54-1517707')
  r,_,_=self.flow([link("America's Charities",'9927')],variants=[self.org.organization_name])
  self.assertEqual(r.queries_attempted,["America's Charities"])
  self.assertEqual(r.matched_registry_identifier,'9927')
 def test_full_query_stays_first_and_equivalent_dash_variants_are_deduplicated(self):
  self.org=c.checker.Organization('Beth Israel Deaconess Hospital – Milton, Inc.','04-2103604')
  r,_,_=self.flow([],text='0 record(s) found',variants=[self.org.organization_name,'Beth Israel Deaconess Hospital - Milton, Inc.','Beth Israel Deaconess'])
  self.assertEqual(r.queries_attempted,['Beth Israel Deaconess Hospital - Milton, Inc.','Beth Israel Deaconess'])

class LocationTests(unittest.TestCase):
 setUp=wv_controls.SelectionTests.setUp
 def wv(self,records,name="Comic Relief, Inc.",detail_name=None):
  # The existing harness fixes the query to the name passed. Force the actual
  # broad-query input while retaining each original organization's safe targets.
  with patch.object(c,"wv_preferred_query_variants",return_value=["Beth Israel Deaconess"]):
   return self.broad_flow(records,name,detail_name)
 def broad_flow(self,records,name,detail_name):
  from unittest.mock import Mock
  page=Mock(); selected=[];rows=[]
  for identifier,registry_name,status in records:
   row=Mock();cells=[Mock() for _ in range(5)]
   for cell,value in zip(cells,[identifier,registry_name,"Address","Charity",status]):cell.inner_text.return_value=value
   cell_list=Mock();cell_list.count.return_value=5;cell_list.nth.side_effect=cells.__getitem__
   link=Mock();link.first.click.side_effect=lambda *a,r=(identifier,registry_name,status),**k:selected.append(r)
   row.locator.side_effect=lambda selector,cl=cell_list,li=link:cl if selector=="td" else li
   rows.append(row)
  row_list=Mock();row_list.count.return_value=len(rows);row_list.nth.side_effect=rows.__getitem__
  page.locator.side_effect=lambda selector:row_list if selector=="tr" else Mock()
  def body(_):
   if not selected:return "Search results" if records else "No records found"
   i,n,s=selected[-1]
   return f"Organization Name\n{detail_name or n}\nExpiration Date\n03/14/2027\nContact Name\nControl\nStatus\n{s}\nStreet Address\nAddress"
  with patch.object(c,"registry_page_body",side_effect=body),patch.object(c,"safe_wait_for_network_idle"):
   result=c.search_wv_precise(page,c.checker.Organization(name,"042103604"))
  return result,selected
 def test_reported_siblings_are_rejected_before_click(self):
  for name in ["Beth Israel Deaconess Hospital – Milton, Inc.","Beth Israel Deaconess Medical Center, Inc."]:
   with self.subTest(name=name):
    r,selected=self.wv([("22209","Beth Israel Deaconess Hospital - Needham, Inc.","Exempt")],name)
    self.assertEqual(c.public_status(r),"Not Registered");self.assertFalse(selected);self.assertFalse(r.matched_registry_name)
 def test_correct_location_wins_both_orders_with_active_sibling(self):
  right=("10","Beth Israel Deaconess Hospital - Milton, Inc.","Closed")
  wrong=("22209","Beth Israel Deaconess Hospital - Needham, Inc.","Active")
  for rows in [[wrong,right],[right,wrong]]:
   r,selected=self.wv(rows,"Beth Israel Deaconess Hospital – Milton, Inc.")
   self.assertEqual(selected[0][0],"10");self.assertEqual(c.public_status(r),"Closed / Withdrawn / Canceled")
 def test_correct_location_found_by_broad_query(self):
  r,selected=self.wv([("22209","Beth Israel Deaconess Hospital - Needham, Inc.","Exempt")],"Beth Israel Deaconess Hospital – Needham, Inc.")
  self.assertEqual(c.public_status(r),"Exempt");self.assertEqual(selected[0][0],"22209")
 def test_detail_cannot_switch_to_sibling_using_broad_query(self):
  r,_=self.wv([("10","Beth Israel Deaconess Hospital - Milton, Inc.","Active")],"Beth Israel Deaconess Hospital – Milton, Inc.",detail_name="Beth Israel Deaconess Hospital - Needham, Inc.")
  self.assertEqual(c.public_status(r),"Not Registered");self.assertFalse(r.matched_registry_identifier)

if __name__=="__main__":unittest.main()
