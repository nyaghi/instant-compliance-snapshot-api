"""Final empty-page capture after the existing Alabama decision is settled."""
import copy,secrets,time
PROTOCOL='al-final-empty-v1'

def prepare(master,record,response):
    """An optional signed capture continuation; no source lookup or new decision."""
    from deployment.state_snapshots import completed_negative_result,matching_reference
    result=response.get('result')
    if (record.get('state')!='AL' or record.get('al_evidence_protocol')!=PROTOCOL
        or response.get('phase')!='complete' or not isinstance(result,dict)
        or not completed_negative_result(result) or record.get('al_final_empty')
        or record.get('expires',0)-time.time()<4
        or matching_reference(result,record.get('source_snapshots',[]))):return response
    completed=record.get('completed',[])
    if not completed:return response
    last=completed[-1];query=last.get('query',{});evidence=last.get('evidence',{})
    # Only an actual, last completed empty grid may be captured in place.
    # Nonempty unrelated grids need separate source-image support; never pretend zero.
    if (query.get('state')!='AL' or query.get('operation')!='search'
        or evidence.get('query')!=query or evidence.get('complete') is not True
        or evidence.get('verification_pending') is not False or evidence.get('total')!=0
        or evidence.get('rows')!=[]):return response
    frozen=copy.deepcopy(record)
    qid=secrets.token_urlsafe(18)
    frozen['al_final_empty']={'query_id':qid,'query':query,'result':result}
    try:token=master.ny_connector_pack(frozen)
    except (ValueError,TypeError):return response
    return {'phase':'capture_empty','query_id':qid,'query':query,'result':result,
            'check_token':token,'lookup_remaining_ms':max(0,int((record['expires']-time.time())*1000))}

def complete(master,record,payload):
    from deployment.state_snapshots import connector_archive,attach_links
    from deployment.search_history import attach
    pending=record.get('al_final_empty')
    if (record.get('state')!='AL' or record.get('al_evidence_protocol')!=PROTOCOL
        or not isinstance(pending,dict) or payload.get('query_id')!=pending.get('query_id')
        or not record.get('completed') or record['completed'][-1].get('query')!=pending.get('query')):
        return 409,{'error':'The capture is stale or belongs to another registry query.'}
    last=record['completed'][-1]
    # Reuse only signed, previously cleaned evidence; ignore payload evidence/status.
    before=copy.deepcopy(record.get('source_snapshots',[]))
    connector_archive(record,payload,pending['query'],last['evidence'])
    if before==record.get('source_snapshots',[]):
        return 200,{'phase':'complete','result':copy.deepcopy(pending['result'])}
    result=attach_links(copy.deepcopy(pending['result']),record.get('source_snapshots',[]))
    return 200,{'phase':'complete','result':attach(record,result)}
