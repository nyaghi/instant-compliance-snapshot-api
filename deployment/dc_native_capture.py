from deployment.workflow_observation import workflow_call, trace_return, workflow_stage
"""LOCAL ONLY. Original publisher-linked DC table, never a reconstructed page.

No staging import points to this module. Matching and status are not changed.
"""
import re
import time
from datetime import date
from urllib.parse import urlsplit, parse_qsl

SOURCE='https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/DCRA/FeatureServer/0'
VIEWER='https://www.arcgis.com/apps/mapviewer/index.html?url='+SOURCE+'&source=sd'
COLUMNS=('CUSTOMERNUMBER','LICENSESTATUS','LICENSEENDDATE','ENTITYNAME')
LABELS=('Customer Number','License Status','Licensed End Date','Entity Name')

READ_ROW=r'''() => {
 const grids=[...document.querySelectorAll('vaadin-grid')].filter(g=>g.getBoundingClientRect().width>0);
 if(grids.length!==1)return null;
 const g=grids[0],s=g.shadowRoot,t=s?.querySelector('table');
 if(!t||t.getAttribute('aria-rowcount')!=='2'||t.getAttribute('aria-colcount')!=='5')return null;
 const columns=[...g.querySelectorAll('vaadin-grid-column')].map(e=>e.getAttribute('data-fieldname'));
 const rows=[...s.querySelectorAll('tbody tr')].filter(r=>!r.hidden&&!r.hasAttribute('loading')&&r.getBoundingClientRect().height>0);
 if(rows.length!==1||rows[0].getAttribute('aria-rowindex')!=='2')return null;
 const cells=[...rows[0].querySelectorAll('td')].slice(1);
 const texts=[],clipped=[];
 for(const td of cells){
  const slot=td.querySelector('slot'),assigned=slot?.assignedElements();
  if(assigned?.length!==1)return null;
  const e=assigned[0],r=e.getBoundingClientRect(),c=td.getBoundingClientRect();
  if(r.width<=0||r.height<=0||c.x<0||c.right>innerWidth||c.y<0||c.bottom>innerHeight)return null;
  const range=document.createRange();range.selectNodeContents(e);
  const textRect=range.getBoundingClientRect();
  texts.push(e.innerText.trim());
  clipped.push(textRect.right>c.right-4||textRect.left<c.left);
 }
 const headings=[...s.querySelectorAll('thead th')].slice(1).map(td=>td.querySelector('slot')?.assignedElements().map(e=>e.innerText.trim()).join(''));
 return {columns,texts,clipped,headings};
}'''

READ_ROW_DIAGNOSTIC = "() => {\n const grids=[...document.querySelectorAll('vaadin-grid')].filter(g=>g.getBoundingClientRect().width>0);\n if(grids.length!==1)return {reason:'grid_count'};\n const g=grids[0],s=g.shadowRoot,t=s?.querySelector('table');\n if(!t||t.getAttribute('aria-rowcount')!=='2'||t.getAttribute('aria-colcount')!=='5')return {reason:'table_shape'};\n const columns=[...g.querySelectorAll('vaadin-grid-column')].map(e=>e.getAttribute('data-fieldname'));\n const rows=[...s.querySelectorAll('tbody tr')].filter(r=>!r.hidden&&!r.hasAttribute('loading')&&r.getBoundingClientRect().height>0);\n if(rows.length!==1||rows[0].getAttribute('aria-rowindex')!=='2')return {reason:'rendered_row'};\n const cells=[...rows[0].querySelectorAll('td')].slice(1);\n const texts=[],clipped=[];\n for(const td of cells){\n  const slot=td.querySelector('slot'),assigned=slot?.assignedElements();\n  if(assigned?.length!==1)return {reason:'assigned_cell'};\n  const e=assigned[0],r=e.getBoundingClientRect(),c=td.getBoundingClientRect();\n  if(r.width<=0||r.height<=0||c.x<0||c.right>innerWidth||c.y<0||c.bottom>innerHeight)return {reason:'cell_geometry'};\n  const range=document.createRange();range.selectNodeContents(e);\n  const textRect=range.getBoundingClientRect();\n  texts.push(e.innerText.trim());\n  clipped.push(textRect.right>c.right-4||textRect.left<c.left);\n }\n const headings=[...s.querySelectorAll('thead th')].slice(1).map(td=>td.querySelector('slot')?.assignedElements().map(e=>e.innerText.trim()).join(''));\n return {reason:'row_available',columns:columns.slice(0,8),texts:texts.slice(0,4).map(v=>v.slice(0,320)),clipped:clipped.slice(0,4),headings:headings.slice(0,8)};\n}"

