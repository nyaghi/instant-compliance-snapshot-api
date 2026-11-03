"""On-demand Compliance Express package of displayed results and saved evidence.

No registry requests, status calculation, or background generation. Archive URLs
are opaque local identifiers, bound to the result's EIN and state before use.
"""
import copy
import io
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape
from urllib.parse import urlsplit

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import RectangleObject
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parent.parent
NAVY = colors.HexColor('#0B2A5B')
RED = colors.HexColor('#C8202E')
INK = colors.HexColor('#263445')
GRAY = colors.HexColor('#64748B')
PALE = colors.HexColor('#F3F6FA')
WIDTH, HEIGHT, MARGIN = 612, 792, 38
STATE_NAMES = dict(zip(
    'AK AL AR CA CO CT DC FL GA HI IL KS KY LA MA MD ME MI MN MS NC ND NH NJ NM NV NY OH OK OR PA RI SC TN VA WA WI WV'.split(),
    ['Alaska','Alabama','Arkansas','California','Colorado','Connecticut','District of Columbia','Florida','Georgia','Hawaii','Illinois','Kansas','Kentucky','Louisiana','Massachusetts','Maryland','Maine','Michigan','Minnesota','Mississippi','North Carolina','North Dakota','New Hampshire','New Jersey','New Mexico','Nevada','New York','Ohio','Oklahoma','Oregon','Pennsylvania','Rhode Island','South Carolina','Tennessee','Virginia','Washington','Wisconsin','West Virginia']))
STYLES = {k: ParagraphStyle(k,fontName='Helvetica',fontSize=size,leading=leading,textColor=INK,spaceAfter=0)
          for k,size,leading in [('body',10,14),('small',8,11),('title',23,27),('heading',14,18)]}

def text(value, limit=12000):
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str(value or ''))[:limit].replace('\u2014',' - ').replace('\u2013','-').replace('\u2011','-')

def para(c,value,x,y,width,style='body'):
    p=Paragraph(escape(text(value)).replace('\n','<br/>'),STYLES[style])
    _,h=p.wrap(width,10000);p.drawOn(c,x,y-h);return y-h

def frame(c, org, ein, title='Compliance package'):
    logo=ROOT/'report-assets/compliance-express.png'
    c.drawImage(str(logo),MARGIN,HEIGHT-67,width=155,height=31,preserveAspectRatio=True,anchor='sw',mask='auto')
    c.setFillColor(GRAY);c.setFont('Helvetica',8);c.drawRightString(WIDTH-MARGIN,HEIGHT-43,title)
    c.setStrokeColor(RED);c.setLineWidth(1.5);c.line(MARGIN,HEIGHT-79,WIDTH-MARGIN,HEIGHT-79)
    c.setFillColor(GRAY);c.setFont('Helvetica',7)
    c.drawString(MARGIN,24,'www.compliance-express.com  |  info@compliance-express.com')
    c.drawRightString(WIDTH-MARGIN,24,'EIN '+ein)

def page_bytes(draw, org, ein, title='Compliance package'):
    b=io.BytesIO();c=canvas.Canvas(b,pagesize=(WIDTH,HEIGHT));frame(c,org,ein,title);draw(c);c.save();return b.getvalue()

def compact_history_page(page):
    """Remove only the generated history's repeated footer and trailing space."""
    bottoms=[]
    def observe(value,cm,tm,font,size):
        if not value.strip():return
        y=tm[4]*cm[1]+tm[5]*cm[3]+cm[5]
        if y<40 and (value.strip().isdigit() or value.startswith('Compliance Express |')):return
        bottoms.append(y-abs(size)*0.4-5)
    page.extract_text(visitor_text=observe)
    if bottoms and all(40<y<float(page.cropbox.top) for y in bottoms):
        page.cropbox=RectangleObject((page.cropbox.left,min(bottoms),page.cropbox.right,page.cropbox.top))
    return page

def label(row):
    review=row.get('identity_review')
    if isinstance(review,dict) and not row.get('identity_review_decision') and row.get('status') in {'Needs Review','Unable to Confirm','Unknown'}:
        return 'Confirm organization'
    return text(row.get('display_status') or row['status'],100)

