"""State-local recovery and interpretation; no organization-specific rules."""
import re
from urllib.parse import urlsplit, parse_qs


def al_out_of_scope_history(before,after):
    excluded={'Commercial Co-Venturer','Commercial Telephone Seller','Health Studio','Professional Fundraiser'}
    return (len(before)>=6 and len(after)>=6 and before[3] in excluded
        and all(before[i]==after[i] for i in (0,1,3,4)))


def ca_name_queries(name):
    """Retain every meaningful name word; only drop terminal legal punctuation."""
    original = re.sub(r'\s+', ' ', name or '').strip()
    base = re.sub(r',?\s+(?:incorporated|inc\.?|corporation|corp\.?|llc|ltd\.?)\s*$', '', original, flags=re.I).strip(' ,')
    return list(dict.fromkeys(value for value in (original, base) if value))


def nv_verified_mark_record(row, detail):
    """A category label alone never excludes a same-name entity."""
    fields=detail.get('fields') or {};history=detail.get('filings') or {}
    norm=lambda s:re.sub(r'[^a-z0-9]','',str(s or '').lower())
    url=urlsplit(str(detail.get('source_url') or ''))
    route,_,query=url.fragment.partition('?');params=parse_qs(query)
    if (url.scheme!='https' or url.netloc!='orion.nv.gov' or url.path!='/portal/public/' or url.query
        or route!='/public/nvsos/en/CaseXscreen' or set(params)!={'screen','id'}
        or params['screen']!=['Manage-Business'] or len(params['id'])!=1
        or not re.fullmatch(r'[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}',params['id'][0])):return False
    if (fields.get('NV Business ID')!=row.get('identifier')
        or norm(fields.get('Entity Name'))!=norm(row.get('name'))
        or fields.get('Entity Type')!=row.get('entity_type')
        or str(fields.get('Solicits Charitable Contribution?') or '').casefold()!='no'
        or history.get('complete') is not True or history.get('identifier')!=row.get('identifier')
        or norm(history.get('name'))!=norm(row.get('name'))):return False
    headers=history.get('headers');rows=history.get('rows')
    expected=['Filed Date','Effective Date','Filing Number','Filing Type','Source','No. of Pages']
    if headers not in [expected,[x for x in expected if x!='Source']] or not isinstance(rows,list) or not rows or type(history.get('total')) is not int or history['total']!=len(rows):return False
    seen=set();types=[]
    for cells in rows:
        if not isinstance(cells,list) or len(cells)!=len(headers) or any(not isinstance(v,str) for v in cells):return False
        filing=dict(zip(headers,cells));number=filing['Filing Number'].strip();kind=filing['Filing Type'].strip()
        if not number or number in seen or kind not in {'Mark Registration','Mark Renewal','Cancellation'}:return False
        if not re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}',filing['Filed Date'].strip()) or not filing['No. of Pages'].strip().isdigit():return False
        seen.add(number);types.append(kind)
    return 'Mark Registration' in types


def va_effective_extension(result, parse_date, today):
    if (getattr(result, 'state', '') != 'VA' or not getattr(result, 'success', False)
            or not getattr(result, 'matched_registry_name', '')
            or not getattr(result, 'matched_registry_identifier', '')):
        return None
    raw = getattr(result, 'raw_status_text', '') or ''
    if re.search(r'\b(?:revoked|suspended|withdrawn|closed|canceled|cancelled|inactive|terminated|not\s+authorized|may\s+not|cease\s+and\s+desist|pending)\b', raw, re.I):
        return None
    fields = dict(re.findall(r'(Registration Number|Expiration Date|Extension Date):\s*([^|]+)', raw))
    if fields.get('Registration Number', '').strip() != str(result.matched_registry_identifier):
        return None
    base = parse_date(fields.get('Expiration Date', '').strip())
    extension = parse_date(fields.get('Extension Date', '').strip())
    if base and extension and extension > base and extension >= today:
        return extension
    return None
