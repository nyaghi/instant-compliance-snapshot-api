"""A Michigan name fallback must read the legal detail's labeled EIN."""
import re
import time


def materially_different(master,entered,selected):
    return master.complete_name_identity_key(entered)!=master.complete_name_identity_key(selected)


def detail_identity(master,org,frame,expected_name):
    prefix='#ctl00_MainContent_fvCSForm_'
    values={key:frame.locator(prefix+suffix).inner_text(timeout=500).strip()
        for key,suffix in {'name':'lblLegalName','ein':'lblEIN','identifier':'lblFileNo'}.items()}
    if (not re.fullmatch(r'\d{3,8}',values['identifier'])
        or master.complete_name_identity_key(values['name'])!=master.complete_name_identity_key(expected_name)):
        raise ValueError('Michigan selected detail changed identity')
    source_ein=master.canonical_ein_digits(values['ein'])
    if source_ein and len(source_ein)!=9:
        return 'possible',values
    if len(source_ein)==9:
        return ('accepted' if source_ein==master.canonical_ein_digits(org.ein) else 'rejected'),values
    return 'possible',values


def retain_candidate(master,result,values,frame,page,deadline):
    """Identity-only review; preserve this displayed original before leaving it."""
    from deployment.state_snapshots import CURRENT
    status=master.public_status(result)
    result._cc_identity_review={'search_complete':False,'records':[{
        'name':values['name'],'identifier':values['identifier'],'ein':'',
        'url':result.source_url,'raw_status':result.raw_status_text,'status':status,
        '_identity_outcome':'possible'}]}
    result.status='Needs Review';result.success=False
    result.source_note='The Michigan legal name differs from the entered name and its selected detail does not establish the requested EIN. Confirm or reject this record; a reviewed alternate name alone does not prove registration coverage.'
    run=CURRENT.get()
    if run is None or run.state!='MI' or time.perf_counter()+2>=deadline:return result
    try:
        text=master.registry_page_body(frame)
        raw=page.screenshot(type='jpeg',quality=80,full_page=True,timeout=max(1,int(min(2,deadline-time.perf_counter())*1000)))
        outcome,after=detail_identity(master,result,frame,values['name'])
        if after!=values or outcome!='possible':return result
        run.document(frame.url,raw,'image',text,note='Original Michigan candidate detail; legal identity requires confirmation because a matching EIN was not displayed.')
    except Exception as exc:
        run.errors.append('MI_candidate_capture_'+type(exc).__name__)
    return result
