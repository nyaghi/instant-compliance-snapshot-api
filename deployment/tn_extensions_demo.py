"""Staging-only Tennessee first-extension demonstration.

The filing gateway is an in-process fake, with no network client, credentials,
configurable destinations, email or live filing code. Registry rules are not
changed. Nonpublic artifacts and all gateway outcomes are explicitly Demo only.
"""
from datetime import date, datetime, timedelta, timezone
import calendar
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

PREFIX='/api/tn-extension-demo'
PORTAL='https://tncab.tnsos.gov/portal/portal-login-page'
SOURCE='https://tncab.tnsos.gov/portal/registered-charities-search'
FORM='https://sos-prod.tnsosgovfiles.com/s3fs-public/document/SS-6074.pdf?VersionId=z7ugMK57NV30ABCiNbBXqaU7pb4TWLHK'
AS_OF='2026-11-18'
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

def eligibility(facts,today):
    reasons=[]
    for key,message in [('identity_verified','Organization identity is not verified.'),
        ('current_verified','Current Tennessee registration is not verified.'),
        ('period_verified','The applicable filing period is not verified.'),
        ('expiration_verified','The actual registration expiration is not verified.'),
        ('first_extension_verified','Eligibility for a first extension is not verified.')]:
        if facts.get(key) is not True:reasons.append(message)
    if facts.get('existing_filing') is True:reasons.append('An extension is already submitted to the test service for this period.' if facts.get('test_submission') else 'A renewal or extension is already on file for this period.')
    elif facts.get('existing_filing') is not False:reasons.append('Confirm whether a renewal or extension has already been submitted for this period.')
    try:
        expires=day(facts.get('expiration'));start=day(facts.get('period_start'));end=day(facts.get('period_end'))
        if start>end or end>=expires:reasons.append('The filing period and registration deadline conflict.')
        if today>expires:reasons.append('The registration deadline has passed; the first-extension window is closed.')
    except Invalid:reasons.append('Verified filing-period or expiration dates are missing.')
    return {'eligible':not reasons,'reasons':reasons}

