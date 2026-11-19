"""Staging-only Tennessee extension demonstration with separate first/second routes.

The filing gateway is an in-process fake, with no network client, credentials,
configurable destinations, email or live filing code. Registry rules are not
changed. Nonpublic artifacts and all gateway outcomes are explicitly Demo only.
"""
from datetime import date, datetime, timedelta, timezone
import calendar
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import time
import uuid
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from psycopg.types.json import Jsonb
from deployment import tn_extension_documents as federal

PREFIX='/api/tn-extension-demo'
PORTAL='https://tncab.tnsos.gov/portal/portal-login-page'
SOURCE='https://tncab.tnsos.gov/portal/registered-charities-search'
FORM='https://sos-prod.tnsosgovfiles.com/s3fs-public/document/SS-6074.pdf?VersionId=z7ugMK57NV30ABCiNbBXqaU7pb4TWLHK'
AS_OF='2026-11-18'
SUGGESTED_REASON='Additional time is requested to complete and review the annual renewal and supporting financial information.'
SCHEMA='''
CREATE TABLE IF NOT EXISTS cc_tn_extension_demo_requests (
 id text PRIMARY KEY, account text NOT NULL, ein text NOT NULL,
 created double precision NOT NULL, updated double precision NOT NULL, data jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS cc_tn_extension_demo_owner ON cc_tn_extension_demo_requests(account,ein,created);
CREATE TABLE IF NOT EXISTS cc_tn_extension_demo_checks (
 account text NOT NULL, ein text NOT NULL, checked double precision NOT NULL, data jsonb NOT NULL,
 PRIMARY KEY(account,ein)
);
CREATE TABLE IF NOT EXISTS cc_tn_extension_demo_documents (
 id text PRIMARY KEY, account text NOT NULL, request_id text NOT NULL
 REFERENCES cc_tn_extension_demo_requests(id), kind text NOT NULL,
 created double precision NOT NULL, sha256 text NOT NULL, body bytea NOT NULL
);
'''

class Invalid(ValueError):pass
class Conflict(Invalid):pass

