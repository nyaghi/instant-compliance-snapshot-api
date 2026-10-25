"""Retain the original certificate already returned by the selected OK filing."""
import io,re,time
from urllib.parse import urlsplit,parse_qsl
from pypdf import PdfReader,PdfWriter

def retain_certificate(run,url,document_number,name,raw):
    if run is None or run.state!='OK':return
    fact={'adapter':'OK-original-certificate','outcome':'rejected'}
    run.visual_adapter_facts.append(fact)
    try:
        u=urlsplit(url);query=parse_qsl(u.query)
        if (u.scheme!='https' or u.netloc!='www.sos.ok.gov' or u.path!='/corp/charityDetail.aspx'
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
            if len(first.pages)!=1 or len(second.pages)!=1:return ordered
            writer=PdfWriter();writer.add_page(first.pages[0]);writer.add_page(second.pages[0])
            out=io.BytesIO();writer.write(out)
            if len(out.getvalue())>MAX_BYTES:return ordered
            combined=(url,out.getvalue(),'source_pdf',text,max(stamp,cert['captured_at']),note+' Original issued certificate from selected filing '+cert['document_number']+' appended as page two; no additional source request.')
            return [combined]+ordered
        except Exception:return ordered
    return ordered