def category(row):
    s=row['status']
    if s in {'Delinquent','Failed to Renew','Expired','Suspended','Revoked','Closed / Withdrawn / Canceled'}:return 0
    if s=='Upcoming Filing':return 1
    if s=='Pending':return 2
    if s in {'Not Registered','Not Registered / Non-Compliant'}:return 3
    if s in {'Current','Exempt'}:return 5
    return 4

CATEGORIES=[
 ('Review adverse or inactive records','Review the state evidence and confirm the renewal, reinstatement, or closure action with your compliance provider.'),
 ('Prepare upcoming filings','Confirm the reported deadline and prepare the renewal documents. Use the state sections for the date and source context.'),
 ('Follow up on pending applications','Check whether the state is awaiting documents, payment, or a decision. Pending is not an issued registration.'),
 ('Assess registration or exemption needs','No qualifying registration was found in these completed checks. Review fundraising activity and exemption eligibility before deciding whether to register.'),
 ('Resolve incomplete checks or identity questions','Use the explanation in each state section. Retry unavailable sources; review candidate identity where a decision is requested.'),
 ('Maintain current registrations and exemptions','Retain the supporting evidence and monitor future filings. An exemption is limited to the basis recorded by the state.')]

def validate(payload,supported):
    rows=payload.get('results') if isinstance(payload,dict) else None
    if not isinstance(rows,list) or not 1<=len(rows)<=len(supported):raise ValueError('Provide completed results for one organization.')
    seen=set();ein=None;name=None;out=[]
    for row in rows:
        if not isinstance(row,dict):raise ValueError('Invalid state result.')
        r=dict(row);e=re.sub(r'\D','',str(r.get('ein','')));st=r.get('state')
        if len(e)!=9 or st not in supported or st in seen or not isinstance(r.get('status'),str) or not 1<=len(r['status'])<=100:raise ValueError('Invalid or duplicate state result.')
        if ein is not None and (e!=ein or r.get('organization_name')!=name):raise ValueError('Results must belong to one organization.')
        if not isinstance(r.get('organization_name'),str) or not 1<=len(r['organization_name'])<=500:raise ValueError('Organization name is required.')
        ein=e;name=r['organization_name'];seen.add(st)
        for k in ['comments','source_note','raw_status_text']:
            if r.get(k) is not None and (not isinstance(r[k],str) or len(r[k])>20000):raise ValueError('Result text exceeds package limit.')
        out.append(r)
    return sorted(out,key=lambda r:STATE_NAMES.get(r['state'],r['state']))

