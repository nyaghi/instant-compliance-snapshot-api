"""Optional NC filing dates only after the unchanged identity/status selection."""

CORE=('name','identifier','raw_status','status','expiration','license_category',
      'street','location','postal_code','region','source_last_application')
RENEWAL=('renewal','renewal_label','renewal_type','renewal_url')


def enrich(master,result,collect):
    row=getattr(result,'_cc_license_record',None)
    if (result.state!='NC' or not result.success or not isinstance(row,dict)
            or getattr(result,'_cc_identity_review',None)
            or row.get('identifier')!=getattr(result,'matched_registry_identifier',None)
            or not str(row.get('identifier','')).startswith(('SL','EX'))):
        return result
    query=dict(state='NC',operation='detail',identifier=row['identifier'],url=row['url'],history='selected')
    # NYConnectorQueryNeeded is deliberately propagated for the signed browser
    # continuation. A missing optional history never becomes non-registration.
    try:
        detail=collect(query)
    except TimeoutError:
        return result
    try:
        master.final_four_clean_evidence(detail,query)
        bound=master.nc_charity_profile_evidence(row,detail['fields'])
        if any(bound.get(k)!=row.get(k) for k in CORE):
            raise ValueError('Selected NC profile changed during optional history')
        history=detail.get('filings')
        if history is not None:
            enriched=master.nc_charity_profile_evidence(row,detail['fields'],history)
            for k in RENEWAL:
                if k in enriched:row[k]=enriched[k]
    except (ValueError,KeyError,TypeError):
        note="North Carolina's renewal filing history was incomplete; the last-renewal date remains blank."
        row['date_evidence_note']=note
        if note not in result.source_note:result.source_note+=' '+note
    return result
