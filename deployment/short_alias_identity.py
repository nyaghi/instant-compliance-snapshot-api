"""Require independent identity evidence for short reviewed aliases.

Uses evidence already collected in this lookup. Never fetches, retries, changes
search plans, or accepts an identity on the user's behalf.
"""
import re

STATES={'ME','NH','KY','OK','SC'}
FINAL={'Current','Upcoming Filing','Delinquent','Exempt','Pending','Suspended',
       'Revoked','Failed to Renew','Closed / Withdrawn / Canceled'}

def apply(result,org,body,master):
    state=getattr(result,'state','')
    if state not in STATES or getattr(result,'_cc_identity_review',None):return
    name=str(getattr(result,'matched_registry_name','') or '').strip()
    key=lambda value:re.sub(r'[^a-z0-9]','',str(value).lower())
    original=getattr(org,'original_organization_name',None) or getattr(org,'organization_name','')
    if (not re.fullmatch(r'[A-Za-z0-9. &-]{2,12}',name)
        or not 2<=len(key(name))<=4 or key(name)==key(original)
        or key(name)not in {key(v) for v in master.known_names_for_ein(org.ein)}):return
    requested=master.canonical_ein_digits(org.ein)
    review=master.USER_IDENTITY_CONTEXT.get()
    accepted=review.get('accepted',{})
    if (review.get('ein')==requested and review.get('state')==state
        and accepted.get('identifier')==str(getattr(result,'matched_registry_identifier',''))
        and key(accepted.get('name',''))==key(name)):
        return  # Existing signed Kentucky decision, scoped to this exact row.
    verified=master.canonical_ein_digits(getattr(result,'verified_registry_ein',''))
    address=getattr(result,'address_evidence',{}) or {}
    if verified==requested and len(requested)==9:return
    if address.get('decision') in {'same_ein','corroborated'}:return
    # A hard EIN mismatch is never offered as a user-overridable identity.
    if verified or address.get('decision')=='different_ein':
        result.status='Unable to Confirm';result.success=False
        result.reason_code='SHORT_ALIAS_EIN_CONFLICT'
        result.source_note='The short-name candidate has a conflicting EIN and was not accepted.'
        return
    identifier=str(getattr(result,'matched_registry_identifier','') or '')
    try:status=master.true_status_from_body(result,body)
    except (ValueError,TypeError):status='Unable to Confirm'
    raw=str(getattr(result,'raw_status_text','') or '')
    expiry=''
    if state=='ME':
        readable=re.sub(r'\s+',' ',master.html_to_text(body or '')).strip()
        # This is a provisional candidate classification, never the main result.
        # Read only its bound credential block, not a nearby organization's row.
        bound=re.search(r'\bLicense\s+Number\s*:?\s*'+re.escape(identifier)+r'\b',readable,re.I) if identifier else None
        standing=re.search(r'\bStatus\s*:?\s*([A-Za-z][A-Za-z /-]+?)\s+Expiration\s+Date\s*:?\s*(\d{1,2}/\d{1,2}/\d{4})',readable,re.I)
        if bound and standing:
            raw=standing[1].strip();expiry=standing[2]
            due=master.parse_due_date(expiry)
            if due and raw.lower() in {'active','current','registered'}:status=master.status_from_calendar_date(due)
    if not expiry:
        due=getattr(result,'computed_due_date',None)
        if due:expiry=due.isoformat() if hasattr(due,'isoformat') else str(due)
    result.status='Needs Review';result.success=False
    result.reason_code='SHORT_ALIAS_IDENTITY_REVIEW'
    result.status_reason='SHORT_ALIAS_IDENTITY_UNCONFIRMED'
    location=address.get('registry_location','')
    result.source_note=(f'{state} returned {name} ({identifier}), a short alternate name shared by unrelated organizations. '
        'The checked alternate name alone does not confirm this state record belongs to the requested EIN. '
        'Review the original record and accept or reject its identity before relying on its status.')
    if address.get('decision')=='conflict':
        result.source_note+=f" The registry location {location} conflicts with the EIN-linked location {address.get('ein_linked_location','')}."
    # Incomplete records stay incomplete. A complete, bound candidate can use
    # the existing signed review transport without an additional source query.
    if identifier and status in FINAL:
        result._cc_identity_review={'records':[{'name':name,'identifier':identifier,
            'ein':'','url':getattr(result,'source_url',''),'location':location,
            'raw_status':raw,'expiration':expiry,'status':status,
            '_identity_outcome':'conflict' if address.get('decision')=='conflict' else 'possible'}],
            'search_complete':False,'freshness':''}

def preserves_review_match(result):
    """Keep a bound pending candidate; never turn it into an accepted identity."""
    state=getattr(result,'state','')
    reason=getattr(result,'reason_code','')
    if not ((state in STATES and reason=='SHORT_ALIAS_IDENTITY_REVIEW')
            or (state=='WV' and reason=='WV_SHORT_NAME_IDENTITY_UNCONFIRMED')):return False
    rows=(getattr(result,'_cc_identity_review',None) or {}).get('records',[])
    return (len(rows)==1 and rows[0].get('status') in FINAL
        and rows[0].get('name')==getattr(result,'matched_registry_name','')
        and str(rows[0].get('identifier') or '')==str(getattr(result,'matched_registry_identifier',''))
        and bool(rows[0].get('name')) and bool(rows[0].get('identifier')))

def visual_result(data):
    """Use the exact signed-review candidate for pixels, preserving the public result."""
    if not isinstance(data,dict):return data
    state=data.get('state');reason=data.get('reason_code')
    if state=='RI':
        # The master has retrieved this candidate but has not confirmed identity.
        # Photograph only its validated official detail; never promote its status.
        context=data.get('_worker_identity_review') or {}
        rows=context.get('records',[])
        if context.get('search_complete') is not True or len(rows)!=1:return data
        row=rows[0]
        if (row.get('status') not in FINAL or not row.get('name')
            or row.get('_identity_outcome') not in {'possible','conflict'}
            or row.get('ein') and re.sub(r'\D','',str(row['ein']))!=re.sub(r'\D','',str(data.get('ein','')))
            or not re.fullmatch(r'CO\.\d+',str(row.get('identifier','')))
            or not re.fullmatch(r'https://ridbrprod-search\.state-reg-eastern\.tylerapp\.com/search/C\d+/detail',str(row.get('url','')))):
            return data
        return {**data,'status':row['status'],'success':True,
            'matched_registry_name':row['name'],'matched_registry_identifier':row['identifier'],'source_url':row['url']}
    if not ((state in {'ME','SC'} and reason=='SHORT_ALIAS_IDENTITY_REVIEW')
            or (state=='WV' and reason=='WV_SHORT_NAME_IDENTITY_UNCONFIRMED')):return data
    rows=(data.get('_worker_identity_review') or {}).get('records',[])
    if len(rows)!=1:return data
    row=rows[0];identifier=str(row.get('identifier') or '')
    if (row.get('status') not in FINAL or row.get('name')!=data.get('matched_registry_name')
        or identifier!=str(data.get('matched_registry_identifier') or '') or not identifier
        or row.get('url')!=data.get('source_url')
        or row.get('_identity_outcome') not in {'possible','conflict'}):return data
    return {**data,'status':row['status'],'success':True}
