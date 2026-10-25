"""Evidence from the exact original LA workbook used by the status lookup."""
import hashlib,io,json,re,time,zipfile
from pathlib import Path
from functools import lru_cache
from PIL import Image
URL='https://www.ag.state.la.us/Charity/Registration/Listing'

@lru_cache(maxsize=1)
def load_cache(root,index_stamp,archive_stamp,source_stamp):
 root=Path(root);source=root/'LA.xlsx';index_path=root/'LA-original-row-images.json';archive=root/'LA-original-row-images.zip'
 if source.stat().st_size>20_000_000 or index_path.stat().st_size>10_000_000 or archive.stat().st_size>50_000_000:raise ValueError('Cache bound')
 index=json.loads(index_path.read_text())
 if index.get('schema')!='la-original-row-images-v1' or index.get('source_url')!=URL or index.get('source_sha256')!=hashlib.sha256(source.read_bytes()).hexdigest() or index.get('archive_sha256')!=hashlib.sha256(archive.read_bytes()).hexdigest():raise ValueError('Cache/source changed')
 rows=index.get('rows',[])
 if not 25<=len(rows)<=20000:raise ValueError('Row count')
 return index

def capture_original_la_row(master,result,run,deadline,root=None):
 if run is None or run.state!='LA' or result.get('state')!='LA' or re.sub(r'\D','',str(result.get('ein','')))!=run.ein:return False
 if result.get('success') is not True or result.get('confirmation_required') or result.get('_worker_identity_review') or result.get('status') in {'Not Registered','Unable to Confirm','Unable to Verify','Site Not Reachable','Needs Review'}:return False
 if result.get('status_reason')!='LA_STATUS_FROM_OFFICIAL_EXCEL_EXPORT' or result.get('source_url')!=URL:return False
 if time.monotonic()+.5>=deadline:return False
 root=Path(root) if root else Path(__file__).resolve().parents[1]/'downloadable-data'
 fact=dict(adapter='LA-original-workbook-row',outcome='not_started',total_ms=0,capture_ms=0);run.visual_adapter_facts.append(fact);start=time.perf_counter()
 try:
  index=load_cache(str(root),*( (root/name).stat().st_mtime_ns for name in ('LA-original-row-images.json','LA-original-row-images.zip','LA.xlsx')))
  rows=master.la_registered_charities_rows_from_xlsx(root/'LA.xlsx');name=result.get('matched_registry_name','')
  selected=[r for r in rows if master.la_record_name(r)==name]
  if len(selected)!=1:raise ValueError('Ambiguous selected row')
  selected=selected[0];date=master.la_record_registered_through(selected);services=master.la_record_program_services(selected)
  raw=' | '.join(s for s in [f'Registered Through: {date}' if date else '',f'Program Services Percentage: {services}' if services else '']) or 'Louisiana export row matched'
  if raw!=result.get('raw_status_text'):raise ValueError('Selected fields changed')
  cached=[r for r in index['rows'] if isinstance(r.get('cells'),list) and len(r['cells'])==3 and master.clean_registry_name(r['cells'][0])==name and master.parse_due_date(r['cells'][1])==master.parse_due_date(date)]
  if len(cached)!=1:raise ValueError('Original row absent or ambiguous')
  row=cached[0]
  from decimal import Decimal
  if Decimal(row['cells'][2].replace('%',''))!=Decimal(services.replace('%','')):raise ValueError('Percentage changed')
  if not re.fullmatch(r'\d+\.webp',row['image']):raise ValueError('Image path')
  with zipfile.ZipFile(root/'LA-original-row-images.zip') as archive:
   info=archive.getinfo(row['image'])
   if info.file_size>1_000_000:raise ValueError('Image bound')
   packed=archive.read(info)
  if hashlib.sha256(packed).hexdigest()!=row['image_sha256']:raise ValueError('Pixels changed')
  image=Image.open(io.BytesIO(packed));image.load()
  if image.format!='WEBP' or image.width*image.height>4_000_000:raise ValueError('Image shape')
  output=io.BytesIO();image.convert('RGB').save(output,format='PNG')
  if time.monotonic()+.1>=deadline:raise ValueError('Deadline')
  before=len(run.documents);run.document(URL,output.getvalue(),'image',row['public_text'],note='Original Louisiana workbook row '+str(row['row'])+' used by this lookup. Cached Calc viewer pixels; source workbook SHA256 '+index['source_sha256']+'. This is the saved weekly workbook, not a fresh web-table search.')
  if len(run.documents)<=before:raise ValueError('Document not retained')
  doc=run.documents[-1];run.documents[-1]=(*doc[:4],row['rendered_at'],doc[5]);fact['outcome']='captured';return True
 except Exception as exc:
  fact.update(outcome='cache_or_binding_unavailable',error_type=type(exc).__name__);return False
 finally:fact['total_ms']=round((time.perf_counter()-start)*1000,2)