def valid_viewer(url):
 try:
  u=urlsplit(url)
  return (trace_return('deployment/dc_native_capture.py:valid_viewer:42:2:return',(u.scheme=='https' and u.hostname=='www.arcgis.com' and u.port in (None,443)
   and not u.username and not u.password and not u.fragment
   and u.path=='/apps/mapviewer/index.html'
   and parse_qsl(u.query,keep_blank_values=True)==[('url',SOURCE),('source','sd')])))
 except (ValueError,TypeError):return trace_return('deployment/dc_native_capture.py:valid_viewer:46:31:return',(False))

def expected_record(record):
 if not isinstance(record,dict):return trace_return('deployment/dc_native_capture.py:expected_record:49:32:return',(None))
 number=str(workflow_call('deployment/dc_native_capture.py:expected_record:50:12:get',record.get,locals(), 'identifier') or '')
 name=str(workflow_call('deployment/dc_native_capture.py:expected_record:51:10:get',record.get,locals(), 'name') or '').strip();status=str(workflow_call('deployment/dc_native_capture.py:expected_record:51:55:get',record.get,locals(), 'raw_status') or '').strip()
 expiry=str(workflow_call('deployment/dc_native_capture.py:expected_record:52:12:get',record.get,locals(), 'expiration') or '')
 if not re.fullmatch(r'\d{5,16}',number) or not name or len(name)>300 or not status or len(status)>100:return trace_return('deployment/dc_native_capture.py:expected_record:53:103:return',(None))
 if 'charitable' not in str(workflow_call('deployment/dc_native_capture.py:expected_record:54:28:get',record.get,locals(), 'license_category','')).lower():return trace_return('deployment/dc_native_capture.py:expected_record:54:71:return',(None))
 try:
  day=date.fromisoformat(expiry)
  u=urlsplit(workflow_call('deployment/dc_native_capture.py:expected_record:57:13:get',record.get,locals(), 'url',''));pairs=parse_qsl(u.query,keep_blank_values=True)
  if (u.scheme!='https' or u.hostname!='maps2.dcgis.dc.gov' or u.port not in (None,443)
      or u.username or u.password or u.fragment or u.path!='/dcgis/rest/services/FEEDS/DCRA/FeatureServer/0/query'
      or pairs!=[('where',"CUSTOMERNUMBER='"+number+"'"),('outFields','*'),('returnGeometry','false'),('f','pjson')]):return trace_return('deployment/dc_native_capture.py:expected_record:60:118:return',(None))
 except (ValueError,TypeError):return trace_return('deployment/dc_native_capture.py:expected_record:61:31:return',(None))
 return trace_return('deployment/dc_native_capture.py:expected_record:62:1:return',({'identifier':number,'name':name,'raw_status':status,'expiration':day.isoformat()}))

def bound_values(url,values,expected):
 if not valid_viewer(url) or not isinstance(values,dict) or not expected:return trace_return('deployment/dc_native_capture.py:bound_values:65:73:return',(None))
 if workflow_call('deployment/dc_native_capture.py:bound_values:66:4:get',values.get,locals(), 'columns')!=list(COLUMNS) or workflow_call('deployment/dc_native_capture.py:bound_values:66:44:get',values.get,locals(), 'headings')!=list(LABELS):return trace_return('deployment/dc_native_capture.py:bound_values:66:81:return',(None))
 text=workflow_call('deployment/dc_native_capture.py:bound_values:67:6:get',values.get,locals(), 'texts');clipped=workflow_call('deployment/dc_native_capture.py:bound_values:67:34:get',values.get,locals(), 'clipped')
 if not isinstance(text,list) or len(text)!=4 or clipped!=[False]*4:return trace_return('deployment/dc_native_capture.py:bound_values:68:68:return',(None))
 if text[0]!=expected['identifier'] or text[1]!=expected['raw_status'] or text[3]!=expected['name']:return trace_return('deployment/dc_native_capture.py:bound_values:69:100:return',(None))
 day=date.fromisoformat(expected['expiration'])
 if text[2]!=f'{day.month}/{day.day}/{day.year%100:02d}, 12:00 AM':return trace_return('deployment/dc_native_capture.py:bound_values:71:67:return',(None))
 return trace_return('deployment/dc_native_capture.py:bound_values:72:1:return',(tuple(text)))