def ein(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{2}-?\d{7}',value):raise Invalid('Enter a valid EIN.')
    return value.replace('-','')

def day(value):
    try:return date.fromisoformat(value)
    except (TypeError,ValueError):raise Invalid('A verified calendar date is required.')

def local_day(now):return datetime.fromtimestamp(now,ZoneInfo('America/Chicago')).date()

def extension_number(facts):
    return 2 if facts.get('extension_number')==2 else 1

def eligibility(facts,today):
    if facts.get('refresh_error'):return {'eligible':False,'reasons':[facts['refresh_error']]}
    if facts.get('ineligibility_reason'):return {'eligible':False,'reasons':[facts['ineligibility_reason']]}
    reasons=[]
    for key,message in [('identity_verified','Organization identity is not verified.'),
        ('current_verified','Current Tennessee registration is not verified.'),
        ('period_verified','The applicable filing period is not verified.'),
        ('expiration_verified','The actual registration expiration is not verified.'),
        ('second_extension_verified' if extension_number(facts)==2 else 'first_extension_verified','Eligibility for this extension is not verified.')]:
        if facts.get(key) is not True:reasons.append(message)
    if extension_number(facts)==2 and facts.get('first_extension_granted_verified') is not True:
        reasons.append('The granted first extension and its expiration must be verified before requesting a second extension.')
    if facts.get('existing_filing') is True:reasons.append('An extension is already submitted to the test service for this period.' if facts.get('test_submission') else 'A renewal or extension is already on file for this period.')
    elif facts.get('existing_filing') is not False:reasons.append('Confirm whether a renewal or extension has already been submitted for this period.')
    try:
        expires=day(facts.get('expiration'))
        if extension_number(facts)==2:
            original=day(facts.get('original_expiration'))
            if not original<expires<=original+timedelta(days=90):reasons.append('The first-extension expiration is inconsistent with the original deadline.')
            if facts.get('return_type')=='990-N':reasons.append('Form 990-N cannot provide the IRS extension required for a second request.')
        if today>expires:reasons.append('The verified deadline has passed; this extension window is closed.')
        start=day(facts.get('period_start'));end=day(facts.get('period_end'))
        if start>end or end>=expires:reasons.append('The filing period and registration deadline conflict.')
    except Invalid:reasons.append('Verified filing-period or expiration dates are missing.')
    return {'eligible':not reasons,'reasons':reasons}

def eligibility_explanation(facts,today):
    """Explain verified state facts separately from federal submission eligibility."""
    number=extension_number(facts);maximum=60 if number==2 else 90;ordinal='second' if number==2 else 'first'
    result=dict(source=FORM,registry_source=facts.get('source') or SOURCE,extension_number=number,
        checked_at=facts.get('checked_at',''),fiscal_year_end=facts.get('period_end',''),
        registration_expiration=facts.get('expiration',''),maximum_days=maximum,
        checked_at_epoch=facts.get('checked_at_epoch'),account_check=facts.get('account_check'),
        maximum_requested_date='',approval_required=True,
        prior_filing_confirmation_required=facts.get('existing_filing') is None,
        federal=federal.federal_status(facts,today) if number==2 else None,summary='',basis=[])
    checks=[
        (facts.get('identity_verified') is True,f"Organization identity and CO number {facts.get('coid') or '(not verified)'} match the reviewed Tennessee record."),
        (facts.get('current_verified') is True,'The reviewed Tennessee registration is Active.'),
        (facts.get('period_verified') is True,f"The applicable fiscal period is {facts.get('period_start') or 'unverified'} to {facts.get('period_end') or 'unverified'}."),
        (facts.get('second_extension_verified' if number==2 else 'first_extension_verified') is True,f'The reviewed period and expiration support a {ordinal}-extension request, subject to confirming prior submissions.'),
    ]
    result['basis']=[message for verified,message in checks if verified]
    if facts.get('existing_filing') is False:result['basis'].append('The authorized filer confirmed that no renewal or extension has been submitted for this period; public lookup alone does not establish this.')
    elif facts.get('existing_filing') is None:result['basis'].append('A prior renewal or extension is not yet ruled out. The authorized filer must confirm before preparation.')
    try:
        end=day(facts.get('period_end'));expires=day(facts.get('expiration'))
        if facts.get('period_verified') and facts.get('expiration_verified'):
            result['basis'].append(f'The request window is open: today is on or before the verified {expires:%B %d, %Y} expiration.' if today<=expires else f'The request window is closed: the verified {expires:%B %d, %Y} expiration has passed.')
            result['maximum_requested_date']=(expires+timedelta(days=maximum)).isoformat()
            result['summary']=(f'The reviewed fiscal year ends {end:%B %d, %Y}; Tennessee registration expires {expires:%B %d, %Y}. '
                f'Tennessee may grant a {ordinal} extension of up to {maximum} days, through {expires+timedelta(days=maximum):%B %d, %Y}, if requested by the verified expiration date. '
                +('A second extension requires proof of an IRS extension. ' if number==2 else 'Attach an existing Form 8868 or a document stating the reason for the first extension. ')+
                'This is a request, not an approved extension.')
    except Invalid:pass
    if not result['summary']:result['summary']='A first extension cannot be offered until the current registration, filing period and actual expiration are verified.'
    return result

def reference_facts(record,today):
    """Generic rule for dated, reviewed registry references; no organization exceptions.

    A standard original deadline + same-month prior financial period establishes
    a candidate. A filer declaration is still needed about pending submissions.
    Nonstandard/extended dates, stale references and gaps stay disabled.
    """
    f={k:record.get(k,'') for k in ['ein','name','coid','address','phone','website','expiration','checked_at','source','identity_source','return_type','irs_street','irs_city_state_zip','irs_source']}
    f.update(identity_verified=False,current_verified=False,period_verified=False,expiration_verified=False,
        first_extension_verified=False,period_start='',period_end='',existing_filing=None,
        limitation='A dated public-source check cannot establish absence of pending filings. The authorized filer must confirm existing submissions. CO entry and required upload were inspected; later portal review, submission and receipts remain unverified.')
    try:
        expires=day(f['expiration']);reported=day(record.get('last_reported_period'));checked=day(f['checked_at'])
        fresh=0<=(today-checked).days<=1
        f.update(identity_verified=fresh and record.get('identity_verified') is True,
            current_verified=fresh and record.get('status')=='Active',expiration_verified=fresh)
        month=expires.month-1-6;year=expires.year+month//12;month=month%12+1
        end=date(year,month,calendar.monthrange(year,month)[1])
        standard=expires.day==calendar.monthrange(expires.year,expires.month)[1]
        prior=date(end.year-1,end.month,min(end.day,calendar.monthrange(end.year-1,end.month)[1]))
        if fresh and standard and reported==prior and end<=today<=expires:
            f.update(period_start=date(end.year-1+end.month//12,end.month%12+1,1).isoformat(),period_end=end.isoformat(),period_verified=True,first_extension_verified=True)
    except Invalid:pass
    return f

def public_facts(identifier,today=None):
    records=json.loads(Path(__file__).with_name('tn-extension-public-references.json').read_text(encoding='utf-8'))['records']
    record=next((r for r in records if r.get('ein')==identifier),{'ein':identifier})
    return reference_facts(record,today or day(AS_OF))

def demo_facts(identifier,name,scenario):
    if scenario not in {'open','closed','already-filed','unverified','second-open'}:raise Invalid('Unknown demo case.')
    source=public_facts(identifier)
    f=dict(ein=identifier,name=name,coid=source['coid'] or 'DEMO-CO100',
        address=source['address'] or '100 Demo Avenue, Nashville, TN 37201',phone=source['phone'],website=source['website'],
        expiration='2026-12-31',period_start='2025-07-01',period_end='2026-06-30',
        identity_verified=True,current_verified=True,period_verified=True,expiration_verified=True,
        first_extension_verified=True,existing_filing=False,
        source='Demo only: synthetic eligibility and period; NOT the real organization\'s verified extension window.')
    if scenario=='closed':f['expiration']='2026-11-01'
    if scenario=='already-filed':f['existing_filing']=True
    if scenario=='unverified':f['period_verified']=False
    if scenario=='second-open':
        f.update(extension_number=2,first_extension_granted_verified=True,second_extension_verified=True,
            original_expiration='2027-02-28',expiration='2027-05-29',period_start='2025-09-01',period_end='2026-08-31',
            return_type='990',irs_street=source.get('irs_street',''),irs_city_state_zip=source.get('irs_city_state_zip',''))
    return f

def document_pdf(title,fields):
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import simpleSplit,ImageReader
    out=io.BytesIO();p=canvas.Canvas(out,pagesize=(612,792));p.setTitle('Demo only - '+title)
    logo=Path(__file__).parents[1]/'web-staging/assets/compliance-express-extension.png'
    if logo.exists():p.drawImage(ImageReader(str(logo)),38,738,width=180,height=32,preserveAspectRatio=True,mask='auto')
    else:
        p.setFont('Helvetica-Bold',18);p.drawString(38,750,'Compliance Express')
    p.setFillColorRGB(.04,.16,.36);p.setFont('Helvetica-Bold',14);p.drawString(38,711,title)
    p.setFillColorRGB(.77,.15,.15);p.setFont('Helvetica-Bold',12);p.drawString(38,681,'DEMO ONLY - NOT FILED WITH TENNESSEE OR THE IRS')
    p.setFillColorRGB(.12,.12,.12);p.setFont('Helvetica',10);y=650
    for label,value in fields.items():
        for line in simpleSplit(str(label)+': '+str(value),'Helvetica',10,530):
            if y<85:
                p.showPage();p.setFont('Helvetica-Bold',12);p.drawString(38,750,'DEMO ONLY - '+title);p.setFont('Helvetica',10);y=720
            p.drawString(38,y,line);y-=15
        y-=5
    p.setFont('Helvetica',8);p.drawString(38,35,'www.compliance-express.com | info@compliance-express.com | Test service only')
    p.save();return out.getvalue()

class Service:
    def __init__(self,alerts,*,source_key="",session_binding="",source_version=""):
        self.alerts=alerts
        self.source_key=source_key;self.session_binding=session_binding;self.source_version=source_version
        # Explicit offline test dependency only. Production Alerts has no
        # reference provider; live eligibility must use fresh source evidence.
        self.reference_provider=getattr(alerts,'extension_reference_provider',None)
    def upgrade_draft(self,r):
        if r.get('scenario')=='verified' and r['status'] in {'Draft','Submission failed'}:
            r['workflow_version']=max(4,r.get('workflow_version',0))
            reference=public_facts(r['ein'],day(r['as_of']))
            keys=['coid','period_start','period_end','expiration']
            if all(reference.get(k)==r['facts'].get(k) for k in keys) and reference.get('identity_verified'):
                # Enrich only unsubmitted drafts with reviewed prefill provenance.
                # Preserve user edits and the original state eligibility facts.
                for k in ['return_type','irs_street','irs_city_state_zip','irs_source']:
                    if reference.get(k) and not r['facts'].get(k):r['facts'][k]=reference[k]
        return r
    def initialize(self,c):
        c.execute('SELECT pg_advisory_xact_lock(824527339)')
        c.execute(SCHEMA)
    def load(self,c,account,identifier):
        if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{32}',identifier):raise Invalid('Invalid draft.')
        row=c.execute('SELECT * FROM cc_tn_extension_demo_requests WHERE id=%s AND account=%s FOR UPDATE',(identifier,account)).fetchone()
        if not row:raise Invalid('Draft not found for this account.')
        return self.upgrade_draft(row['data'])
    def save(self,c,account,r,now):
        c.execute('UPDATE cc_tn_extension_demo_requests SET data=%s,updated=%s WHERE id=%s AND account=%s',(Jsonb(r),now,r['id'],account))
    def existing(self,c,account,identifier):
        rows=c.execute('SELECT data FROM cc_tn_extension_demo_requests WHERE account=%s AND ein=%s ORDER BY created DESC LIMIT 30',(account,identifier)).fetchall()
        return [x['data'] for x in rows]
    def public(self,r):
        self.upgrade_draft(r)
        fields=dict(r['fields'])
        if r['status'] in {'Draft','Submission failed'} and not fields.get('reason','').strip():fields['reason']=SUGGESTED_REASON
        return {k:v for k,v in r.items() if k!='gateway'} | {'fields':fields,'eligibility':eligibility(r['facts'],day(r['as_of'])),
            'portal_verified':False,'production_ready':False,'portal':PORTAL,'form_source':FORM,
            'extension_number':extension_number(r['facts']),
            'federal_required':extension_number(r['facts'])==2,
            'federal_check':federal.federal_status(r['facts'],day(r['as_of'])) if extension_number(r['facts'])==2 else None,
            'federal_fields':r.get('federal_fields') or federal.prefill(r['facts']),
            'eligibility_explanation':eligibility_explanation(r['facts'],day(r['as_of'])),
            'acknowledgment_provenance':r.get('acknowledgment_provenance'),
            'application_sha256':r.get('gateway',{}).get('application_sha256'),
            'confirmation_capture':r.get('confirmation_capture'),
            'receipt_method':'This demo polls its isolated test service. A matching receipt is stored and linked; it is not a Tennessee response. Tennessee also sends review outcomes by email, including returned-for-correction notices. Account history is read-only; actual filing-document and email retrieval are not connected. Receipt does not mean approval. No email is read or sent.',
            'support':r.get('support'),'portal_schema':'CO number; IRS Form 8868 or Other Documentation upload. Later steps unverified.'}
    def checked_facts(self,c,account,identifier,now):
        from deployment import tn_extension_refresh as refresh
        f=self.reference_provider(identifier,local_day(now)) if self.reference_provider else refresh.facts(self,c,account,identifier,now)
        row=c.execute('SELECT data FROM cc_tn_extension_demo_checks WHERE account=%s AND ein=%s',(account,identifier)).fetchone()
        answer=row['data'] if row else {}
        if (answer.get('period_end'),answer.get('expiration'),answer.get('source_checked_at'))==(f['period_end'],f['expiration'],f['checked_at']):
            f['existing_filing']={'yes':True,'no':False}.get(answer.get('answer'))
            if f.get('account_check',{}).get('requires_period_review') and answer.get('answer')=='no' and answer.get('records_not_for_period') is not True:f['existing_filing']=None
            f['filer_declaration']=answer
        for old in self.existing(c,account,identifier):
            if old.get('scenario')=='verified' and old['facts']['period_end']==f['period_end'] and old['status'] in {'Extension submitted','Receipt acknowledged','Submission unconfirmed'}:
                f['existing_filing']=True;f['test_submission']=True;break
        return f
    def create(self,c,account,p,now):
        identifier=ein(p.get('ein'));name=str(p.get('name','')).strip()
        if not 1<=len(name)<=200:raise Invalid('Organization name is required.')
        count=c.execute('SELECT count(*) AS n FROM cc_tn_extension_demo_requests WHERE account=%s',(account,)).fetchone()['n']
        if count>=100:raise Invalid('This demo account has reached its 100-draft limit.')
        scenario=p.get('scenario','open')
        if scenario=='verified':
            f=self.checked_facts(c,account,identifier,now)
            if not eligibility(f,local_day(now))['eligible']:raise Invalid('Check extensions and confirm prior filings before preparing the request.')
            name=f['name']
        else:f=demo_facts(identifier,name,scenario)
        # Reuse a prior submitted period rather than opening a duplicate draft.
        for old in self.existing(c,account,identifier):
            if old['scenario']==scenario and extension_number(old['facts'])==extension_number(f) and old['facts']['period_end']==f['period_end'] and old['status'] in {'Extension submitted','Receipt acknowledged','Submission unconfirmed'}:
                self.reconcile(c,account,old,now);return self.public(old)
            if scenario=='verified' and old['scenario']=='verified' and old['status'] in {'Draft','Submission failed'} and all(old['facts'].get(k)==f.get(k) for k in ['coid','period_start','period_end','expiration']):
                old['facts']=f;old['as_of']=local_day(now).isoformat();old['workflow_version']=4;old['prior_filing']='no'
                self.save(c,account,old,now)
                return self.prepare_first(c,account,old,now) if extension_number(f)==1 else self.public(old)
        r=dict(id=uuid.uuid4().hex,ein=identifier,scenario=scenario,demo_only=True,as_of=AS_OF,facts=f,
            status='Draft',approval='Not approved - demo only',documents={},gateway={},state_sends=0,
            fields=dict(name=name,coid=f['coid'],address=f['address'],phone=f['phone'],website=f['website'],
                contact='',contact_email='',title='',reason=SUGGESTED_REASON,requested_days='60' if extension_number(f)==2 else '90'),
            prior_filing='no' if scenario=='verified' else 'unknown',reviewed=False,authorized=False,
            workflow_version=4 if scenario in {'verified','second-open'} else 1)
        if scenario=='verified':r['as_of']=local_day(now).isoformat()
        c.execute('INSERT INTO cc_tn_extension_demo_requests VALUES (%s,%s,%s,%s,%s,%s)',(r['id'],account,identifier,now,now,Jsonb(r)))
        if scenario=='verified':return self.prepare_first(c,account,r,now)
        return self.find_federal(c,account,r,now) if extension_number(f)==2 else self.public(r)
    def edit(self,r,p):
        if r['status'] not in {'Draft','Submission failed'}:raise Conflict('The submitted application is immutable. Check its receipt before retrying.')
        fields=p.get('fields')
        if not isinstance(fields,dict) or set(fields)-set(r['fields']):raise Invalid('Unexpected form fields.')
        for k,v in fields.items():
            if not isinstance(v,str) or len(v)>600:raise Invalid('Invalid form field.')
            r['fields'][k]=v.strip()
        prior=p.get('prior_filing','unknown')
        if prior not in {'unknown','yes','no'}:raise Invalid('Confirm whether anything has already been filed.')
        r['prior_filing']=prior;r['reviewed']=p.get('reviewed') is True;r['authorized']=p.get('authorized') is True
    def review(self,r,now):
        if not eligibility(r['facts'],local_day(now) if r['scenario']=='verified' else day(r['as_of']))['eligible']:raise Invalid('The extension window or eligibility is not verified for this case.')
        if r['prior_filing']!='no':raise Invalid('Confirm that no renewal or extension is already submitted for this period.')
        if not r['reviewed'] or not r['authorized']:raise Invalid('Review the application and confirm that you are the authorized filer.')
        if r.get('workflow_version',0)>=2:
            if r['fields']['coid']!=r['facts']['coid']:raise Invalid('The CO number must match the verified Tennessee record.')
            support=r.get('support')
            if not support or support.get('tuple')!=self.filing_tuple(r):raise Invalid('Attach a validated matching supporting document before submitting.')
            if extension_number(r['facts'])==2 and (support['kind']!='8868' or not support.get('accepted')):
                raise Invalid('A second extension requires matching, accepted IRS extension evidence.')
            if extension_number(r['facts'])==1 and support['kind'] not in {'first-request','8868'}:
                raise Invalid('Attach a reason statement or matching filed IRS extension for the first request.')
            if support['kind']=='first-request' and support.get('reason')!=r['fields']['reason']:
                raise Invalid('Update the reason document after editing the statement, then review it before submitting.')
            if support['kind']=='8868' and not support.get('accepted'):raise Invalid('IRS acceptance must be verified before carrying Form 8868 forward.')
            return
        for k in ['name','coid','address','contact','contact_email','title','reason']:
            if not r['fields'][k]:raise Invalid('Complete the highlighted organization, contact, title and reason fields.')
        if r['fields']['coid']!=r['facts']['coid'] or r['fields']['name']!=r['facts']['name']:raise Invalid('Changing the registered identity requires reverification.')
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',r['fields']['contact_email']):raise Invalid('Confirm the filer email address.')
        if not re.fullmatch(r'\d{1,2}',r['fields']['requested_days']) or not 1<=int(r['fields']['requested_days'])<=90:raise Invalid('A first extension request must be between 1 and 90 days.')
    def fields(self,r):
        if r.get('workflow_version',0)>=2:
            support=r.get('support',{})
            return {'Request':'SECOND extension, up to 60 days' if extension_number(r['facts'])==2 else 'FIRST extension, up to 90 days',
                'Tennessee CO number':r['facts']['coid'],'Organization context (not an additional portal field)':r['facts']['name'],
                'EIN':r['ein'],'Applicable period beginning':r['facts']['period_start'],'Applicable period ending':r['facts']['period_end'],
                'Registration expiration':r['facts']['expiration'],'Supporting document kind':support.get('kind',''),
                'Exact attachment SHA256':support.get('sha256',''),'Source':r['facts']['source'],
                'Form basis':'Observed online CO entry and required supporting-document upload; later native portal steps unverified'}
        labels={'name':'Organization legal name','coid':'Tennessee CO number','address':'Mailing address','phone':'Phone','website':'Website',
            'contact':'Authorized filer','contact_email':'Filer email','title':'Filer title','reason':'Reason for extension','requested_days':'Days requested'}
        return {'Request':'FIRST extension; request only, not approval','EIN':r['ein'],
            'Applicable period beginning':r['facts']['period_start'],'Applicable period ending':r['facts']['period_end'],
            'Registration expiration':r['facts']['expiration'],
            'Requested date (not granted)':(day(r['facts']['expiration'])+timedelta(days=int(r['fields']['requested_days']))).isoformat(),
            'Prior filing answer':r['prior_filing'],'Eligibility source':r['facts']['source']} | {labels[k]:v for k,v in r['fields'].items()}
    def document(self,c,account,r,kind,body,now):
        identifier=uuid.uuid4().hex
        c.execute('INSERT INTO cc_tn_extension_demo_documents VALUES (%s,%s,%s,%s,%s,%s,%s)',(identifier,account,r['id'],kind,now,hashlib.sha256(body).hexdigest(),body))
        return PREFIX+'/documents/'+identifier
    def filing_tuple(self,r):return [r['ein'],r['facts']['coid'],r['facts']['period_start'],r['facts']['period_end'],r['facts'].get('return_type','')]
    def editable(self,r):
        if r['status'] not in {'Draft','Submission failed'}:raise Conflict('Submitted attachments and applications are immutable.')
    def prepare_first(self,c,account,r,now,reason=None):
        self.editable(r)
        if extension_number(r['facts'])!=1:raise Invalid('This is a second extension; matching IRS evidence is required instead.')
        if not eligibility(r['facts'],local_day(now) if r['scenario']=='verified' else day(r['as_of']))['eligible']:
            raise Invalid('The first-extension window or required registration facts are not verified.')
        statement=(r['fields'].get('reason') or SUGGESTED_REASON) if reason is None else reason
        if not isinstance(statement,str) or not 1<=len(statement.strip())<=600:raise Invalid('Enter a reason statement between 1 and 600 characters.')
        statement=statement.strip();r['fields']['reason']=statement;support=r.get('support',{})
        facts_sha=hashlib.sha256(json.dumps({k:r['facts'].get(k) for k in ['ein','name','coid','period_start','period_end','expiration']},sort_keys=True).encode()).hexdigest()
        if support.get('kind')=='first-request' and support.get('tuple')==self.filing_tuple(r) and support.get('reason')==statement and support.get('facts_sha')==facts_sha:return self.public(r)
        fields={'Request':'First Tennessee extension, up to 90 days; request only, not approval',
            'Organization':r['facts']['name'],'EIN':r['ein'],'CO number':r['facts']['coid'],
            'Period beginning':r['facts']['period_start'],'Period ending':r['facts']['period_end'],
            'Current expiration':r['facts']['expiration'],'Reason for extension':statement,
            'Supporting documentation':'Reason statement instead of IRS Form 8868, as specified by Tennessee. This TEST document has not been approved by the state.'}
        body=document_pdf('Reason statement for Tennessee first extension - Demo only',fields)
        digest=hashlib.sha256(body).hexdigest()
        original_url=r['documents'].get('first_request') or (support.get('url') if support.get('kind')=='first-request' and support.get('tuple')==self.filing_tuple(r) else None)
        if original_url:
            url=original_url;identifier=url.rsplit('/',1)[-1]
            c.execute('UPDATE cc_tn_extension_demo_documents SET body=%s,sha256=%s WHERE id=%s AND account=%s AND request_id=%s AND kind=%s',(body,digest,identifier,account,r['id'],'first-request'))
        else:url=self.document(c,account,r,'first-request',body,now)
        r['support']=dict(kind='first-request',tuple=self.filing_tuple(r),sha256=hashlib.sha256(body).hexdigest(),
            url=url,demo_only=True,label='Reason statement for first extension',reason=statement,facts_sha=facts_sha,accepted=False)
        r['documents']['support']=url;r['documents']['first_request']=url
        self.save(c,account,r,now);return self.public(r)
    def issue_support(self,c,account,r,kind,now):
        self.editable(r)
        if kind not in {'8868','other','mismatch'}:raise Invalid('Unknown test document type.')
        for old in r.get('issued_support',{}).values():
            if old.get('fixture_kind')==kind:return {'url':old['url'],'filename':'demo-only-'+kind+'.pdf','demo_only':True}
        fields=self.fields(r)|{'Test document':'Demo only - simulated existing supporting evidence, not a real filing or state determination'}
        if kind=='mismatch':fields['EIN']='999999999'
        body=document_pdf('Simulated '+('IRS Form 8868 acceptance packet' if kind=='8868' else 'supporting documentation'),fields)
        if kind=='8868':
            from pypdf import PdfReader,PdfWriter
            values=federal.prefill(r['facts'])|dict(books='Demo document custodian',phone='202-555-0100',tax_a='0',tax_b='0',tax_c='0')
            if not values['return_type']:raise Invalid('Verify the federal return type before generating a matching test packet.')
            form=federal.form8868(values,accepted=True);writer=PdfWriter();writer.append(PdfReader(io.BytesIO(body)));writer.append(PdfReader(io.BytesIO(form)))
            out=io.BytesIO();writer.write(out);body=out.getvalue()
        url=self.document(c,account,r,'test-support',body,now);digest=hashlib.sha256(body).hexdigest()
        metadata=dict(kind='8868' if kind=='8868' else 'other',fixture_kind=kind,accepted=kind=='8868',tuple=self.filing_tuple(r),sha256=digest,url=url,
            demo_only=True,label='Simulated accepted Form 8868 packet' if kind=='8868' else 'Simulated other supporting document')
        if kind=='mismatch':metadata['tuple'][0]='999999999'
        r.setdefault('issued_support',{})[digest]=metadata;self.save(c,account,r,now)
        return {'url':url,'filename':'demo-only-'+kind+'.pdf','demo_only':True}
    def upload_support(self,c,account,r,p,now):
        self.editable(r)
        try:body=base64.b64decode(p.get('body',''),validate=True)
        except (ValueError,TypeError):raise Invalid('Upload a valid test PDF.')
        if not 0<len(body)<=2*1024*1024 or not body.startswith(b'%PDF'):raise Invalid('Use a test PDF no larger than 2 MB.')
        digest=hashlib.sha256(body).hexdigest();proof=r.get('issued_support',{}).get(digest)
        if not proof:raise Invalid('This proof of concept accepts only its issued Demo only documents. Do not upload real tax documents.')
        if proof['tuple']!=self.filing_tuple(r):raise Invalid('The supporting document EIN, CO number, period or return type does not match.')
        r['support']=dict(proof);r['documents']['support']=proof['url'];self.save(c,account,r,now);return self.public(r)
    def find_federal(self,c,account,r,now):
        self.editable(r)
        r['federal_searched_at']=now
        for old in self.existing(c,account,r['ein']):
            support=old.get('support')
            if support and support['kind']=='8868' and support.get('accepted') and support['tuple']==self.filing_tuple(r):
                r['support']=dict(support);r['documents']['support']=support['url'];self.save(c,account,r,now)
                return self.public(r)|{'federal_found':True}
        self.save(c,account,r,now)
        return self.public(r)|{'federal_found':False}
    def irs_draft(self,c,account,r,p,now,submit=False):
        self.editable(r)
        if extension_number(r['facts'])!=2:raise Invalid('A first Tennessee extension does not require Form 8868.')
        if submit:
            if r.get('irs_submission'):return self.public(r)
            found=self.find_federal(c,account,r,now)
            if found['federal_found']:return found
        check=federal.federal_status(r['facts'],local_day(now))
        if not check['eligible']:raise Invalid(check['reason']+' A new Form 8868 cannot be prepared through this submission workflow; upload evidence of an existing timely filing if available.')
        incoming=p.get('federal_fields',{})
        if not isinstance(incoming,dict) or set(incoming)-set(federal.prefill(r['facts'])) or any(not isinstance(v,str) or len(v)>180 for v in incoming.values()):raise Invalid('Unexpected IRS form fields.')
        try:values=federal.validated_fields(r['facts'],incoming) if submit else federal.prefill(r['facts'])|incoming
        except ValueError as exc:raise Invalid(str(exc))
        # Draft identity/period cannot be changed by the client either.
        for k in ['ein','return_type','period_start','period_end']:
            if values[k]!=federal.prefill(r['facts'])[k]:raise Invalid('The IRS identity, period and return type must match the verified request.')
        if submit and (p.get('reviewed') is not True or p.get('authorized') is not True):raise Invalid('The authorized filer must review and explicitly submit the IRS TEST request.')
        r['federal_fields']=values
        body=federal.form8868(values,accepted=submit);url=self.document(c,account,r,'irs-filed' if submit else 'irs-draft',body,now)
        r['documents']['irs_filed' if submit else 'irs_draft']=url
        if submit:
            confirmation='DEMO-IRS-'+uuid.uuid4().hex[:12]
            receipt=document_pdf('IRS acceptance - simulated',{'Outcome':'Demo only - accepted by isolated TEST service; NOT an IRS response','EIN':r['ein'],'Return type':values['return_type'],
                'Period start':values['period_start'],'Period end':values['period_end'],'Confirmation':confirmation,'Form SHA256':hashlib.sha256(body).hexdigest()})
            acknowledgment=self.document(c,account,r,'irs-acceptance',receipt,now)
            r['documents']['irs_acceptance']=acknowledgment;r['irs_submission']=dict(confirmation=confirmation,submitted_at=now,sends=1,
                source='Isolated IRS test service',demo_only=True,accepted_at=now,form_sha256=hashlib.sha256(body).hexdigest())
            r['support']=dict(kind='8868',accepted=True,tuple=self.filing_tuple(r),sha256=hashlib.sha256(body).hexdigest(),url=url,demo_only=True,label='Form 8868 accepted by IRS TEST service',acceptance_url=acknowledgment)
            r['documents']['support']=url
        self.save(c,account,r,now);return self.public(r)
    def capture_confirmation(self,c,account,r,p,now):
        """Store the browser-rendered TEST confirmation card, never a live receipt."""
        if r.get('demo_only') is not True:raise Invalid('Only this isolated test confirmation may be captured.')
        if r['status'] not in {'Extension submitted','Receipt acknowledged'}:raise Invalid('A confirmed test submission is required before capturing its confirmation.')
        g=r.get('gateway',{})
        if (p.get('confirmation'),p.get('application_sha256'))!=(g.get('confirmation'),g.get('application_sha256')):raise Invalid('The confirmation capture does not match this submitted application.')
        old_capture=r['documents'].get('confirmation_screen')
        if old_capture and r.get('confirmation_capture',{}).get('format_version',0)>=2:return self.public(r)
        try:
            body=base64.b64decode(p.get('body',''),validate=True)
            if not 0<len(body)<=1024*1024 or not body.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError()
            from PIL import Image
            picture=Image.open(io.BytesIO(body))
            if not 100<=picture.width<=1800 or not 80<=picture.height<=1800:raise ValueError()
            picture.verify()
        except Exception as exc:
            raise Invalid('Use a valid bounded PNG capture of the test confirmation.') from exc
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        image=ImageReader(io.BytesIO(body));width,height=image.getSize();scale=min(540/width,640/height)
        out=io.BytesIO();pdf=canvas.Canvas(out,pagesize=(612,792));pdf.setTitle('Demo only - captured test submission confirmation')
        pdf.setFont('Helvetica-Bold',11);pdf.drawString(36,760,'DEMO ONLY - CAPTURE OF CHARITYCLARITY TEST CONFIRMATION')
        pdf.drawImage(image,36,725-height*scale,width=width*scale,height=height*scale,mask='auto')
        pdf.setFont('Helvetica',8);pdf.drawString(36,45,'Not a screenshot of the Tennessee website; not state approval.')
        pdf.drawString(36,32,'Compliance Express | www.compliance-express.com | info@compliance-express.com');pdf.save()
        r['documents']['confirmation_screen']=self.document(c,account,r,'confirmation-screen',out.getvalue(),now)
        r['confirmation_capture']=dict(source='Browser capture of the displayed CharityClarity test confirmation',demo_only=True,format_version=2,
            captured_at=now,confirmation=g['confirmation'],application_sha256=g['application_sha256'],image_sha256=hashlib.sha256(body).hexdigest())
        if old_capture:
            # Replace only the obsolete derived TEST screenshot. Submitted
            # applications, federal evidence and provider receipts are immutable.
            c.execute("DELETE FROM cc_tn_extension_demo_documents WHERE id=%s AND account=%s AND request_id=%s AND kind='confirmation-screen'",(old_capture.rsplit('/',1)[-1],account,r['id']))
        self.save(c,account,r,now);return self.public(r)
    def submit(self,c,account,r,p,now):
        if r['status'] in {'Extension submitted','Receipt acknowledged'}:return self.public(r)
        if r['status']=='Submission unconfirmed':raise Conflict('Submission unconfirmed. Check for a receipt before any retry.')
        self.edit(r,p);self.review(r,now)
        if r.get('workflow_version',0)>=2:
            support=r['support'];proof=c.execute('SELECT sha256 FROM cc_tn_extension_demo_documents WHERE id=%s AND account=%s',(support['url'].rsplit('/',1)[-1],account)).fetchone()
            if not proof or proof['sha256']!=support['sha256']:raise Invalid('The exact supporting document is unavailable or changed. Prepare and review it again before submitting.')
        if r['scenario']=='verified':
            f=self.checked_facts(c,account,r['ein'],now)
            if not eligibility(f,local_day(now))['eligible'] or any(f.get(k)!=r['facts'].get(k) for k in ['coid','period_start','period_end','expiration']):raise Invalid('Recheck extensions: the source, period, CO number, deadline or prior-filing answer changed.')
        for old in self.existing(c,account,r['ein']):
            if old['id']!=r['id'] and extension_number(old['facts'])==extension_number(r['facts']) and (old['facts']['coid'],old['facts']['period_start'],old['facts']['period_end'])==(r['facts']['coid'],r['facts']['period_start'],r['facts']['period_end']) and old['status'] in {'Extension submitted','Receipt acknowledged','Submission unconfirmed'}:
                raise Conflict('Another application for this period is already submitted or unconfirmed. Review it before retrying.')
        behavior=p.get('test_response','delayed')
        if behavior not in {'immediate','delayed','timeout','failed','returned'}:raise Invalid('Only the built-in test service is available.')
        r['state_sends']+=1
        if behavior=='failed':
            r['status']='Submission failed';r['failure']='Test service confirmed failure before accepting the filing. Draft retained.'
        else:
            confirmation='DEMO-TN-'+uuid.uuid4().hex[:12]
            body=document_pdf('Tennessee extension application - submitted TEST copy',self.fields(r)|{'Confirmation':confirmation,'Submitted UTC':datetime.fromtimestamp(now,timezone.utc).isoformat()})
            url=self.document(c,account,r,'application',body,now)
            r['gateway']=dict(confirmation=confirmation,ein=r['ein'],coid=r['facts']['coid'],period_start=r['facts']['period_start'],period_end=r['facts']['period_end'],
                application_sha256=hashlib.sha256(body).hexdigest(),submitted_at=now,ack_at=now+(0 if behavior=='immediate' else 15),document=url)
            # Persist the TEST provider response at submission. Time passing alone
            # cannot acknowledge a new workflow without this exact matching record.
            if r.get('workflow_version',0)>=3:
                r['gateway']['receipt']=dict(source='Isolated Tennessee test service',demo_only=True,account=account,
                    confirmation=confirmation,ein=r['ein'],coid=r['facts']['coid'],period_start=r['facts']['period_start'],period_end=r['facts']['period_end'],
                    application_sha256=r['gateway']['application_sha256'],available_at=r['gateway']['ack_at'])
            r.update(submitted_at=now,confirmation=confirmation,status='Submission unconfirmed' if behavior=='timeout' else 'Extension submitted')
            if behavior=='returned':r['gateway']['return_for_correction']=True
            r['documents']['application']=url
            if behavior in {'immediate','returned'}:
                if behavior=='returned':
                    r['gateway']['ack_at']=now
                    if r['gateway'].get('receipt'):r['gateway']['receipt']['available_at']=now
                self.reconcile(c,account,r,now)
        self.save(c,account,r,now);return self.public(r)
    def reconcile(self,c,account,r,now):
        g=r.get('gateway')
        if not g:return
        row=c.execute('SELECT * FROM cc_tn_extension_demo_documents WHERE id=%s AND account=%s',(g['document'].rsplit('/',1)[-1],account)).fetchone()
        if not row or (g.get('ein'),g.get('coid'),g.get('period_start'),g.get('period_end'),g.get('application_sha256'))!=(r['ein'],r['facts']['coid'],r['facts']['period_start'],r['facts']['period_end'],row['sha256']):return
        if r['status']=='Submission unconfirmed':r['status']='Extension submitted'
        proof=g.get('receipt')
        if r.get('workflow_version',0)>=3:
            if not proof or proof.get('source')!='Isolated Tennessee test service' or proof.get('demo_only') is not True:return
            if tuple(proof.get(k) for k in ['account','confirmation','ein','coid','period_start','period_end','application_sha256','available_at'])!=(account,g['confirmation'],r['ein'],r['facts']['coid'],r['facts']['period_start'],r['facts']['period_end'],row['sha256'],g['ack_at']):return
        if now>=g['ack_at'] and not r['documents'].get('acknowledgment'):
            body=document_pdf('Tennessee acknowledgment - simulated',self.fields(r)|{'Outcome':'Receipt acknowledged by TEST service. NOT state approval.',
                'Confirmation':g['confirmation'],'Submitted UTC':datetime.fromtimestamp(g['submitted_at'],timezone.utc).isoformat(),
                'Acknowledged UTC':datetime.fromtimestamp(now,timezone.utc).isoformat(),'Exact submitted application SHA256':g['application_sha256']})
            r['documents']['acknowledgment']=self.document(c,account,r,'acknowledgment',body,now)
            r.update(acknowledged_at=now,status='Receipt acknowledged')
            r['acknowledgment_provenance']=dict(source='Isolated Tennessee test service',demo_only=True,
                received_at=now,confirmation=g['confirmation'],application_sha256=g['application_sha256'],
                receipt_url=r['documents']['acknowledgment'],matched_fields=['Account','EIN','CO number','Filing period','Application hash','Confirmation'])
        if r['documents'].get('acknowledgment') and g.get('return_for_correction') and not r.get('state_review'):
            r['state_review']=dict(outcome='Returned for correction',demo_only=True,received_at=now,confirmation=g['confirmation'],
                reason='Simulated reviewer requests a more specific reason statement. Correct the existing filing; do not create a duplicate.',source='Simulated Tennessee review email')
            r['approval']='Returned for correction - NOT approved - demo only'
            r['documents']['state_response']=self.document(c,account,r,'state-response',document_pdf('Returned for correction - simulated email',r['state_review']),now)
        self.save(c,account,r,now)
    def dispatch(self,c,account,p,now):
        from deployment import tn_extension_refresh as refresh
        action=p.get('action')
        if action=='begin-check':return refresh.begin(self,c,account,p,now)
        if action=='refresh-failed':
            refresh.failure(self,c,account,p,now)
            return self.dispatch(c,account,dict(action='status',ein=p['ein']),now)
        if action=='account-observation':
            refresh.account_observation(self,c,account,p,now)
            return self.dispatch(c,account,dict(action='status',ein=p['ein']),now)
        if action in {'check','status'}:
            identifier=ein(p.get('ein'));facts=self.checked_facts(c,account,identifier,now);rows=self.existing(c,account,identifier)
            if action=='check' and not self.reference_provider and not refresh.stored(c,account,identifier).get('fresh'):
                facts['refresh_error']='Refresh CharityClarity to load the current extension checker, then click Check for extensions.'
            for r in rows:self.reconcile(c,account,r,now)
            return dict(demo_only=True,state='TN',facts=facts,eligibility=eligibility(facts,local_day(now)),
                eligibility_explanation=eligibility_explanation(facts,local_day(now)),
                requests=[self.public(r) for r in rows],supported_states=['TN'],needs_prior_confirmation=facts['period_verified'] and facts['existing_filing'] is None)
        if action=='confirm-prior':
            identifier=ein(p.get('ein'));answer=p.get('answer')
            if answer not in {'yes','no','unknown'}:raise Invalid('Confirm whether anything has already been submitted for this period.')
            f=self.checked_facts(c,account,identifier,now)
            if not f['period_verified']:raise Invalid('The original period and deadline must be verified first.')
            if f.get('refresh_error'):raise Invalid(f['refresh_error'])
            records=f.get('account_check',{}).get('records',[])
            if answer=='no' and f.get('account_check',{}).get('requires_period_review') and p.get('records_not_for_period') is not True:raise Invalid('Review the matching account filings and confirm they do not cover this period, or correct the existing request.')
            declaration=dict(answer=answer,account=account,answered_at=now,period_end=f['period_end'],expiration=f['expiration'],source_checked_at=f['checked_at'],records_not_for_period=p.get('records_not_for_period') is True)
            data=refresh.stored(c,account,identifier);data.update(declaration)
            refresh.save(c,account,identifier,data,now)
            return self.dispatch(c,account,dict(action='check',ein=identifier),now)
        if action=='prepare':
            identifier=ein(p.get('ein'));f=self.checked_facts(c,account,identifier,now)
            return self.create(c,account,dict(ein=identifier,name=f['name'],scenario='verified'),now)
        if action=='create':return self.create(c,account,p,now)
        r=self.load(c,account,p.get('id'))
        if action=='prepare-first':return self.prepare_first(c,account,r,now,p.get('reason'))
        if action=='attach-demo-evidence':
            issued=self.issue_support(c,account,r,'8868',now)
            raw=c.execute('SELECT body FROM cc_tn_extension_demo_documents WHERE id=%s AND account=%s',(issued['url'].rsplit('/',1)[-1],account)).fetchone()['body']
            return self.upload_support(c,account,r,dict(body=base64.b64encode(raw).decode()),now)
        if action=='test-document':return self.issue_support(c,account,r,p.get('kind'),now)
        if action=='upload-support':return self.upload_support(c,account,r,p,now)
        if action=='find-federal':return self.find_federal(c,account,r,now)
        if action in {'irs-draft','irs-submit'}:return self.irs_draft(c,account,r,p,now,submit=action=='irs-submit')
        if action=='capture-confirmation':return self.capture_confirmation(c,account,r,p,now)
        if action=='save':self.edit(r,p);self.save(c,account,r,now);return self.public(r)
        if action=='submit':return self.submit(c,account,r,p,now)
        if action=='receipt':self.reconcile(c,account,r,now);return self.public(r)
        raise Invalid('Unsupported extension action.')

def handle(alerts,handler,*,origin,include_body=True,source_key="",source_version=""):
    headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
    try:
        entry=urlsplit(handler.path)
        from deployment.tn_extension_refresh import session_binding
        service=Service(alerts,source_key=source_key,session_binding=session_binding(handler),source_version=source_version)
        with alerts.transaction() as c:
            account=alerts.account(c,handler)
            if not account:return handler._send_json(403,{'error':'Sign into your existing CharityClarity account to use the extension demo.','sign_in':'/alerts'},headers)
            service.initialize(c);now=time.time()
            if handler.command in {'GET','HEAD'}:
                match=re.fullmatch(re.escape(PREFIX)+r'/documents/([a-f0-9]{32})',entry.path)
                if not match:return handler._send_json(404,{'error':'Not found.'},headers)
                row=c.execute('SELECT * FROM cc_tn_extension_demo_documents WHERE id=%s AND account=%s',(match[1],account)).fetchone()
                if not row:return handler._send_json(404,{'error':'Document not found.'},headers)
                body=bytes(row['body']);handler.send_response(200)
                filename={'first-request':'Reason statement - Demo only.pdf','irs-filed':'Filed Form 8868 - Demo only.pdf','irs-acceptance':'IRS acceptance - Demo only.pdf'}.get(row['kind'],'Tennessee extension document - Demo only.pdf')
                for k,v in (headers|{'Content-Type':'application/pdf','Content-Disposition':'inline; filename="'+filename+'"','Content-Length':str(len(body))}).items():handler.send_header(k,v)
                handler.end_headers()
                if include_body:handler.wfile.write(body)
                return
            if handler.command!='POST' or handler.headers.get('Origin')!=origin:return handler._send_json(403,{'error':'Invalid request origin.'},headers)
            if handler.headers.get('Content-Type','').split(';')[0]!='application/json':raise Invalid('JSON input required.')
            n=int(handler.headers.get('Content-Length','0'))
            if not 0<n<=2900000:raise Invalid('Invalid request size.')
            p=json.loads(handler.rfile.read(n))
            if not isinstance(p,dict) or any(k in p for k in ['endpoint','url','live','account','owner','facts','as_of']):raise Invalid('Only this account and the fixed test service are supported.')
            if p.get('action')=='create':raise Invalid('Use Check for extensions and the Tennessee File Extension button.')
            result=service.dispatch(c,account,p,now)
        return handler._send_json(200,result,headers)
    except Conflict as exc:return handler._send_json(409,{'error':str(exc)},headers)
    except (Invalid,ValueError,TypeError,KeyError,UnicodeError) as exc:return handler._send_json(400,{'error':str(exc)[:240]},headers)
    except Exception:return handler._send_json(503,{'error':'Extension demo temporarily unavailable. Check for a receipt before retrying a submission.'},headers)
