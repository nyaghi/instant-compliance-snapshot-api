from deployment.workflow_observation import workflow_call, trace_return, workflow_stage
"""Original workbook viewer pixels, bound to the exact Kansas source bytes.

No lookup, status calculation, invented row, or viewer startup during a check.
The maintenance cache is invalidated by any workbook checksum change.
"""
import hashlib,io,json,re,time,zipfile
from pathlib import Path
from functools import lru_cache
from datetime import datetime
from PIL import Image

@lru_cache(maxsize=1)
def load_cache(root,index_stamp,archive_stamp):
    root=Path(root);index_path=root/'KS-original-row-images.json';archive_path=root/'KS-original-row-images.zip'
    if index_path.stat().st_size>20_000_000 or archive_path.stat().st_size>150_000_000:raise ValueError('Cache bound exceeded')
    index=json.loads(index_path.read_text())
    if (workflow_call('deployment/kansas_row_evidence.py:load_cache:17:8:get',index.get,locals(), 'schema')!='ks-original-row-images-v1' or not re.fullmatch(r'[a-f0-9]{64}',workflow_call('deployment/kansas_row_evidence.py:load_cache:17:93:get',index.get,locals(), 'source_sha256',''))
        or hashlib.sha256(archive_path.read_bytes()).hexdigest()!=workflow_call('deployment/kansas_row_evidence.py:load_cache:18:66:get',index.get,locals(), 'archive_sha256')):raise ValueError('Cache integrity mismatch')
    rows=workflow_call('deployment/kansas_row_evidence.py:load_cache:19:9:get',index.get,locals(), 'rows')
    if not isinstance(rows,list) or not 1<=len(rows)<=20000:raise ValueError('Invalid cache rows')
    by_id={}
    for row in rows:
        if not isinstance(row,dict) or not re.fullmatch(r'\d+\.webp',workflow_call('deployment/kansas_row_evidence.py:load_cache:23:69:get',row.get,locals(), 'image','')):raise ValueError('Invalid row image')
        by_id.setdefault(workflow_call('deployment/kansas_row_evidence.py:load_cache:24:25:get',row.get,locals(), 'identifier'),[]).append(row)
    return trace_return('deployment/kansas_row_evidence.py:load_cache:25:4:return',(index,by_id))

def original_row(module,result,root):
    if (workflow_call('deployment/kansas_row_evidence.py:original_row:28:8:get',result.get,locals(), 'state')!='KS' or workflow_call('deployment/kansas_row_evidence.py:original_row:28:37:get',result.get,locals(), 'success') is not True or workflow_call('deployment/kansas_row_evidence.py:original_row:28:74:get',result.get,locals(), 'confirmation_required')
        or workflow_call('deployment/kansas_row_evidence.py:original_row:29:11:get',result.get,locals(), 'status') in {'Not Registered','Unable to Confirm','Unable to Verify','Site Not Reachable','Needs Review'}):return trace_return('deployment/kansas_row_evidence.py:original_row:29:130:return',(None))
    root=Path(root)
    index,by_id=load_cache(str(root),(root/'KS-original-row-images.json').stat().st_mtime_ns,(root/'KS-original-row-images.zip').stat().st_mtime_ns)
    source=module.load_embedded_workbook_bytes();sha=hashlib.sha256(source).hexdigest()
    if sha!=index['source_sha256'] or sha!=module.SNAPSHOT_CHECKSUM or module.SNAPSHOT_SOURCE_URL!=index['source_url']:
        raise ValueError('Original workbook changed; regenerate row evidence')
    identifier=workflow_call('deployment/kansas_row_evidence.py:original_row:35:15:get',result.get,locals(), 'matched_registry_identifier');name=workflow_call('deployment/kansas_row_evidence.py:original_row:35:62:get',result.get,locals(), 'matched_registry_name')
    matches=[r for r in workflow_call('deployment/kansas_row_evidence.py:original_row:36:24:get',by_id.get,locals(), identifier,[]) if workflow_call('deployment/kansas_row_evidence.py:original_row:36:52:get',r.get,locals(), 'name')==name]
    if len(matches)!=1:raise ValueError('Unambiguous original row required')
    row=matches[0];records=module.records_from_workbook_bytes(source)
    actual=[r for r in records if r.contact_number==identifier and r.name==name]
    if len(actual)!=1:raise ValueError('Source row is ambiguous')
    actual=actual[0];expiration=actual.expire_date.isoformat() if actual.expire_date else ''
    displayed=datetime.strptime(row['expiration'],'%m/%d/%Y').date().isoformat() if workflow_call('deployment/kansas_row_evidence.py:original_row:42:84:get',row.get,locals(), 'expiration') else ''
    raw=actual.status+(' | Expiration Date: '+expiration if expiration else '')
    if workflow_call('deployment/kansas_row_evidence.py:original_row:44:7:get',row.get,locals(), 'raw_status')!=actual.status or expiration!=displayed or workflow_call('deployment/kansas_row_evidence.py:original_row:44:72:get',result.get,locals(), 'raw_status_text')!=raw:
        raise ValueError('Original standing or date changed')
    with zipfile.ZipFile(root/'KS-original-row-images.zip') as archive:
        item=archive.getinfo(row['image'])
        if item.file_size>1_000_000:raise ValueError('Row image exceeds bound')
        packed=workflow_call('deployment/kansas_row_evidence.py:original_row:49:15:read',archive.read,locals(), item)
    if hashlib.sha256(packed).hexdigest()!=row['image_sha256']:raise ValueError('Row pixels changed')
    image=Image.open(io.BytesIO(packed));image.load()
    if image.format!='WEBP' or image.width*image.height>4_000_000:raise ValueError('Invalid original row pixels')
    out=io.BytesIO();image.convert('RGB').save(out,format='PNG')
    return trace_return('deployment/kansas_row_evidence.py:original_row:54:4:return',(row,out.getvalue(),index))