def capture_ready(page,expected,deadline):
 before=bound_values(page.url,workflow_call('deployment/dc_native_capture.py:capture_ready:75:30:evaluate',page.evaluate,locals(), READ_ROW),expected)
 if before is None or deadline-time.monotonic()<1:return trace_return('deployment/dc_native_capture.py:capture_ready:76:50:return',(None))
 started=time.perf_counter()
 raw=workflow_call('deployment/dc_native_capture.py:capture_ready:78:5:screenshot',page.screenshot,locals(), type='png',full_page=True,timeout=max(1,int((deadline-time.monotonic()-.5)*1000)))
 after=bound_values(page.url,workflow_call('deployment/dc_native_capture.py:capture_ready:79:29:evaluate',page.evaluate,locals(), READ_ROW),expected)
 if after!=before or time.monotonic()>=deadline:return trace_return('deployment/dc_native_capture.py:capture_ready:80:48:return',(None))
 return trace_return('deployment/dc_native_capture.py:capture_ready:81:1:return',({'source_url':page.url,'bytes':raw,'fields':dict(zip(LABELS,before)),'capture_ms':round((time.perf_counter()-started)*1000,2),
  'note':'Original DC published-license table in its publisher-linked ArcGIS viewer. This is the public extract used for the status lookup, not a fresh BOSS record. Its published refresh limitation still applies.'}))

