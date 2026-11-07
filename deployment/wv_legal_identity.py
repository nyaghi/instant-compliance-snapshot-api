"""Prefer a fully corroborated legal-name/DBA record over an obsolete name-only hit."""
import re
import time


def choose(master,org,best,candidates,lookup,deadline):
    if lookup is None or not best or not re.fullmatch(r'expired|closed|inactive',best[3],re.I):
        return None
    targets={master.complete_name_identity_key(n) for n in master.known_names_for_ein(org.ein)}
    options=[r for r in candidates if r[1]!=best[1] and len(master.distinctive_match_tokens(r[2]))>=3
        and master.complete_name_identity_key(r[2]) in targets]
    if not 1<=len(options)<=3:return None
    proven=[]
    for item in options:
        if time.perf_counter()+2>=deadline:return None
        text=lookup.detail(item[0],item[1])
        name=master.text_between_labels(text,'Organization Name',['Expiration Date','Contact Name','Status','Street Address'])
        if master.complete_name_identity_key(name)!=master.complete_name_identity_key(item[2]):continue
        dba=re.search(r'(?im)^DBA\s*\r?\nName\s*\r?\n([^\r\n]+)',text)
        if not dba or master.complete_name_identity_key(dba[1])!=master.complete_name_identity_key(org.organization_name):continue
        address=master.text_between_labels(text,'Street Address',['County','Mailing Address'])
        match=re.fullmatch(r'(.+?),\s*([^,]+),\s*([A-Z]{2})\s+(\d{5})(?:\s*-\s*\d{4})?(?:,\s*USA)?',address.strip(),re.I)
        if not match:continue
        row={'name':name,'street':match[1],'location':match[2]+', '+match[3],
            'region':match[3],'postal_code':match[4]}
        proof=master.licensed_charity_street_evidence(org,row,time.monotonic()+max(0,deadline-time.perf_counter()))
        if proof.get('decision')!='corroborated':continue
        expiry=master.parse_due_date(master.text_between_labels(text,'Expiration Date',['Contact Name','Status','Street Address']))
        status=master.text_between_labels(text,'Status',['Street Address','County'])
        proven.append((item,text,proof,expiry,status))
    if not proven:return None
    if len(proven)>1:
        # Date comparison is allowed only after each record's full legal name,
        # displayed DBA and EIN-linked organization office have been proved.
        if any(p[3] is None for p in proven):return None
        latest=max(p[3] for p in proven)
        proven=[p for p in proven if p[3]==latest]
        if len(proven)!=1:return None
    item,text,proof,expiry,status=proven[0]
    lookup.body=text
    return item,text,{'legal_name':item[2],'detail_dba':org.organization_name,'office':proof,
        'selection_basis':'Verified legal name, explicit source DBA and full EIN-linked organization office outrank an obsolete short-name-only hit.'}
