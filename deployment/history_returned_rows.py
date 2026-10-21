"""Optional public source-row summaries. No source I/O, identity or status decisions."""
import datetime,json,re

MAX_ROWS=100
MAX_BYTES=24000
FIELDS=frozenset('name fullname organizationname orgname legalname csllegalname businessname title entityname entitytradename charityname licenseename identifier id objectid customernumber orgid licenseid charityid number licensenumber licenseregistration registrationnumber licenseregistrationnumber registrationlicensenumber registrationid entitynumber credential conumber status rawstatus standing licensestatus expiration expirationdate expiry expirydate granteddate issueddate issuedate initialissuedate renewaldate lastfilingdate fiscalyearend fiscalyearenddate registrationdate effectivedate licenseenddate licensestartdate datarefreshedon address address1 address2 street street1 street2 location businessaddress mailingaddress premiseaddress premiseindc city state region zip zipcode postalcode country registrationtype licensetype licensecategory businessactivity credentialtype'.split())

ADDRESS_FIELDS=frozenset('address address1 address2 street street1 street2 location businessaddress mailingaddress premiseaddress premiseindc city state region zip zipcode postalcode country'.split())

def public_field_column(label):
 """Presentation only: retain the original source label and value unchanged."""
 key=re.sub(r'[^a-z0-9]','',label.casefold())
 if key in ADDRESS_FIELDS:return 2
 if 'date' in key or key in {'status','rawstatus','standing','licensestatus','expiration','expiry','fiscalyearend','datarefreshedon'}:return 1
 return 0

def wi_text_records(text):
 """Read the existing WI reader's six-column table, never issue a query.

 Do not turn an arbitrary line containing a credential into a source record.
 All six original cells are retained; links become their visible text only.
 An ambiguous/truncated table returns None rather than a fabricated count.
 """
 if not isinstance(text,str):return None
 if not re.search(r'Organization\s+Search\s+Results|Search\s+Parameters|Charitable\s+Organization',text,re.I):return None
 totals=re.findall(r'Total\s+Search\s+Results\s*:\s*(\d+)',text,re.I)
 rows=[]
 for line in text.splitlines():
  if not line.strip().startswith('|'):continue
  cells=[c.strip() for c in line.strip().strip('|').split('|')]
  if not cells or not re.fullmatch(r'\d+-800',cells[0]):continue
  if len(cells)!=6 or not re.fullmatch(r'Charitable\s+Organization',cells[1],re.I):return None
  def visible(cell):
   match=re.fullmatch(r'\[([^\]]+)\]\([^\s)]+\)',cell)
   return match.group(1) if match else '' if cell.startswith('[') else cell
  values=[visible(c) for c in cells]
  if not values[2]:return None
  rows.append(dict(zip(('License Number','Credential Type','Name','Location','Granted Date','Expiration Date'),values)))
 if rows:
  # A no-results marker alongside rows is contradictory, not a zero response.
  if re.search(r'There\s+are\s+no\s+query\s+results|No\s+query\s+results',text,re.I):return None
  if len(totals)!=1 or int(totals[0])!=len(rows):return None
  return rows
 if re.search(r'There\s+are\s+no\s+query\s+results|No\s+query\s+results',text,re.I) and (not totals or totals==['0']):return []
 return None

def returned_record_details(evidence):
 """Preserve source row order/duplicates/blanks; strictly exclude private fields."""
 if not isinstance(evidence,dict) or not isinstance(evidence.get('rows'),list):return {}
 rows=evidence['rows'];headers=evidence.get('headers');records=[];size=0;unsupported=0
 if not rows:return {}
 for i,row in enumerate(rows[:MAX_ROWS]):
  if isinstance(row,dict):items=list(row.items())
  elif isinstance(row,list) and isinstance(headers,list) and len(headers)==len(row):items=list(zip(headers,row))
  else:unsupported+=1;continue
  fields=[]
  for label,value in items:
   if not isinstance(label,str) or len(label)>100 or re.sub(r'[^a-z0-9]','',label.casefold()) not in FIELDS:continue
   if isinstance(value,(datetime.datetime,datetime.date)):value=value.isoformat()
   if value is None:value=''
   if not isinstance(value,(str,int,float)) or isinstance(value,bool):continue
   value=str(value)
   if len(value)>500:value=value[:500]+' [value truncated]'
   fields.append([label,value])
   if len(fields)==16:break
  if not fields:unsupported+=1;continue
  record={'row_number':i+1,'fields':fields};cost=len(json.dumps(record,ensure_ascii=False).encode())
  if size+cost>MAX_BYTES:break
  records.append(record);size+=cost
 return {'returned_records':records,'returned_records_not_listed':len(rows)-len(records),'returned_records_limit':MAX_ROWS,
         'returned_records_note':('Some returned records could not be listed within the supported field/size limits.' if len(records)<len(rows) else '')}

def validate_returned_details(entry):
 records=entry.get('returned_records')
 if records is None:return
 count=entry.get('returned_rows')
 if not isinstance(records,list) or len(records)>MAX_ROWS or type(count) is not int:raise ValueError('Invalid returned record detail')
 seen=[]
 for record in records:
  if not isinstance(record,dict) or set(record)!={'row_number','fields'} or type(record['row_number']) is not int or not 1<=record['row_number']<=count:raise ValueError('Invalid returned row order')
  fields=record['fields']
  if not isinstance(fields,list) or not 1<=len(fields)<=16:raise ValueError('Invalid public source fields')
  for pair in fields:
   if not isinstance(pair,list) or len(pair)!=2 or any(not isinstance(x,str) for x in pair) or len(pair[0])>100 or len(pair[1])>520 or re.sub(r'[^a-z0-9]','',pair[0].casefold()) not in FIELDS:raise ValueError('Unexpected public source field')
  seen.append(record['row_number'])
 if seen!=sorted(set(seen)) or entry.get('returned_records_not_listed')!=count-len(records):raise ValueError('Returned record count changed')
 if len(json.dumps(records,ensure_ascii=False).encode())>MAX_BYTES+MAX_ROWS*4:raise ValueError('Returned detail too large')

def drop_returned_details(record):
 """Drop optional row details before mature token/history limits are applied."""
 changed=False
 entries=[item.get('search_receipt',{}) for item in record.get('completed',[])]+record.get('queries',[])
 for receipt in entries:
  for key in list(receipt):
   if key.startswith('returned_records'):
    receipt.pop(key);changed=True
 return changed
