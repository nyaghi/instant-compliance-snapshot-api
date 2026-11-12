"""Explicitly labeled network-field evidence alongside unchanged MA images."""
import io
import re
from xml.sax.saxutils import escape


def extract(run,row):
    from .state_snapshots import digits,key
    evidence=row.get('ma_filing_evidence') or {}
    status=evidence.get('registry_status','')
    activity_review = (row.get('status') == 'Unable to Confirm'
                       and row.get('status_reason') == 'MA_FORM_PC_DETAIL_UNCONFIRMED'
                       and status.strip().casefold() == 'not doing business in mass')
    if not (evidence.get('contrary_status') or activity_review) or not status:return None
    for binding in getattr(run,'ma_view_more_bindings',{}).values():
        record=binding.get('record') or {}
        if (record.get('registry_status')==status and digits(record.get('ein'))==run.ein
            and record.get('ago_account')==evidence.get('ago_account')==row.get('matched_registry_identifier')
            and key(record.get('name'))==key(row.get('matched_registry_name'))):
            return dict(ein=run.ein,name=row['matched_registry_name'],ago_account=record['ago_account'],
                registry_status=status,source_field='Charity_Status__c',
                source_url='https://masscharities.my.site.com/FilingSearch/s/detail/'+record['record_id'])
    return None


def validate(value,meta):
    from .state_snapshots import key
    if (not isinstance(value,dict) or meta['state']!='MA' or value.get('ein')!=meta['ein']
        or value.get('ago_account')!=meta['identifier'] or key(value.get('name'))!=key(meta['record_name'])
        or value.get('source_field')!='Charity_Status__c'
        or not re.fullmatch(r'\d{6}',str(value.get('ago_account','')))
        or not isinstance(value.get('registry_status'),str) or not 1<=len(value['registry_status'])<=100
        or not re.fullmatch(r'https://masscharities\.my\.site\.com/FilingSearch/s/detail/a09[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?',str(value.get('source_url','')))):
        raise ValueError('Massachusetts status extract is not bound to the selected original')
    return value


def append(pdf,value):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from pypdf import PdfReader,PdfWriter
    styles=getSampleStyleSheet();p=lambda s:Paragraph(escape(str(s)),styles['BodyText'])
    rows=[['Organization',value['name']],['EIN',value['ein']],['AGO account',value['ago_account']],
        ['Charity status',value['registry_status']],['Official response field',value['source_field']]]
    table=Table([[p(a),p(b)] for a,b in rows],colWidths=[155,365]);table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(0,-1),colors.HexColor('#F1F5F9')),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
    out=io.BytesIO();SimpleDocTemplate(out,pagesize=(612,792),leftMargin=46,rightMargin=46).build([
        Paragraph('Massachusetts official record — status extract',styles['Heading1']),
        p('This is a formatted extract of the official registry response received during this check. It is not a screenshot. The preceding pages preserve the original state website views.'),Spacer(1,18),
        p('The registry response includes the charity status below; the public detail page does not display that field.'),Spacer(1,18),table,Spacer(1,18),p('Official selected record: '+value['source_url'])])
    writer=PdfWriter()
    for source in (pdf,out.getvalue()):
        for page in PdfReader(io.BytesIO(source)).pages:writer.add_page(page)
    merged=io.BytesIO();writer.write(merged);return merged.getvalue()
