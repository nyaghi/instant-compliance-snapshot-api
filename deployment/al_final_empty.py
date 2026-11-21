"""Final empty-page capture after the existing Alabama decision is settled."""
import copy
PROTOCOL='al-final-empty-v1'

def prepare(master,record,response):
    """Completed negatives use the names-searched PDF, without another capture."""
    return response


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
