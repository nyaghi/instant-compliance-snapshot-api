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

def valid_viewer(url):
 try:
  u=urlsplit(url)
  return (u.scheme=='https' and u.hostname=='www.arcgis.com' and u.port in (None,443)
   and not u.username and not u.password and not u.fragment
   and u.path=='/apps/mapviewer/index.html'
   and parse_qsl(u.query,keep_blank_values=True)==[('url',SOURCE),('source','sd')])
 except (ValueError,TypeError):return False

def expected_record(record):
 if not isinstance(record,dict):return None
 number=str(record.get('identifier') or '')
 name=str(record.get('name') or '').strip();status=str(record.get('raw_status') or '').strip()
 expiry=str(record.get('expiration') or '')
 if not re.fullmatch(r'\d{5,16}',number) or not name or len(name)>300 or not status or len(status)>100:return None
 if 'charitable' not in str(record.get('license_category','')).lower():return None
 try:
  day=date.fromisoformat(expiry)
  u=urlsplit(record.get('url',''));pairs=parse_qsl(u.query,keep_blank_values=True)
  if (u.scheme!='https' or u.hostname!='maps2.dcgis.dc.gov' or u.port not in (None,443)
      or u.username or u.password or u.fragment or u.path!='/dcgis/rest/services/FEEDS/DCRA/FeatureServer/0/query'
      or pairs!=[('where',"CUSTOMERNUMBER='"+number+"'"),('outFields','*'),('returnGeometry','false'),('f','pjson')]):return None
 except (ValueError,TypeError):return None
 return {'identifier':number,'name':name,'raw_status':status,'expiration':day.isoformat()}

def bound_values(url,values,expected):
 if not valid_viewer(url) or not isinstance(values,dict) or not expected:return None
 if values.get('columns')!=list(COLUMNS) or values.get('headings')!=list(LABELS):return None
 text=values.get('texts');clipped=values.get('clipped')
 if not isinstance(text,list) or len(text)!=4 or clipped!=[False]*4:return None
 if text[0]!=expected['identifier'] or text[1]!=expected['raw_status'] or text[3]!=expected['name']:return None
 day=date.fromisoformat(expected['expiration'])
 if text[2]!=f'{day.month}/{day.day}/{day.year%100:02d}, 12:00 AM':return None
 return tuple(text)

def capture_ready(page,expected,deadline):
 before=bound_values(page.url,page.evaluate(READ_ROW),expected)
 if before is None or deadline-time.monotonic()<1:return None
 started=time.perf_counter()
 raw=page.screenshot(type='png',full_page=True,timeout=max(1,int(min(1.5,deadline-time.monotonic()-.5)*1000)))
 after=bound_values(page.url,page.evaluate(READ_ROW),expected)
 if after!=before or time.monotonic()>=deadline:return None
 return {'source_url':page.url,'bytes':raw,'fields':dict(zip(LABELS,before)),'capture_ms':round((time.perf_counter()-started)*1000,2),
  'note':'Original DC published-license table in its publisher-linked ArcGIS viewer. This is the public extract used for the status lookup, not a fresh BOSS record. Its published refresh limitation still applies.'}

def navigate_and_capture(page,record,deadline,on_query=None,metrics=None):
 """Native controls only. Caller supplies owned page and absolute deadline."""
 expected=expected_record(record)
 if not expected or deadline-time.monotonic()<3:return None
 metrics=metrics if metrics is not None else {}
 def measured(label,action):
  metrics['last_phase']=label;started=time.perf_counter()
  try:return action()
  finally:metrics[label+'_seconds']=round(time.perf_counter()-started,6)
 def allowance():
  remaining=deadline-time.monotonic()-1
  if remaining<=0:raise TimeoutError('DC visual deadline reserve')
  return max(1,int(remaining*1000))
 response=measured('navigation',lambda:page.goto(VIEWER,wait_until='domcontentloaded',timeout=allowance()))
 if response is None or response.status!=200 or not valid_viewer(page.url):return None
 measured('tables_ready',lambda:page.get_by_role('button',name=re.compile(r'^Tables(?: \(Indicator present\))?$')).click(timeout=allowance()))
 measured('filter_ready',lambda:page.get_by_role('button',name='Filter',exact=True).click(timeout=allowance()))
 measured('condition_ready',lambda:page.get_by_role('button',name='Add new',exact=True).click(timeout=allowance()))
 page.get_by_role('button',name='Customer Number',exact=True).wait_for(state='visible',timeout=allowance())
 # Default native operator must be exact; never submit a broadened condition.
 operator=page.get_by_role('combobox',name='Operator',exact=True)
 if operator.count()!=1 or operator.input_value(timeout=allowance())!='is':return None
 page.get_by_role('textbox',name='Value',exact=True).fill(expected['identifier'],timeout=allowance())
 if on_query:on_query()
 measured('exact_query_submit',lambda:page.get_by_role('button',name='Save',exact=True).click(timeout=allowance()))
 measured('column_controls_ready',lambda:page.get_by_role('button',name='Column visibility',exact=True).click(timeout=allowance()))
 columns_started=time.perf_counter();metrics['last_phase']='select_columns'
 select=page.get_by_role('button',name='Select all',exact=True)
 if select.count():select.click(timeout=allowance())
 page.get_by_role('button',name='Deselect all',exact=True).click(timeout=allowance())
 for label in LABELS:
  page.locator('.label').filter(has_text=re.compile('^'+re.escape(label)+'$')).click(timeout=allowance())
 page.get_by_role('button',name='Column visibility',exact=True).click(timeout=allowance())
 # Close the native Tables panel to give the original row its full width.
 # No source CSS/text is changed. Long names still must pass clipping checks.
 page.get_by_role('button',name='Tables',exact=True).click(timeout=allowance())
 metrics['select_columns_seconds']=round(time.perf_counter()-columns_started,6)
 # Observe rendered row, not hidden virtualized records left in DOM.
 day=date.fromisoformat(expected['expiration'])
 ready_text=[expected['identifier'],expected['raw_status'],f'{day.month}/{day.day}/{day.year%100:02d}, 12:00 AM',expected['name']]
 measured('bound_record_ready',lambda:page.wait_for_function('arg=>{const v=('+READ_ROW+')();return v&&JSON.stringify(v.columns)===JSON.stringify(arg.columns)&&JSON.stringify(v.headings)===JSON.stringify(arg.labels)&&JSON.stringify(v.texts)===JSON.stringify(arg.texts)&&v.clipped.every(x=>x===false)}',arg={'columns':list(COLUMNS),'labels':list(LABELS),'texts':ready_text},timeout=allowance()))
 return measured('screenshot_and_recheck',lambda:capture_ready(page,expected,deadline))