def capture_selected_kansas(master,result,run,deadline,root=None):
    if run is None or run.state!='KS' or workflow_call('deployment/kansas_row_evidence.py:capture_selected_kansas:57:41:get',result.get,locals(), 'state')!='KS' or re.sub(r'\D','',str(workflow_call('deployment/kansas_row_evidence.py:capture_selected_kansas:57:90:get',result.get,locals(), 'ein','')))!=run.ein:return trace_return('deployment/kansas_row_evidence.py:capture_selected_kansas:57:122:return',None)
    if getattr(run,'ks_original_row_attempted',False):return trace_return('deployment/kansas_row_evidence.py:capture_selected_kansas:58:54:return',None)
    run.ks_original_row_attempted=True
    start=time.perf_counter();fact={'adapter':'KS-original-workbook-row','outcome':'not_started','total_ms':0,'capture_ms':0};run.visual_adapter_facts.append(fact)
    try:
        if time.monotonic()+.5>=deadline:fact['outcome']='deadline_reserve';return trace_return('deployment/kansas_row_evidence.py:capture_selected_kansas:62:76:return',None)
        root=Path(root) if root else Path(__file__).resolve().parents[1]/'downloadable-data'
        item=original_row(master.load_ks_weekly_checker(),result,root)
        if item is None:fact['outcome']='no_selected_row';return trace_return('deployment/kansas_row_evidence.py:capture_selected_kansas:65:58:return',None)
        row,pixels,index=item
        workflow_call('deployment/kansas_row_evidence.py:capture_selected_kansas:67:8:document',run.document,locals(), index['source_url'],pixels,'image',row['public_text'],note='Original Kansas workbook row '+str(row['row'])+' shown by LibreOffice Calc; cells wrapped for readability; no cell values changed. Source workbook SHA256 '+index['source_sha256']+'. Cached viewer image; no new state search.')
        # The archive must retain when these pixels were produced, not pretend
        # that a cached workbook was re-photographed during every run.
        if run.documents:
            last=run.documents[-1];run.documents[-1]=(*last[:4],row['rendered_at'],last[5]);fact['outcome']='captured'
    except Exception:
        fact['outcome']='cache_or_binding_unavailable';run.errors.append('KS_original_row_unavailable')
    finally:fact['total_ms']=round((time.perf_counter()-start)*1000,2)