def reference_facts(record,today):
    """Generic rule for dated, reviewed registry references; no organization exceptions.

    A standard original deadline + same-month prior financial period establishes
    a candidate. A filer declaration is still needed about pending submissions.
    Nonstandard/extended dates, stale references and gaps stay disabled.
    """
    f={k:record.get(k,'') for k in ['ein','name','coid','address','phone','website','expiration','checked_at','source','identity_source']}
    f.update(identity_verified=False,current_verified=False,period_verified=False,expiration_verified=False,
        first_extension_verified=False,period_start='',period_end='',existing_filing=None,
        limitation='A dated public-source check cannot establish absence of pending filings. The authorized filer must confirm existing submissions. Portal-specific filing steps remain unverified.')
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
    if scenario not in {'open','closed','already-filed','unverified'}:raise Invalid('Unknown demo case.')
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
    def __init__(self,alerts):self.alerts=alerts
    def initialize(self,c):
        c.execute('SELECT pg_advisory_xact_lock(824527339)')
        c.execute(SCHEMA)
    def load(self,c,account,identifier):
        if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{32}',identifier):raise Invalid('Invalid draft.')
        row=c.execute('SELECT * FROM cc_tn_extension_demo_requests WHERE id=%s AND account=%s FOR UPDATE',(identifier,account)).fetchone()
        if not row:raise Invalid('Draft not found for this account.')
        return row['data']
    def save(self,c,account,r,now):
        c.execute('UPDATE cc_tn_extension_demo_requests SET data=%s,updated=%s WHERE id=%s AND account=%s',(Jsonb(r),now,r['id'],account))
    def existing(self,c,account,identifier):
        rows=c.execute('SELECT data FROM cc_tn_extension_demo_requests WHERE account=%s AND ein=%s ORDER BY created DESC LIMIT 30',(account,identifier)).fetchall()
        return [x['data'] for x in rows]
    def public(self,r):
        return {k:v for k,v in r.items() if k!='gateway'} | {'eligibility':eligibility(r['facts'],day(r['as_of'])),
            'portal_verified':False,'production_ready':False,'portal':PORTAL,'form_source':FORM}
    def checked_facts(self,c,account,identifier,now):
        f=public_facts(identifier,local_day(now))
        row=c.execute('SELECT data FROM cc_tn_extension_demo_checks WHERE account=%s AND ein=%s',(account,identifier)).fetchone()
        answer=row['data'] if row else {}
        if (answer.get('period_end'),answer.get('expiration'),answer.get('source_checked_at'))==(f['period_end'],f['expiration'],f['checked_at']):
            f['existing_filing']={'yes':True,'no':False}.get(answer.get('answer'))
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
            if old['scenario']==scenario and old['facts']['period_end']==f['period_end'] and old['status'] in {'Extension submitted','Receipt acknowledged','Submission unconfirmed'}:
                self.reconcile(c,account,old,now);return self.public(old)
        r=dict(id=uuid.uuid4().hex,ein=identifier,scenario=scenario,demo_only=True,as_of=AS_OF,facts=f,
            status='Draft',approval='Not approved - demo only',documents={},gateway={},state_sends=0,
            fields=dict(name=name,coid=f['coid'],address=f['address'],phone=f['phone'],website=f['website'],
                contact='',contact_email='',title='',reason='',requested_days='90'),
            prior_filing='no' if scenario=='verified' else 'unknown',reviewed=False,authorized=False)
        if scenario=='verified':r['as_of']=local_day(now).isoformat()
        c.execute('INSERT INTO cc_tn_extension_demo_requests VALUES (%s,%s,%s,%s,%s,%s)',(r['id'],account,identifier,now,now,Jsonb(r)))
        return self.public(r)
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
        for k in ['name','coid','address','contact','contact_email','title','reason']:
            if not r['fields'][k]:raise Invalid('Complete the highlighted organization, contact, title and reason fields.')
        if r['fields']['coid']!=r['facts']['coid'] or r['fields']['name']!=r['facts']['name']:raise Invalid('Changing the registered identity requires reverification.')
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',r['fields']['contact_email']):raise Invalid('Confirm the filer email address.')
        if not re.fullmatch(r'\d{1,2}',r['fields']['requested_days']) or not 1<=int(r['fields']['requested_days'])<=90:raise Invalid('A first extension request must be between 1 and 90 days.')
    def fields(self,r):
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
    def submit(self,c,account,r,p,now):
        if r['status'] in {'Extension submitted','Receipt acknowledged'}:return self.public(r)
        if r['status']=='Submission unconfirmed':raise Conflict('Submission unconfirmed. Check for a receipt before any retry.')
        self.edit(r,p);self.review(r,now)
        if r['scenario']=='verified':
            f=self.checked_facts(c,account,r['ein'],now)
            if not eligibility(f,local_day(now))['eligible'] or f['period_end']!=r['facts']['period_end']:raise Invalid('Recheck extensions: the source, period or prior-filing answer is no longer eligible.')
        for old in self.existing(c,account,r['ein']):
            if old['id']!=r['id'] and (old['facts']['coid'],old['facts']['period_start'],old['facts']['period_end'])==(r['facts']['coid'],r['facts']['period_start'],r['facts']['period_end']) and old['status'] in {'Extension submitted','Receipt acknowledged','Submission unconfirmed'}:
                raise Conflict('Another application for this period is already submitted or unconfirmed. Review it before retrying.')
        behavior=p.get('test_response','delayed')
        if behavior not in {'immediate','delayed','timeout','failed'}:raise Invalid('Only the built-in test service is available.')
        r['state_sends']+=1
        if behavior=='failed':
            r['status']='Submission failed';r['failure']='Test service confirmed failure before accepting the filing. Draft retained.'
        else:
            confirmation='DEMO-TN-'+uuid.uuid4().hex[:12]
            body=document_pdf('Tennessee extension application - submitted TEST copy',self.fields(r)|{'Confirmation':confirmation,'Submitted UTC':datetime.fromtimestamp(now,timezone.utc).isoformat(),'Form basis':'Published SS-6074; portal-specific fields unverified'})
            url=self.document(c,account,r,'application',body,now)
            r['gateway']=dict(confirmation=confirmation,ein=r['ein'],coid=r['facts']['coid'],period_start=r['facts']['period_start'],period_end=r['facts']['period_end'],
                application_sha256=hashlib.sha256(body).hexdigest(),submitted_at=now,ack_at=now+(0 if behavior=='immediate' else 15),document=url)
            r.update(submitted_at=now,confirmation=confirmation,status='Submission unconfirmed' if behavior=='timeout' else 'Extension submitted')
            r['documents']['application']=url
            if behavior=='immediate':self.reconcile(c,account,r,now)
        self.save(c,account,r,now);return self.public(r)
    def reconcile(self,c,account,r,now):
        g=r.get('gateway')
        if not g:return
        row=c.execute('SELECT * FROM cc_tn_extension_demo_documents WHERE id=%s AND account=%s',(g['document'].rsplit('/',1)[-1],account)).fetchone()
        if not row or (g.get('ein'),g.get('coid'),g.get('period_start'),g.get('period_end'),g.get('application_sha256'))!=(r['ein'],r['facts']['coid'],r['facts']['period_start'],r['facts']['period_end'],row['sha256']):return
        if r['status']=='Submission unconfirmed':r['status']='Extension submitted'
        if now>=g['ack_at'] and not r['documents'].get('acknowledgment'):
            body=document_pdf('Tennessee acknowledgment - simulated',self.fields(r)|{'Outcome':'Receipt acknowledged by TEST service. NOT state approval.',
                'Confirmation':g['confirmation'],'Submitted UTC':datetime.fromtimestamp(g['submitted_at'],timezone.utc).isoformat(),
                'Acknowledged UTC':datetime.fromtimestamp(now,timezone.utc).isoformat(),'Exact submitted application SHA256':g['application_sha256']})
            r['documents']['acknowledgment']=self.document(c,account,r,'acknowledgment',body,now)
            r.update(acknowledged_at=now,status='Receipt acknowledged')
        self.save(c,account,r,now)
    def dispatch(self,c,account,p,now):
        action=p.get('action')
        if action in {'check','status'}:
            identifier=ein(p.get('ein'));facts=self.checked_facts(c,account,identifier,now);rows=self.existing(c,account,identifier)
            for r in rows:self.reconcile(c,account,r,now)
            return dict(demo_only=True,state='TN',facts=facts,eligibility=eligibility(facts,local_day(now)),requests=[self.public(r) for r in rows],supported_states=['TN'],needs_prior_confirmation=facts['period_verified'] and facts['existing_filing'] is None)
        if action=='confirm-prior':
            identifier=ein(p.get('ein'));answer=p.get('answer')
            if answer not in {'yes','no','unknown'}:raise Invalid('Confirm whether anything has already been submitted for this period.')
            f=public_facts(identifier,local_day(now))
            if not f['period_verified']:raise Invalid('The original period and deadline must be verified first.')
            declaration=dict(answer=answer,account=account,answered_at=now,period_end=f['period_end'],expiration=f['expiration'],source_checked_at=f['checked_at'])
            c.execute('INSERT INTO cc_tn_extension_demo_checks VALUES (%s,%s,%s,%s) ON CONFLICT(account,ein) DO UPDATE SET checked=excluded.checked,data=excluded.data',(account,identifier,now,Jsonb(declaration)))
            return self.dispatch(c,account,dict(action='check',ein=identifier),now)
        if action=='prepare':
            identifier=ein(p.get('ein'));f=public_facts(identifier,local_day(now))
            return self.create(c,account,dict(ein=identifier,name=f['name'],scenario='verified'),now)
        if action=='create':return self.create(c,account,p,now)
        r=self.load(c,account,p.get('id'))
        if action=='save':self.edit(r,p);self.save(c,account,r,now);return self.public(r)
        if action=='submit':return self.submit(c,account,r,p,now)
        if action=='receipt':self.reconcile(c,account,r,now);return self.public(r)
        raise Invalid('Unsupported extension action.')

