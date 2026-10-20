"""NV empty pages are admitted only with an explicit complete-empty receipt."""
import base64,copy,io,time,unittest
from pypdf import PdfReader
from PIL import Image
from testing.test_state_snapshots import Snapshots,image,COHORT
from deployment import state_snapshots as s
class NVEmptyPages(Snapshots):
 def inputs(self,org):
  query=dict(state='NV',operation='search',name=org['name'])
  images=[]
  for line in ['LOCAL QUERY','LOCAL No records available']:
   output=io.BytesIO();Image.open(io.BytesIO(image(org['name'],line))).convert('RGB').save(output,format='JPEG');images.append(base64.b64encode(output.getvalue()).decode())
  record=dict(state='NV',ein=org['ein'],organization_name=org['name'],issued=time.time())
  payload=dict(query_id='local',state_snapshot=dict(query=query,source_url='https://orion.nv.gov/portal/public/',public_text=org['name']+' No records available',captured_at=time.time(),image=images[0],images=images))
  return record,payload,query,dict(query=query,complete=True,total=0,rows=[])
 def test_thirty_empty_source_page_sets_archive_original_bytes_and_reopen(self):
  for org in COHORT:
   record,payload,q,e=self.inputs(org);s.connector_archive(record,payload,q,e);ref=record['source_snapshots'][0];self.assertEqual(ref['identifier'],'@completed-search');_,pdf=s.saved_pdf(ref['url'].split('/')[-1][:-4],self.store);pages=PdfReader(io.BytesIO(pdf)).pages;self.assertEqual(len(pages),2)
   for page,raw in zip(pages,payload['state_snapshot']['images']):self.assertEqual(page.extract_text(),'');self.assertEqual(list(page['/Resources']['/XObject'].get_object().values())[0].get_object().get_data(),base64.b64decode(raw))
 def test_thirty_contexts_ten_unsafe_page_sets_fail_closed(self):
  for org in COHORT:
   for bad in ['incomplete','unknown-total','positive','wrong-query','wrong-host','captcha','missing-empty','first-page-mismatch','four-pages','other-state-search']:
    record,payload,q,e=self.inputs(org);snapshot=payload['state_snapshot']
    if bad=='incomplete':e['complete']=False
    if bad=='unknown-total':e.pop('total')
    if bad=='positive':e.update(total=1,rows=[dict(name=org['name'],identifier='OTHER')]);snapshot['public_text']+=' OTHER'
    if bad=='wrong-query':snapshot['query']={**q,'name':'OTHER'}
    if bad=='wrong-host':snapshot['source_url']='https://example.com/search'
    if bad=='captcha':snapshot['public_text']='Verify you are human'
    if bad=='missing-empty':snapshot['public_text']=org['name']
    if bad=='first-page-mismatch':snapshot['image']=snapshot['images'][1]
    if bad=='four-pages':snapshot['images']*=2
    if bad=='other-state-search':record['state']='TN';q['state']='TN';snapshot['source_url']='https://tncab.tnsos.gov/portal/registered-charities-search'
    s.connector_archive(record,payload,q,e);self.assertFalse(record.get('source_snapshots'),bad)
if __name__=='__main__':
 suite=unittest.TestSuite(NVEmptyPages(n) for n in ['test_thirty_empty_source_page_sets_archive_original_bytes_and_reopen','test_thirty_contexts_ten_unsafe_page_sets_fail_closed']);result=unittest.TextTestRunner(verbosity=2).run(suite);raise SystemExit(not result.wasSuccessful())
