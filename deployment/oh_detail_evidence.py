"""Prefer an already captured Ohio detail over its selected search row."""
import re
from urllib.parse import urlsplit,parse_qs

def bound(doc,row,ein):
    url,raw,kind,text,stamp,note=doc
    if kind!='image':return False
    u=urlsplit(url);q=parse_qs(u.query)
    identifier=str(row.get('matched_registry_identifier') or row.get('identifier') or '')
    if (u.scheme!='https' or u.hostname!='charitableregistration.ohioago.gov'
        or u.path not in {'/Charities/OrganizationDetails','/Charities/PartiallyExemptOrganization'}
        or not identifier or q.get('Id')!=[identifier]):return False
    identity=re.search(r'Employer Identification Number\s*\(EIN\)\s*:?\s*(\d{2}-?\d{7})\b',text,re.I)
    if not identity or re.sub(r'\D','',identity[1])!=ein:return False
    return (all(label in text for label in ('Organization Name','Fiscal Year End'))
            and any(label in text for label in ('Registration Status','Exemption Status'))
            and not re.search(r'Server Error|Runtime Error|verify you are human|access denied',text,re.I))

def select(run,ordered,row):
    if run.state!='OH':return ordered
    details=[doc for doc in ordered if bound(doc,row,run.ein)]
    run.visual_adapter_facts.append({'adapter':'OH-original-selected-detail',
        'outcome':'selected' if details else 'detail_unavailable',
        'additional_source_requests':0})
    return details+[doc for doc in ordered if doc not in details]