def handle(alerts,handler,*,origin,include_body=True):
    headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
    try:
        entry=urlsplit(handler.path);service=Service(alerts)
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
                for k,v in (headers|{'Content-Type':'application/pdf','Content-Disposition':'inline; filename="demo-only-tennessee-extension.pdf"','Content-Length':str(len(body))}).items():handler.send_header(k,v)
                handler.end_headers()
                if include_body:handler.wfile.write(body)
                return
            if handler.command!='POST' or handler.headers.get('Origin')!=origin:return handler._send_json(403,{'error':'Invalid request origin.'},headers)
            if handler.headers.get('Content-Type','').split(';')[0]!='application/json':raise Invalid('JSON input required.')
            n=int(handler.headers.get('Content-Length','0'))
            if not 0<n<=16000:raise Invalid('Invalid request size.')
            p=json.loads(handler.rfile.read(n))
            if not isinstance(p,dict) or any(k in p for k in ['endpoint','url','live','account','owner','facts','as_of']):raise Invalid('Only this account and the fixed test service are supported.')
            if p.get('action')=='create':raise Invalid('Use Check for extensions and the Tennessee File Extension button.')
            result=service.dispatch(c,account,p,now)
        return handler._send_json(200,result,headers)
    except Conflict as exc:return handler._send_json(409,{'error':str(exc)},headers)
    except (Invalid,ValueError,TypeError,KeyError,UnicodeError) as exc:return handler._send_json(400,{'error':str(exc)[:240]},headers)
    except Exception:return handler._send_json(503,{'error':'Extension demo temporarily unavailable. Check for a receipt before retrying a submission.'},headers)
