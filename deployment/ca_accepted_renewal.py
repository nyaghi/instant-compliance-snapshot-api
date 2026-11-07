"""Reconcile one selected CA registration with an accepted, same-EIN RRF-1."""
import json
import re
import time
from datetime import date
from urllib.parse import urlencode


def accepted_period(master, entity, registration, rows, ein):
    if not isinstance(rows,list) or len(rows)>=200:
        return None
    confirmed=[]
    for row in rows:
        if not isinstance(row,dict):return None
        if (row.get('status')!='Accepted' or row.get('formType')!='Form RRF-1'
            or row.get('registrationMethod')!='Renewal'):continue
        if (str((row.get('relatedEntity') or {}).get('id'))!=str(entity.get('id'))
            or str((row.get('relatedRegistration') or {}).get('id'))!=str(registration.get('id'))
            or str(row.get('stateCharityRegistrationNumber'))!=str(registration.get('registrationNumber'))
            or master.canonical_ein_digits(row.get('fein',''))!=master.canonical_ein_digits(ein)
            or master.complete_name_identity_key(row.get('officialName',''))!=master.complete_name_identity_key(master.checker.ca_evoke_display_name(entity))
            or row.get('isShortFiscalYear')!='No' or row.get('countOfOpenDeficiencies')!=0
            or row.get('newReportingStatus')!='Current' or row.get('newRegistrationStatus')!='Registered'):
            continue
        try:
            start=date.fromisoformat(row['fullAccountingPeriodBeginning'])
            end=date.fromisoformat(row['fullAccountingPeriodEnding'])
            received=date.fromisoformat(row['recievedDate'])
        except (ValueError,KeyError,TypeError):continue
        if not 364 <= (end-start).days <= 366 or not start<end<=received<=date.today():continue
        rid=str(row.get('id') or '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',rid):continue
        confirmed.append({'id':rid,'ein':master.canonical_ein_digits(ein),
            'name':master.checker.ca_evoke_display_name(entity),'registration':str(registration['registrationNumber']),
            'registration_id':str(registration['id']),'entity_id':str(entity['id']),
            'period_start':start.isoformat(),'period_end':end.isoformat(),'received':received.isoformat(),
            'status':'Accepted','url':'https://ca-rcf.evokeplatform.com/app/publicPortal/requestDetailsRenewal/'+rid})
    if not confirmed:return None
    latest=max(r['period_end'] for r in confirmed)
    tops=[r for r in confirmed if r['period_end']==latest]
    if len({r['period_start'] for r in tops})!=1:return None
    return max(tops,key=lambda r:r['received'])


def reconcile(master,org,result,entity,registrations):
    if (not result.success or result.status not in {'Delinquent',master.checker.STATUS_DELINQUENT}
        or not isinstance(entity,dict) or not isinstance(registrations,list)
        or len(master.canonical_ein_digits(org.ein))!=9
        or master.canonical_ein_digits(entity.get('fein',''))!=master.canonical_ein_digits(org.ein)):
        return
    selected=[r for r in registrations if str(r.get('registrationNumber',''))==str(result.matched_registry_identifier)]
    if len(selected)!=1:return
    reg=selected[0]
    if (reg.get('registrationType')!='Charitable Organization' or reg.get('registrationStatus')!='Registered'
        or reg.get('reportingStatus')!='Current' or reg.get('complianceStatus')
        or re.search(r'suspended|revoked|enforcement|cease|closed|withdrawn',str(entity.get('entityStatus','')),re.I)):
        return
    try:
        old=date.fromisoformat(reg['currentExpirationDate'])
        if old>=date.today():return
        query={'order':'registrationYear DESC','skip':0,'where':{'and':[
            {'registrationMethod':'Renewal'},{'relatedRegistration.id':str(reg['id'])}]},'limit':200}
        url=master.checker.CA_EVOKE_API_ROOT+'/data/objects/requests/instances?'+urlencode({'filter':json.dumps(query,separators=(',',':'))})
        from deployment.state_snapshots import DEADLINE
        deadline=min(time.monotonic()+8,DEADLINE.get()-1)
        if deadline<=time.monotonic():return
        payload=json.loads(master.identity_fetch(url,deadline))
        proof=accepted_period(master,entity,reg,payload,org.ein)
        if not proof or date.fromisoformat(proof['period_end'])<old:return
        end=date.fromisoformat(proof['period_end'])
        due,rule=master.filing_due_date('CA',end.year+1,(end.month,end.day))
        if due is None:return
        result.status=master.status_from_calendar_date(due)
        result.status_reason='CA_ACCEPTED_RENEWAL_NEXT_CYCLE'
        result.computed_due_date=due.isoformat()
        result.next_required_period=master.add_months_preserving_end_of_month(end,12).isoformat()
        proof['computed_due_date']=due.isoformat()
        result._cc_ca_accepted_renewal=proof
        result.raw_status_text += ' | Accepted RRF-1 FYE: '+end.isoformat()+' | Calculated next filing due: '+due.isoformat()
        result.source_note=('The selected registration header has an older expiration date. The same-EIN RRF-1 was accepted '
            'for the fiscal year ending '+end.isoformat()+'. The next unfiled annual period is due '+due.isoformat()+' '+rule+
            '; this is a calculated filing deadline, not a replacement expiration date published by the registry. '
            'The header and accepted renewal are retained as evidence.')
    except Exception as exc:
        result._cc_ca_renewal_diagnostic={'outcome':'unavailable','error_type':type(exc).__name__}