def navigate_and_capture(page,record,deadline,on_query=None,metrics=None):
 """Native controls only. Caller supplies owned page and absolute deadline."""
 expected=expected_record(record)
 if not expected or deadline-time.monotonic()<3:return trace_return('deployment/dc_native_capture.py:navigate_and_capture:87:48:return',(None))
 metrics=metrics if metrics is not None else {}
 def measured(label,action):
  metrics['last_phase']=label;started=time.perf_counter()
  try:return trace_return('deployment/dc_native_capture.py:measured:91:6:return',(action()))
  finally:metrics[label+'_seconds']=round(time.perf_counter()-started,6)
 def allowance():
  remaining=deadline-time.monotonic()-1
  if remaining<=0:raise TimeoutError('DC visual deadline reserve')
  return trace_return('deployment/dc_native_capture.py:allowance:96:2:return',(max(1,int(remaining*1000))))
 response=measured('navigation',lambda:workflow_call('deployment/dc_native_capture.py:navigate_and_capture:97:39:goto',page.goto,locals(), VIEWER,wait_until='domcontentloaded',timeout=allowance()))
 if response is None or response.status!=200 or not valid_viewer(page.url):return trace_return('deployment/dc_native_capture.py:navigate_and_capture:98:75:return',(None))
 measured('tables_ready',lambda:workflow_call('deployment/dc_native_capture.py:navigate_and_capture:99:32:click',page.get_by_role('button',name=re.compile(r'^Tables(?: \(Indicator present\))?$')).click,locals(), timeout=allowance()))
 measured('filter_ready',lambda:workflow_call('deployment/dc_native_capture.py:navigate_and_capture:100:32:click',page.get_by_role('button',name='Filter',exact=True).click,locals(), timeout=allowance()))
 measured('condition_ready',lambda:workflow_call('deployment/dc_native_capture.py:navigate_and_capture:101:35:click',page.get_by_role('button',name='Add new',exact=True).click,locals(), timeout=allowance()))
 workflow_call('deployment/dc_native_capture.py:navigate_and_capture:102:1:wait_for',page.get_by_role('button',name='Customer Number',exact=True).wait_for,locals(), state='visible',timeout=allowance())
 # Default native operator must be exact; never submit a broadened condition.
 operator=page.get_by_role('combobox',name='Operator',exact=True)
 # ArcGIS renders the select before asynchronously supplying its native options.
 # Observe completion within the existing deadline; never select a different mode.
 measured('operator_visible',lambda:workflow_call('deployment/dc_native_capture.py:navigate_and_capture:107:36:wait_for',operator.wait_for,locals(), state='visible',timeout=allowance()))
 if workflow_call('deployment/dc_native_capture.py:navigate_and_capture:108:4:count',operator.count,locals())!=1:return trace_return('deployment/dc_native_capture.py:navigate_and_capture:108:24:return',(None))
 measured('operator_options_ready',lambda:workflow_call('deployment/dc_native_capture.py:navigate_and_capture:109:42:wait_for',operator.locator('option[value="is"]').wait_for,locals(), state='attached',timeout=allowance()))
 metrics['operator_count']=workflow_call('deployment/dc_native_capture.py:navigate_and_capture:110:27:count',operator.count,locals())
 metrics['operator_value']=workflow_call('deployment/dc_native_capture.py:navigate_and_capture:111:27:input_value',operator.input_value,locals(), timeout=allowance())
 if metrics['operator_count']!=1 or metrics['operator_value']!='is':return trace_return('deployment/dc_native_capture.py:navigate_and_capture:112:68:return',(None))
 workflow_call('deployment/dc_native_capture.py:navigate_and_capture:113:1:fill',page.get_by_role('textbox',name='Value',exact=True).fill,locals(), expected['identifier'],timeout=allowance())
 if on_query:on_query()
 measured('exact_query_submit',lambda:workflow_call('deployment/dc_native_capture.py:navigate_and_capture:115:38:click',page.get_by_role('button',name='Save',exact=True).click,locals(), timeout=allowance()))
 measured('column_controls_ready',lambda:workflow_call('deployment/dc_native_capture.py:navigate_and_capture:116:41:click',page.get_by_role('button',name='Column visibility',exact=True).click,locals(), timeout=allowance()))
 columns_started=time.perf_counter();metrics['last_phase']='select_columns'
 select=page.get_by_role('button',name='Select all',exact=True)
 if workflow_call('deployment/dc_native_capture.py:navigate_and_capture:119:4:count',select.count,locals()):workflow_call('deployment/dc_native_capture.py:navigate_and_capture:119:19:click',select.click,locals(), timeout=allowance())
 workflow_call('deployment/dc_native_capture.py:navigate_and_capture:120:1:click',page.get_by_role('button',name='Deselect all',exact=True).click,locals(), timeout=allowance())
 # Native selection updates asynchronously. Observe each completed selection
 # before the next click; preserve the final exact table/record/pixel guards.
 from playwright.sync_api import expect
 for label in LABELS:
  row=page.get_by_role('row',name=label,exact=True)
  measured('column_cleared_'+label,lambda:expect(row).to_have_attribute('aria-selected','false',timeout=allowance()))
 for label in LABELS:
  row=page.get_by_role('row',name=label,exact=True)
  workflow_call('DC.column_select',row.click,locals(),timeout=allowance())
  measured('column_selected_'+label,lambda:expect(row).to_have_attribute('aria-selected','true',timeout=allowance()))
 workflow_call('deployment/dc_native_capture.py:navigate_and_capture:123:1:click',page.get_by_role('button',name='Column visibility',exact=True).click,locals(), timeout=allowance())
 # Close the native Tables panel to give the original row its full width.
 # No source CSS/text is changed. Long names still must pass clipping checks.
 workflow_call('deployment/dc_native_capture.py:navigate_and_capture:126:1:click',page.get_by_role('button',name='Tables',exact=True).click,locals(), timeout=allowance())
 metrics['select_columns_seconds']=round(time.perf_counter()-columns_started,6)
 # Observe rendered row, not hidden virtualized records left in DOM.
 day=date.fromisoformat(expected['expiration'])
 ready_text=[expected['identifier'],expected['raw_status'],f'{day.month}/{day.day}/{day.year%100:02d}, 12:00 AM',expected['name']]
 try:
  measured('bound_record_ready',lambda:workflow_call('deployment/dc_native_capture.py:navigate_and_capture:131:38:wait_for_function',page.wait_for_function,locals(), 'arg=>{const v=('+READ_ROW+')();return v&&JSON.stringify(v.columns)===JSON.stringify(arg.columns)&&JSON.stringify(v.headings)===JSON.stringify(arg.labels)&&JSON.stringify(v.texts)===JSON.stringify(arg.texts)&&v.clipped.every(x=>x===false)}',arg={'columns':list(COLUMNS),'labels':list(LABELS),'texts':ready_text},timeout=allowance()))
 except Exception:
  # Read only the failed public-table predicate inside the existing completion
  # reserve. No retry, alternate record, query, or changed acceptance rule.
  remaining=deadline-time.monotonic()
  if remaining>.1:
   try:
    metrics['bound_record_failure']=page.locator('body').evaluate('el=>('+READ_ROW_DIAGNOSTIC+')()',timeout=max(1,int(min(.5,remaining)*1000)))
   except Exception as exc:metrics['bound_record_observation_error']=type(exc).__name__
  raise
 return trace_return('deployment/dc_native_capture.py:navigate_and_capture:132:1:return',(measured('screenshot_and_recheck',lambda:workflow_call('deployment/dc_native_capture.py:navigate_and_capture:132:49:capture_ready',capture_ready,locals(), page,expected,deadline))))
