"""Clearly labeled official download extract, alongside unchanged source pixels."""
import hashlib, io, json, re
from pathlib import Path
from xml.sax.saxutils import escape

SOURCE='https://justice.oregon.gov/Charities/Charity/GetZip'

def extract(ein, name, public_text, source_url):
    import registry_snapshot_server as master
    row=master.or_snapshot_row_dict_for_ein(ein)
    if not row:return None
    normalize=lambda s:re.sub('[^a-z0-9]','',str(s).lower())
    # Bind to the validated local dataset and the exact official live record.
    if (re.sub(r'\D','',row.get('EIN',''))!=ein
        or normalize(row.get('Name'))!=normalize(name)
        or source_url!='https://justice.oregon.gov/Charities/Charity/details?charityID='+row.get('CharityID','')):
        return None
    manifest=json.loads((Path(master.__file__).parent/'downloadable-state-data.json').read_text(encoding='utf-8-sig'))['states']['OR']
    periods=re.findall(r'Fiscal Year Beginning\s*:?\s*(\d{1,2}/\d{1,2}/\d{4})\s*Ending\s*:?\s*(\d{1,2}/\d{1,2}/\d{4})',public_text,re.I)
    return dict(schema=1,source_url=SOURCE,downloaded_at=manifest['downloaded_at'],
        sha256=manifest['assets'][0]['sha256'],row=row,
        portal_periods=[list(p) for p in periods[:20]])

def validate(value, meta):
    if not isinstance(value,dict) or value.get('schema')!=1 or value.get('source_url')!=SOURCE:
        raise ValueError('Invalid Oregon export evidence')
    row=value.get('row');periods=value.get('portal_periods')
    if (meta['state']!='OR' or not isinstance(row,dict) or not 1<=len(row)<=80
        or any(not isinstance(k,str) or not isinstance(v,str) or len(k)>100 or len(v)>2000 for k,v in row.items())
        or re.sub(r'\D','',row.get('EIN',''))!=meta['ein']
        or meta['source_url']!='https://justice.oregon.gov/Charities/Charity/details?charityID='+row.get('CharityID','')
        or not re.fullmatch('[a-f0-9]{64}',str(value.get('sha256','')))
        or not isinstance(value.get('downloaded_at'),str) or len(value['downloaded_at'])>50
        or not isinstance(periods,list) or len(periods)>20
        or any(not isinstance(p,list) or len(p)!=2 or any(not isinstance(v,str) or not re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}',v) for v in p) for p in periods)):
        raise ValueError('Oregon export identity or schema changed')
    return value

def append(pdf, value):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from pypdf import PdfReader, PdfWriter
    out=io.BytesIO();styles=getSampleStyleSheet()
    p=lambda text:Paragraph(escape(str(text)),styles['BodyText'])
    row=value['row']
    story=[Paragraph('Oregon official download — record extract',styles['Heading1']),
        p('Supporting data used for the status calculation. This is a formatted extract of the official state download, not a screenshot of the portal.'),Spacer(1,12),
        p('The portal and download are separate official views. Their reporting periods may differ; neither source is silently changed to match the other.'),Spacer(1,10),
        p('Portal periods visible in the saved page: '+('; '.join(a+' to '+b for a,b in value['portal_periods']) or 'Not extracted; refer to the original page.')),Spacer(1,12)]
    data=[[p('Official field'),p('Downloaded value')]]+[[p(k),p(v or '(blank)')] for k,v in row.items()]
    table=Table(data,colWidths=[170,350],repeatRows=1,hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EEEEEE')),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,0),(-1,0),.5,colors.grey)]))
    story += [table,Spacer(1,12),p('Official source: '+SOURCE),p('Downloaded: '+value['downloaded_at']),p('Source file SHA-256: '+value['sha256'])]
    SimpleDocTemplate(out,pagesize=(612,792),leftMargin=46,rightMargin=46,topMargin=42,bottomMargin=42).build(story)
    writer=PdfWriter()
    for source in (pdf,out.getvalue()):
        for page in PdfReader(io.BytesIO(source)).pages:writer.add_page(page)
    merged=io.BytesIO();writer.write(merged);return merged.getvalue()