def preserves(result):
    proof=getattr(result,'_cc_ca_accepted_renewal',None)
    return bool(result.state=='CA' and result.success and getattr(result,'status_reason','')=='CA_ACCEPTED_RENEWAL_NEXT_CYCLE'
        and isinstance(proof,dict) and proof.get('status')=='Accepted'
        and proof.get('ein')==re.sub(r'\D','',str(result.ein))
        and proof.get('name')==result.matched_registry_name
        and proof.get('registration')==str(result.matched_registry_identifier)
        and proof.get('computed_due_date')==result.computed_due_date)


def capture_renewal(page,run,proof,stop,fact):
    """Second original image, same capture deadline; never reconstruct source pixels."""
    if not proof or time.monotonic()+5>=stop:return
    url=proof['url'];fact['renewal_capture']='navigation'
    timeout=lambda:max(1,int((stop-time.monotonic()-1)*1000))
    response=page.goto(url,wait_until='domcontentloaded',timeout=timeout())
    if response is None or response.status!=200 or page.url!=url:return
    ending=page.get_by_text('Full Accounting Period Ending',exact=False)
    ending.wait_for(state='visible',timeout=timeout())
    def bound(text):
        flat=re.sub(r'\s+',' ',text)
        fmt=lambda v:date.fromisoformat(v).strftime('%m/%d/%Y')
        return (re.search(r'Renewal\s*-\s*Form RRF-1\s+Accepted\b',flat)
            and proof['name'] in flat and proof['registration'] in flat
            and proof['ein'] in re.sub(r'\D','',flat)
            and re.search(r'Full Accounting Period Beginning\s*\*?\s*'+re.escape(fmt(proof['period_start'])),flat)
            and re.search(r'Full Accounting Period Ending\s*\*?\s*'+re.escape(fmt(proof['period_end'])),flat))
    text=page.inner_text('body',timeout=timeout())
    if not bound(text):fact['renewal_capture']='identity_or_period_rejected';return
    box=ending.locator('..').locator('..').bounding_box()
    if not box or not 100<box['y']+box['height']<5000:return
    raw=page.screenshot(type='jpeg',quality=80,full_page=True,
        clip={'x':0,'y':0,'width':1600,'height':int(box['y']+box['height']+25)},timeout=timeout())
    if page.url!=url or not bound(page.inner_text('body',timeout=timeout())):return
    before=len(run.documents)
    run.document(url,raw,'image',text[:20000],note='Original accepted same-EIN RRF-1, through its complete accounting-period fields; accompanies the retained registration header.')
    fact['renewal_capture']='captured' if len(run.documents)>before else 'archive_rejected'