def evidence(row,store):
    from deployment import state_snapshots as ss,search_history as sh
    # Same presentation policy as the app: completed negatives use search history.
    candidates=(row.get('identity_review') or {}).get('candidates') or []
    all_rejected=bool(candidates) and all(c.get('decision')=='reject' for c in candidates)
    negative=ss.completed_negative_result(row) or (row.get('identity_review_evidence_final') is True and all_rejected)
    if not negative and not row.get('evidence_url') and candidates:
        included=[c for c in candidates if c.get('decision')!='reject' and c.get('evidence_url')]
        if included:
            combined=PdfWriter()
            for candidate in included:
                bound={**row, 'identity_review':None, 'evidence_url':candidate['evidence_url'],
                       'matched_registry_identifier':candidate.get('identifier') or '',
                       'matched_registry_name':candidate.get('name') or ''}
                raw,kind=evidence(bound,store)
                if raw:
                    title=('Identity accepted: ' if candidate.get('decision')=='accept' else 'Unconfirmed candidate: ')+text(candidate.get('name'))
                    heading=page_bytes(lambda c:para(c,title,MARGIN,HEIGHT-103,WIDTH-2*MARGIN,'heading'),row['organization_name'],row['ein'])
                    combined.append(PdfReader(io.BytesIO(heading)));combined.append(PdfReader(io.BytesIO(raw)))
            if len(combined.pages):
                out=io.BytesIO();combined.write(out);return out.getvalue(),'Candidate evidence - identity review'

    path=row.get('search_history_url') if negative else row.get('evidence_url')
    if not path:return None,'Names searched unavailable' if negative else 'State snapshot unavailable'
    pattern=r'/state-evidence/([a-f0-9]{64})/search-history\.pdf' if negative else r'/state-snapshots/([a-f0-9]{64})\.pdf'
    m=re.fullmatch(pattern,str(path))
    if not m:raise ValueError('Invalid saved evidence reference.')
    if negative:
        item=sh.loaded(m[1],store)
        if item is None:return None,'Names searched unavailable'
        meta,doc,cached=item
        raw=cached or sh.render_pdf(doc)
    else:
        item=ss.saved_pdf(m[1],store)
        if item is None:return None,'State snapshot unavailable'
        meta,raw=item
    if meta.get('state')!=row['state'] or ss.digits(meta.get('ein'))!=ss.digits(row['ein']):raise ValueError('Evidence belongs to another organization or state.')
    if not negative:
        expected=row.get('matched_registry_identifier') or ''
        if expected and str(meta.get('identifier') or '')!=str(expected):
            # The existing strict matcher already supports state-specific IDs.
            ref={**meta,'url':path}
            # Archived image metadata predates the operation field carried by
            # live references. NY's observed detail URL independently proves it.
            if row['state']=='NY':
                source=urlsplit(meta.get('source_url') or '')
                selected=urlsplit(row.get('source_url') or '')
                record=re.fullmatch(r'/RegistrySearch/(\d{2}-\d{2}-\d{2})/?',source.path)
                if (record and source.scheme=='https' and source.hostname=='charities-search.ag.ny.gov'
                        and source.hostname==selected.hostname and source.path.rstrip('/')==selected.path.rstrip('/')
                        and meta.get('identifier')==record[1]):ref['operation']='detail'
            if not ss.matching_reference(row,[ref]):raise ValueError(row['state']+': evidence does not match the selected record.')
    return raw,'Names searched' if negative else 'State snapshot'

