"""Qualified WA EIN discrepancies are identity questions, never automatic matches."""
import re
import time
import copy


def key(value):
    words=re.findall(r'[a-z0-9]+',str(value).casefold())
    while words and words[-1] in {'inc','incorporated','corp','corporation','llc','ltd'}:words.pop()
    return ' '.join(words)


def possible(name,source_name,requested,observed):
    digits=lambda s:re.sub(r'\D','',str(s))
    a,b=digits(requested),digits(observed)
    return (len(a)==len(b)==9 and b!='000000000' and sum(x!=y for x,y in zip(a,b))==1
        and len(key(name).split())>=2 and key(name)==key(source_name))


def allowed(row,name,ein):
    proof=row.get('wa_ein_conflict')
    return bool(isinstance(proof,dict) and proof.get('office_correlated') is True
        and proof.get('requested_ein')==re.sub(r'\D','',str(ein))
        and proof.get('source_ein')==re.sub(r'\D','',str(row.get('ein','')))
        and proof.get('identifier')==str(row.get('identifier',''))
        and proof.get('name')==row.get('name') and possible(name,row.get('name'),ein,row.get('ein'))
        and re.fullmatch(r'\d{1,20}',str(row.get('identifier','')))
        and row.get('url')=='https://ccfs.sos.wa.gov/#/cftSearch')


def build(master,result,body):
    observed=master.wa_detail_field(body,'FEIN Number')
    name=master.wa_detail_field(body,'Organization Name')
    number=master.wa_detail_field(body.replace('\u00a0',' '),'Registration Number')
    chosen=getattr(result,'_wa_name_conflict',None)
    if (not isinstance(chosen,dict) or master.canonical_ein_digits(chosen.get('FEINNumber',''))!=master.canonical_ein_digits(observed)
        or key(chosen.get('EntityName'))!=key(name) or not re.fullmatch(r'\d{1,20}',number)
        or not possible(result.organization_name,name,result.ein,observed)):
        return None
    address=master.wa_detail_field(body.replace('\u00a0',' '),'Street Address')
    parts=[s.strip() for s in address.split(',')]
    if len(parts)<4 or not re.fullmatch(r'[A-Z]{2}',parts[2]) or not re.match(r'\d{5}',parts[3]):return None
    street=master.registry_street_key(parts[0]);proof=None
    # Missing unit on the registry is permitted for review only; a conflicting
    # displayed unit or a different building must not pass this comparison.
    base=lambda s:re.sub(r'\s+(?:STE|SUITE|UNIT)\s+\w+$','',s)
    from deployment.state_snapshots import DEADLINE
    deadline=min(time.monotonic()+8,DEADLINE.get()-1)
    for source in ('CA','CO'):
        if time.monotonic()>=deadline:break
        try:
            records=master.identity_source_result(source,master.canonical_ein_digits(result.ein),deadline).get('organization_records',[])
        except Exception:continue
        for row in records:
            other=master.registry_street_key(row.get('street',''))
            if (row.get('address_role')!='organization' or master.canonical_ein_digits(row.get('ein',''))!=master.canonical_ein_digits(result.ein)
                or str(row.get('state','')).upper()!=parts[2] or str(row.get('postal_code',''))[:5]!=parts[3][:5]
                or not any(key(n)==key(name) for n in row.get('names',[]))
                or not street or not (street==other or base(street)==street and street==base(other))):continue
            proof={'requested_ein':master.canonical_ein_digits(result.ein),'source_ein':master.canonical_ein_digits(observed),
                'name':name,'identifier':number,'office_correlated':True}
            break
        if proof:break
    if not proof:return None
    proxy=copy.copy(result);proxy.ein=observed;proxy._wa_name_conflict=None
    proxy=master.wa_apply_detail_master(proxy,body)
    standing=master.public_status(proxy)
    if standing not in {'Current','Upcoming Filing','Delinquent','Exempt','Pending','Suspended','Revoked','Closed / Withdrawn / Canceled'}:return None
    result._cc_identity_review={'search_complete':True,'records':[{
        'name':name,'ein':proof['source_ein'],'identifier':number,'url':result.source_url,
        'raw_status':proxy.raw_status_text,'status':standing,'expiration':master.wa_detail_field(body,'Renewal Date'),
        'wa_ein_conflict':proof,'_identity_outcome':'conflict'}]}
    result.status='Needs Review';result.success=False;result.reason_code='WA_CORROBORATED_EIN_CONFLICT_REVIEW'
    result.matched_registry_name=name;result.matched_registry_identifier=number
    result.raw_status_text='Washington EIN conflict: entered '+proof['requested_ein']+'; registry '+proof['source_ein']+'. '+proxy.raw_status_text
    result.source_note='The exact legal name and organization office corroborate a possible record, but the EIN differs. Review the original and accept or reject this identity. CharityClarity has not assumed the difference is a typo or changed either EIN.'
    return result
