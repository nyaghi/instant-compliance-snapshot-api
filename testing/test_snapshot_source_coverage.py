"""Source-image page and numberless NC archive controls. All local fixtures."""
import base64,copy,io,json,sys,time,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from deployment import state_snapshots as s
from testing.test_state_snapshots import Snapshots,image,COHORT
from pypdf import PdfReader
from PIL import Image
RECEIPT={}

class Coverage(Snapshots):
 def test_jpeg_original_compressed_bytes_are_retained_on_each_pdf_page(self):
  originals=[]
  for label in ['LOCAL TOP','LOCAL EXPIRATION','LOCAL FINANCIAL']:
   with Image.open(io.BytesIO(image('LOCAL FIXTURE ONLY',label))) as im:
    out=io.BytesIO();im.convert('RGB').save(out,format='JPEG',quality=75);originals.append(out.getvalue())
  asset=self.asset(state='TN');asset['kind']='image_pages';asset['content']=base64.b64encode(json.dumps([base64.b64encode(raw).decode() for raw in originals]).encode()).decode()
  meta,raw=s.validate_asset(asset,ein=asset['ein'],state='TN',run_id=asset['run_id'])
  pages=PdfReader(io.BytesIO(s.render_pdf(meta,raw))).pages
  self.assertEqual(len(pages),3)
  for page,original in zip(pages,originals):
   objects=list(page['/Resources']['/XObject'].get_object().values())
   self.assertEqual(len(objects),1);self.assertEqual(objects[0].get_object().get_data(),original)
  RECEIPT['JPEG_original_pages_byte_equal']=3

 def test_thirty_tn_three_original_image_pages_archive_and_reopen_without_redraw(self):
  for org in COHORT:
   originals=[image(org['name'],label) for label in ['CO42115 - LOCAL TOP FIXTURE','CO42115 - LOCAL EXPIRATION FIXTURE','CO42115 - LOCAL FINANCIAL FIXTURE']]
   encoded=[base64.b64encode(b).decode() for b in originals]
   asset=self.asset(org,identifier='CO42115',state='TN');asset['kind']='image_pages';asset['content']=base64.b64encode(json.dumps(encoded).encode()).decode()
   ref=s.archive(asset,ein=org['ein'],state='TN',run_id=asset['run_id'])
   meta,pdf=s.saved_pdf(ref['url'].split('/')[-1][:-4],self.store)
   pages=PdfReader(io.BytesIO(pdf)).pages
   self.assertEqual(len(pages),3);self.assertEqual(meta['kind'],'image_pages')
   for page,original in zip(pages,originals):
    self.assertEqual(page.extract_text(),'');self.assertEqual(len(page.images),1)
    with Image.open(io.BytesIO(page.images[0].data)) as actual,Image.open(io.BytesIO(original)) as expected:self.assertEqual(actual.convert('RGB').tobytes(),expected.convert('RGB').tobytes())
   self.assertEqual(s.saved_pdf(ref['url'].split('/')[-1][:-4],self.store)[1],pdf)
  RECEIPT['TN']={'distinct_retained_identities':30,'original_fixture_image_pages':90,'pixel_equal':True,'covers':0,'live_searches':0}

 def test_thirty_nc_application_snapshots_bind_exact_public_profile_without_invented_number(self):
  for org in COHORT:
   url='https://www.sosnc.gov/online_services/search/charities_profile/20535206'
   query={'state':'NC','operation':'detail','identifier':'NCAPP-20535206','url':url}
   evidence={'query':query,'complete':True,'fields':{'Name':org['name'],'Registration #':'','Status':'In-Process','Expiration Date':'','Extension End Date':'','Last Application Date':'','Street':'','City':'','State':'','Zip':'','profile_url':url}}
   record={'state':'NC','ein':org['ein'],'organization_name':org['name'],'issued':time.time()}
   incoming={'query':query,'source_url':url,'public_text':org['name']+' Status: In-Process','captured_at':time.time(),'image':base64.b64encode(image(org['name'],'LOCAL APPLICATION FIXTURE')).decode()}
   s.connector_archive(record,{'query_id':'local-command','state_snapshot':incoming},query,evidence)
   self.assertEqual(len(record['source_snapshots']),1)
   result=self.result(org,'NCAPP-20535206','NC');result['status']='Pending'
   linked=s.attach_links(result,record['source_snapshots']);self.assertTrue(linked['evidence_url']);self.assertEqual(linked['status'],'Pending')
   for bad in [{**query,'url':url+'0'},{**query,'identifier':'NCAPP-20535207'},{**query,'operation':'search'}]:
    negative={k:v for k,v in record.items() if k!='source_snapshots'}
    s.connector_archive(negative,{'query_id':'local-command','state_snapshot':{**incoming,'query':bad}},bad,evidence)
    self.assertFalse(negative.get('source_snapshots'))
  RECEIPT['NC']={'distinct_retained_identities':30,'exact_profile_bindings':30,'wrong_profile_or_operation_guards':90,'live_searches':0}

 def test_image_page_bounds_and_unsupported_browser_scope(self):
  asset=self.asset(state='TN');asset['kind']='image_pages'
  valid=base64.b64encode(image('LOCAL','CO42115')).decode()
  for encoded in [[],[valid],[valid]*4,[valid,'not-base64'],[valid,42],{'image':valid}]:
   asset['content']=base64.b64encode(json.dumps(encoded).encode()).decode()
   with self.subTest(encoded_type=type(encoded).__name__),self.assertRaises(Exception):s.validate_asset(asset,ein=asset['ein'],state='TN',run_id=asset['run_id'])
  record={'state':'NC','ein':COHORT[0]['ein'],'organization_name':COHORT[0]['name'],'issued':time.time()}
  query={'state':'NC','operation':'detail','identifier':'SL123456'}
  incoming={'query':query,'source_url':'https://www.sosnc.gov/online_services/search/charities_profile/123','public_text':COHORT[0]['name']+' SL123456','captured_at':time.time(),'image':valid,'images':[valid,valid]}
  s.connector_archive(record,{'query_id':'local-command','state_snapshot':incoming},query,{'fields':{'Name':COHORT[0]['name'],'Registration #':'SL123456'}})
  self.assertFalse(record.get('source_snapshots'))
  RECEIPT['page_guards']=7

if __name__=='__main__':
 suite=unittest.TestSuite(Coverage(name) for name in ['test_jpeg_original_compressed_bytes_are_retained_on_each_pdf_page','test_thirty_tn_three_original_image_pages_archive_and_reopen_without_redraw','test_thirty_nc_application_snapshots_bind_exact_public_profile_without_invented_number','test_image_page_bounds_and_unsupported_browser_scope'])
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 (ROOT.parent/'snapshot-source-coverage-receipt.json').write_text(json.dumps({**RECEIPT,'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors)},indent=2))
 sys.exit(not result.wasSuccessful())
