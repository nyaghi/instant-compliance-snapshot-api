"""Retain the original certificate already returned by the selected OK filing."""
import io,re,time
from deployment.ok_source import ARCHIVED_HOSTS
from urllib.parse import urlsplit,parse_qsl
from pypdf import PdfReader,PdfWriter

def retain_exemption_notice(page, run, candidates, name):
    """Optional historical filing; never a renewal or source of current status."""
    if run is None or run.state != 'OK': return ''
    rows = set()
    for value in candidates:
        match = re.fullmatch(r'(\d+)\s+Notice of Registration Exemption\s+([A-Za-z]+ \d{1,2}, \d{4})\s+(\d+)', value.strip())
        if match: rows.add(match.groups())
    if len(rows) != 1: return ''
    number, filed, count = next(iter(rows))
    if not 1 <= int(count) <= 99: return ''
    fact = {'adapter':'OK-historical-exemption-notice','outcome':'unavailable','document_number':number}
    run.visual_adapter_facts.append(fact)
    try:
        from deployment.state_snapshots import DEADLINE
        remaining = min(5.0, DEADLINE.get()-time.monotonic()-1)
        if remaining < 1.5: return ''
        stop=time.monotonic()+remaining; url=page.url; u=urlsplit(url)
        if u.scheme!='https' or u.netloc!='business.sos.ok.gov' or u.path!='/corp/charityDetail.aspx': return ''
        query=parse_qsl(u.query)
        if len(query)!=1 or query[0][0]!='id' or not re.fullmatch(r'\d+',query[0][1]): return ''
        row=page.get_by_text(number,exact=True).locator('xpath=ancestor::tr[1]')
        link=row.get_by_role('link',name='Open PDF',exact=True)
        expected=f'window.open("../CharityDocs/{number}.pdf"); return false;'
        if link.get_attribute('onclick',timeout=500)!=expected: return ''
        source='https://business.sos.ok.gov/CharityDocs/'+number+'.pdf'
        response=page.request.get(source,timeout=max(1,int((stop-time.monotonic())*1000)),max_redirects=0)
        raw=response.body()
        if not response.ok or response.url!=source or page.url!=url or not raw.startswith(b'%PDF') or len(raw)>3_000_000:return ''
        reader=PdfReader(io.BytesIO(raw))
        if reader.is_encrypted or len(reader.pages)!=int(count):return ''
        text=reader.pages[0].extract_text() or ''
        norm=lambda v:re.sub(r'[^a-z0-9]','',v.lower())
        if text.strip():
            if 'exempt' not in text.lower() or norm(name) not in norm(text):return ''
        elif not list(reader.pages[0].images):return ''
        if time.monotonic()>=stop:return ''
        # Like the existing renewal-certificate path, retain its original first
        # page. A long historical attachment must not exceed the archive bound
        # and suppress the selected main-page snapshot.
        writer=PdfWriter();writer.add_page(reader.pages[0]);out=io.BytesIO();writer.write(out)
        if not hasattr(run,'ok_original_certificates'):run.ok_original_certificates={}
        run.ok_original_certificates[(query[0][1],name)]={'pdf':out.getvalue(),'document_number':number,'url':url,
            'captured_at':time.time(),'pages':1,'historical_exemption':True,'filed':filed}
        fact.update(outcome='retained',pages=1,source_pages=int(count),identifier=query[0][1])
        return number
    except Exception as exc:
        fact['error_type']=type(exc).__name__
        return ''

def retain_certificate(run,url,document_number,name,raw):
    if run is None or run.state!='OK':return
    fact={'adapter':'OK-original-certificate','outcome':'rejected'}
    run.visual_adapter_facts.append(fact)
    try:
        u=urlsplit(url);query=parse_qsl(u.query)
        if (u.scheme!='https' or u.netloc not in ARCHIVED_HOSTS or u.path!='/corp/charityDetail.aspx'
            or len(query)!=1 or query[0][0]!='id' or not re.fullmatch(r'\d+',query[0][1])
            or not re.fullmatch(r'\d+',document_number) or not name
            or not isinstance(raw,bytes) or not raw.startswith(b'%PDF') or len(raw)>20_000_000):return
        reader=PdfReader(io.BytesIO(raw))
        if not 1<=len(reader.pages)<=200:return
        # Oklahoma's filing download starts with its issued certificate. Keep
        # that actual page, including scanned certificates; do not redraw/OCR it.
        page=reader.pages[0];text=page.extract_text() or ''
        if text.strip():
            if not re.search(r'CERTIFICATE\s+OF\s+REGISTRATION',text,re.I):return
            printed=re.search(r'Registration\s+of\s+(.+?)\s+has\s+been\s+filed',text,re.I|re.S)
            norm=lambda v:re.sub(r'[^a-z0-9]','',v.lower())
            if printed and norm(printed.group(1))!=norm(name):return
        elif not list(page.images):return
        writer=PdfWriter();writer.add_page(page);out=io.BytesIO();writer.write(out)
        if len(out.getvalue())>3_000_000:return
        retained=getattr(run,'ok_original_certificates',None)
        if retained is None:run.ok_original_certificates={};retained=run.ok_original_certificates
        if len(retained)>=12:return
        retained[(query[0][1],name)]={'pdf':out.getvalue(),'document_number':document_number,'url':url,'captured_at':time.time()}
        fact.update(outcome='retained',identifier=query[0][1],document_number=document_number,pages=1)
    except Exception as exc:fact.update(outcome='unavailable',error_type=type(exc).__name__)

def pair_selected_certificate(run,ordered,row):
    if run.state!='OK' or row.get('success') is not True or row.get('status') in {'Not Registered','Unable to Confirm','Unable to Verify','Site Not Reachable'}:return ordered
    identifier=str(row.get('matched_registry_identifier') or '')
    name=str(row.get('matched_registry_name') or '')
    cert=getattr(run,'ok_original_certificates',{}).get((identifier,name))
    if not cert or not re.search(r'(?<!\d)'+re.escape(cert['document_number'])+r'(?!\d)',str(row.get('raw_status_text') or '')):return ordered
    from deployment.state_snapshots import source_name_present,render_pdf,MAX_BYTES
    for image in ordered:
        url,raw,kind,text,stamp,note=image
        if kind!='image' or url!=cert['url'] or not source_name_present(name,text,'OK'):continue
        if not re.search(r'(?<!\d)'+re.escape(identifier)+r'(?!\d)',text+' '+url):continue
        try:
            first=PdfReader(io.BytesIO(render_pdf({'kind':'image'},raw)))
            second=PdfReader(io.BytesIO(cert['pdf']))
            if len(first.pages)!=1 or len(second.pages)!=cert.get('pages',1):return ordered
            writer=PdfWriter();writer.add_page(first.pages[0])
            for page in second.pages:writer.add_page(page)
            out=io.BytesIO();writer.write(out)
            if len(out.getvalue())>MAX_BYTES:return ordered
            label=(' Original first page of the historical Notice of Registration Exemption filed '+cert['filed']+' ('+cert['document_number']+') appended; not a current renewal certificate.'
                   if cert.get('historical_exemption') else ' Original issued certificate from selected filing '+cert['document_number']+' appended as page two; no additional source request.')
            combined=(url,out.getvalue(),'source_pdf',text,max(stamp,cert['captured_at']),note+label)
            return [combined]+ordered
        except Exception:return ordered
    return ordered