def generate(payload,supported,store=None):
    from deployment import state_snapshots as ss
    rows=validate(payload,supported);store=store or ss.STORE
    if store is None:raise ValueError('Saved evidence storage is unavailable.')
    org=rows[0]['organization_name'];digits=ss.digits(rows[0]['ein']);ein=digits[:2]+'-'+digits[2:]
    stamp=datetime.now(ZoneInfo('America/New_York')).strftime('%B %d, %Y')
    body=PdfWriter();sections=[];issues=[];total_bytes=0
    for row in rows:
        try:raw,kind=evidence(row,store)
        except (OSError,RuntimeError):raw,kind=None,'Saved evidence temporarily unavailable'
        if raw:
            total_bytes+=len(raw)
            if total_bytes>100_000_000:raise ValueError('Evidence package exceeds the supported size.')
            source=PdfReader(io.BytesIO(raw))
            if source.is_encrypted or not 1<=len(source.pages)<=100:raise ValueError('Invalid saved PDF.')
        else:source=None;issues.append(row['state'])
        first=len(body.pages);sections.append({'row':row,'start':first,'kind':kind,'available':bool(raw)})
        comment=text(row.get('comments') or row.get('source_note') or '',12000)
        # Reviewer identity/email is internal audit data, not report content.
        comment=re.sub(r'Reviewed by [^\n.]+@[^\s.]+(?:\.[^\s.]+)+\.?\s*','',comment)
        intro=io.BytesIO();cv=canvas.Canvas(intro,pagesize=(WIDTH,HEIGHT));frame(cv,org,ein)
        y=HEIGHT-98;y=para(cv,STATE_NAMES.get(row['state'],row['state']),MARGIN,y,WIDTH-2*MARGIN,'title')-7
        y=para(cv,label(row),MARGIN,y,WIDTH-2*MARGIN,'heading')-10
        if row.get('checked_at_epoch'):
            try:y=para(cv,'Checked '+datetime.fromtimestamp(float(row['checked_at_epoch']),ZoneInfo('America/New_York')).strftime('%b %d, %Y, %I:%M %p %Z'),MARGIN,y,WIDTH-2*MARGIN,'small')-8
            except (ValueError,TypeError,OverflowError):pass
        # A long explanation gets additional text pages, never truncation.
        chunks=re.split(r'(?<=[.!?])\s+|\n+',comment)
        for chunk in chunks:
            if not chunk:continue
            pp=Paragraph(escape(chunk),STYLES['small']);_,h=pp.wrap(WIDTH-2*MARGIN,10000)
            while h > y-105:
                pieces=pp.split(WIDTH-2*MARGIN,max(0,y-105))
                if pieces:
                    part=pieces[0];_,ph=part.wrap(WIDTH-2*MARGIN,10000);part.drawOn(cv,MARGIN,y-ph)
                    if len(pieces)==1:pp=None;break
                    pp=pieces[1]
                cv.showPage();frame(cv,org,ein,STATE_NAMES[row['state']]+' - result continued');y=HEIGHT-100
                _,h=pp.wrap(WIDTH-2*MARGIN,10000)
            if pp is not None:pp.drawOn(cv,MARGIN,y-h);y-=h+3
        y-=8;y=para(cv,kind,MARGIN,y,WIDTH-2*MARGIN,'heading')-8
        if not raw:
            para(cv,'This package preserves the reported result. No evidence was substituted and no new state search was run.',MARGIN,y,WIDTH-2*MARGIN,'small')
            cv.save();intro.seek(0);body.append(PdfReader(intro));continue
        cv.save();intro.seek(0);intro_reader=PdfReader(intro)
        for page in list(intro_reader.pages)[:-1]:body.add_page(page)
        current=intro_reader.pages[-1];available=y-44
        for source_index,original in enumerate(source.pages):
            original.transfer_rotation_to_content()
            if kind=='Names searched':original=compact_history_page(original)
            box=original.cropbox
            sw,shh=float(box.width),float(box.height);scale=min(1,(WIDTH-2*MARGIN)/sw);top=float(box.top)
            # Avoid an almost-empty extra page for a small trailing image strip.
            # Reduce the whole original uniformly by at most 15%; never crop it.
            continued_capacity=HEIGHT-130-44
            first_capacity=available if available>=110 else continued_capacity
            scaled_height=shh*scale
            if scaled_height>first_capacity:
                full_continuations=int((scaled_height-first_capacity)/continued_capacity)
                compact_capacity=first_capacity+full_continuations*continued_capacity
                remainder=scaled_height-compact_capacity
                if 0<remainder<96 and compact_capacity/scaled_height>=0.85:
                    scale=compact_capacity/shh
            while top>float(box.bottom)+0.01:
                if available<110:
                    body.add_page(current)
                    current=PdfReader(io.BytesIO(page_bytes(lambda c:para(c,STATE_NAMES[row['state']]+' | '+kind+' continued',MARGIN,HEIGHT-99,WIDTH-2*MARGIN,'heading'),org,ein))).pages[0]
                    available=HEIGHT-130-44
                bottom=max(float(box.bottom),top-available/scale)
                part=copy.copy(original);part.cropbox=RectangleObject((box.left,bottom,box.right,top))
                dest_top=44+available
                current.merge_transformed_page(part,Transformation().scale(scale).translate(MARGIN-float(box.left)*scale,dest_top-top*scale))
                top=bottom;available-=((float(part.cropbox.height))*scale)+8
                if top>float(box.bottom)+0.01:available=0
            if source_index<len(source.pages)-1:available=0
        body.add_page(current)
        if len(body.pages)>350:raise ValueError('Package exceeds the supported page count.')
    front=io.BytesIO();c=canvas.Canvas(front,pagesize=(WIDTH,HEIGHT));frame(c,org,ein)
    y=HEIGHT-104;y=para(c,'Compliance package',MARGIN,y,WIDTH-2*MARGIN,'title')-10
    y=para(c,org,MARGIN,y,WIDTH-2*MARGIN,'heading')-7
    y=para(c,'EIN '+ein+'  |  Prepared '+stamp+'  |  '+str(len(rows))+' jurisdictions',MARGIN,y,WIDTH-2*MARGIN,'small')-17
    y=para(c,'Prioritized actions',MARGIN,y,WIDTH-2*MARGIN,'heading')-12
    for index,(heading,action) in enumerate(CATEGORIES):
        group=[r for r in rows if category(r)==index]
        if not group:continue
        names='; '.join(STATE_NAMES[r['state']]+' ('+label(r)+')' for r in group)
        p1=Paragraph(escape(names),STYLES['small']);_,hh=p1.wrap(WIDTH-2*MARGIN-12,10000)
        if y-(hh+75)<70:c.showPage();frame(c,org,ein,'Prioritized actions continued');y=HEIGHT-103
        y=para(c,heading,MARGIN,y,WIDTH-2*MARGIN,'heading')-5
        y=para(c,action,MARGIN,y,WIDTH-2*MARGIN,'small')-5
        y=para(c,names,MARGIN+12,y,WIDTH-2*MARGIN-12,'small')-17
    if issues:
        if y<115:c.showPage();frame(c,org,ein);y=HEIGHT-103
        y=para(c,'Evidence to follow up: '+', '.join(STATE_NAMES[s] for s in issues)+'. See the state sections for what is available.',MARGIN,y,WIDTH-2*MARGIN,'small')-10
    if y<95:c.showPage();frame(c,org,ein);y=HEIGHT-103
    para(c,'Based on the displayed CharityClarity results and saved source documents. This is a registration lookup snapshot, not a complete compliance review or legal/tax advice. No new registry searches were run to create this package.',MARGIN,y,WIDTH-2*MARGIN,'small')
    c.save();front_reader=PdfReader(io.BytesIO(front.getvalue()));front_count=len(front_reader.pages)
    # Fixed-height index rows produce deterministic page targets and links.
    index_count=(len(rows)+18)//19;offset=front_count+index_count
    index_stream=io.BytesIO();c=canvas.Canvas(index_stream,pagesize=(WIDTH,HEIGHT));links=[]
    for block in range(index_count):
        frame(c,org,ein,'State status and evidence index');y=HEIGHT-105
        y=para(c,'State index',MARGIN,y,WIDTH-2*MARGIN,'title')-18
        for local,section in enumerate(sections[block*19:(block+1)*19]):
            r=section['row'];num=offset+section['start']+1
            c.setFillColor(PALE if local%2==0 else colors.white);c.rect(MARGIN,y-27,WIDTH-2*MARGIN,30,fill=1,stroke=0)
            para(c,STATE_NAMES[r['state']],MARGIN+6,y,149,'small')
            para(c,label(r),MARGIN+160,y,195,'small')
            para(c,section['kind'],MARGIN+360,y,125,'small')
            c.setFillColor(NAVY);c.setFont('Helvetica',9);c.drawRightString(WIDTH-MARGIN-5,y-10,str(num))
            links.append((front_count+block,num-1,(MARGIN,y-27,WIDTH-MARGIN,y+3)));y-=31
        c.showPage()
    c.save();writer=PdfWriter();writer.append(front_reader);writer.append(PdfReader(io.BytesIO(index_stream.getvalue())));writer.append(body)
    for section in sections:writer.add_outline_item(STATE_NAMES[section['row']['state']]+' - '+label(section['row']),offset+section['start'])
    from pypdf.annotations import Link
    for page,target,rect in links:
        annotation=writer.add_annotation(page,Link(rect=rect,target_page_index=target))
        annotation['/Dest'][0]=writer.pages[target].indirect_reference
    for i,page in enumerate(writer.pages):
        b=io.BytesIO();cv=canvas.Canvas(b,pagesize=(WIDTH,HEIGHT));cv.setFont('Helvetica',7);cv.setFillColor(GRAY);cv.drawCentredString(WIDTH/2,12,f'{i+1} / {len(writer.pages)}');cv.save();page.merge_page(PdfReader(io.BytesIO(b.getvalue())).pages[0])
    writer.add_metadata({'/Title':org+' - Compliance Package','/Author':'Compliance Express','/Subject':'CharityClarity results and original saved evidence'})
    out=io.BytesIO();writer.write(out);return out.getvalue()
