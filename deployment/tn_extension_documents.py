"""Document and deadline helpers for the isolated Tennessee TEST workflow.

No network client or live filing destination. Test evidence is issued by the
local fake gateway, bound to an exact tuple and accepted only by exact hash.
This is deliberately not a validator for real IRS acceptance documents.
"""
import calendar
from datetime import date, timedelta
import io
from pathlib import Path
from decimal import Decimal, InvalidOperation

def month_date(value, months, number=15):
    index=value.year*12+value.month-1+months
    return date(index//12,index%12+1,number)

def holidays(year):
    def observed(d):return d+timedelta(days=1 if d.weekday()==6 else -1 if d.weekday()==5 else 0)
    def monday(month,n):
        first=date(year,month,1)
        return first+timedelta(days=(0-first.weekday())%7+7*(n-1))
    result={observed(date(y,m,d)) for y in [year-1,year,year+1] for m,d in [(1,1),(6,19),(7,4),(11,11),(12,25)]}
    result|={monday(1,3),monday(2,3),monday(9,1),monday(10,2),observed(date(year,4,16))}
    last=date(year,5,31);result.add(last-timedelta(days=last.weekday()))
    first=date(year,11,1);result.add(first+timedelta(days=(3-first.weekday())%7+21))
    return result

def business_day(value):
    while value.weekday()>4 or value in holidays(value.year):value+=timedelta(days=1)
    return value

def federal_deadline(period_end):return business_day(month_date(date.fromisoformat(period_end),5))

def federal_status(facts,today):
    form=facts.get('return_type','')
    supported=form in {'990','990-EZ','990-PF'}
    try:
        due=federal_deadline(facts['period_end'])
        end=date.fromisoformat(facts['period_end']);start=date.fromisoformat(facts['period_start'])
        regular=start==date(end.year-1+end.month//12,end.month%12+1,1)
    except (ValueError,KeyError,TypeError):return dict(eligible=False,reason='The federal filing period is not verified.',deadline='')
    reason=('Form 990-N cannot be extended using Form 8868.' if form=='990-N' else
        'The return type or regular annual period needs verification.' if not supported or not regular else
        'The ordinary federal deadline has passed. You can prepare a demo draft, but this record cannot be submitted as a timely new IRS extension. No disaster relief has been verified.' if today>due else '')
    return dict(eligible=not reason,reason=reason,deadline=due.isoformat(),return_type=form,
        can_prepare=supported and regular,deadline_open=today<=due,
        search_scope='This account’s accepted test records only. Public Form 990 data supplies prefill, not proof that an IRS extension was or was not filed.',
        form_source='https://www.irs.gov/pub/irs-pdf/f8868.pdf')

def prefill(facts):
    return dict(name=facts.get('name',''),ein=facts.get('ein',''),street=facts.get('irs_street',''),
        city_state_zip=facts.get('irs_city_state_zip',''),return_type=facts.get('return_type',''),
        period_start=facts.get('period_start',''),period_end=facts.get('period_end',''),
        books='',phone='',tax_a='',tax_b='',tax_c='')

def validated_fields(facts,values):
    result=prefill(facts)
    if not isinstance(values,dict) or set(values)-set(result):raise ValueError('Unexpected IRS form fields.')
    for k,v in values.items():
        if not isinstance(v,str) or len(v)>180:raise ValueError('Invalid IRS form field.')
        result[k]=v.strip()
    for k in ['ein','return_type','period_start','period_end']:
        if result[k]!=prefill(facts)[k]:raise ValueError('The IRS identity, period and return type must match the verified request.')
    if any(not result[k] for k in result):raise ValueError('Complete and confirm the highlighted IRS fields, including all three tax lines (zero if applicable).')
    try:
        amounts=[Decimal(result[k]) for k in ['tax_a','tax_b','tax_c']]
        if any(not x.is_finite() or x<0 or x>Decimal('99999999999.99') or x.as_tuple().exponent < -2 for x in amounts):raise ValueError('Enter valid nonnegative tax amounts with at most two decimals.')
        if amounts[2]!=max(Decimal(0),amounts[0]-amounts[1]):raise ValueError('Line 3c must equal line 3a minus line 3b, with a minimum of zero.')
    except InvalidOperation:raise ValueError('Enter valid tax amounts.')
    if len(''.join(c for c in result['phone'] if c.isdigit()))<10:raise ValueError('Confirm the books-in-care-of telephone number.')
    return result

def form8868(values,accepted=False):
    """Official fillable Part I/II, with generated appearances and demo watermark."""
    from pypdf import PdfReader,PdfWriter
    from pypdf.generic import DecodedStreamObject,DictionaryObject,NameObject,ArrayObject,NumberObject
    from reportlab.pdfgen import canvas
    writer=PdfWriter();writer.append(PdfReader(Path(__file__).with_name('tn-extension-form8868.pdf')),pages=(0,1))
    page='topmostSubform[0].Page1[0].';automatic=page+'Automatic[0].'
    end=date.fromisoformat(values['period_end']);start=date.fromisoformat(values['period_start'])
    extended=business_day(month_date(end,11))
    fields={automatic+'f1_1[0]':values['name'],automatic+'f1_2[0]':values['ein'],automatic+'f1_3[0]':values['street'],automatic+'f1_4[0]':values['city_state_zip'],
        page+'f1_5[0]':'04' if values['return_type']=='990-PF' else '01',page+'f1_23[0]':values.get('books',''),page+'f1_24[0]':values.get('phone',''),
        page+'f1_26[0]':extended.strftime('%B %d'),page+'f1_27[0]':str(extended.year)[2:],page+'c1_3[1]':'/2',
        page+'f1_29[0]':start.strftime('%B %d'),page+'f1_30[0]':str(start.year)[2:],page+'f1_31[0]':end.strftime('%B %d'),page+'f1_32[0]':str(end.year)[2:],
        page+'f1_33[0]':values.get('tax_a',''),page+'f1_34[0]':values.get('tax_b',''),page+'f1_35[0]':values.get('tax_c','')}
    # Use the actual widget's export value rather than guessing a checkbox name.
    for annotation in writer.pages[0].get('/Annots',[]):
        a=annotation.get_object()
        if a.get('/T')=='c1_3[1]':fields[page+'c1_3[1]']=next(k for k in a['/AP']['/N'] if k!='/Off')
    writer.update_page_form_field_values(writer.pages[0],fields,auto_regenerate=False)
    # A font-independent checkbox appearance remains interactive when unchecked.
    for annotation in writer.pages[0].get('/Annots',[]):
        a=annotation.get_object()
        if a.get('/T')=='c1_3[1]':
            appearances=DictionaryObject()
            for name,content in [('/Off',b''),(str(a['/AS']),b'0 G 0.8 w 1 1 m 7 7 l S 1 7 m 7 1 l S')]:
                stream=DecodedStreamObject();stream.set_data(content);stream.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Form'),NameObject('/BBox'):ArrayObject([NumberObject(0),NumberObject(0),NumberObject(8),NumberObject(8)])})
                appearances[NameObject(name)]=writer._add_object(stream)
            a[NameObject('/AP')]=DictionaryObject({NameObject('/N'):appearances})
    overlay=io.BytesIO();c=canvas.Canvas(overlay,pagesize=(612,792));c.setFillColorRGB(.7,.08,.08);c.setFont('Helvetica-Bold',11)
    c.drawString(36,782,'DEMO ONLY — '+('SIMULATED FILED COPY' if accepted else 'DRAFT — NOT FILED'))
    c.setFont('Helvetica',7);c.drawString(36,771,'Nothing is sent to the IRS. Part III (Form 5330) is outside this pilot.')
    c.save()
    writer.pages[0].merge_page(PdfReader(overlay).pages[0]);writer.add_metadata({'/Title':'Demo only - Form 8868'})
    output=io.BytesIO();writer.write(output);return output.getvalue()
