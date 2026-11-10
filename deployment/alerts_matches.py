"""Conservative automatic confirmation and reversible Alerts match decisions."""
from hashlib import sha256
import re
import unicodedata

from psycopg.types.json import Jsonb


def match_identifier(state, identifier, name):
    """Return a stable correction key for a named, unnumbered Arkansas row."""
    if isinstance(identifier, str) and identifier.strip():
        return identifier
    if state == 'AR' and isinstance(name, str):
        normalized_name = ' '.join(unicodedata.normalize('NFKC', name).casefold().split())
        if normalized_name:
            return 'ar-name:' + sha256(normalized_name.encode()).hexdigest()
    return None


def auto_confirm(alerts, c, org, state, workflow, result):
    master=alerts.master
    if master is None or not result or result.get('source_truth_conflict'):
        return result, None
    from deployment.alerts_browser import EMAIL
    key=(org['account'],org['ein'],state)
    blocked={r['identifier'] for r in c.execute(
        'SELECT identifier FROM cc_alert_rejected_matches WHERE account=%s AND ein=%s AND state=%s',key).fetchall()}
    selected_key = match_identifier(state, result.get('matched_registry_identifier'),
                                    result.get('matched_registry_name'))
    if selected_key in blocked:
        return {**result,'confirmation_required':True}, None
    device='alerts-'+workflow
    review=result.get('identity_review')
    if not review and result.get('_worker_identity_review'):
        public={k:v for k,v in result.items() if not k.startswith(('_worker_','lab_'))}
        master.attach_identity_review(public,result['_worker_identity_review'])
        review=public.get('identity_review')
    if not isinstance(review,dict) or not review.get('token'):
        # A collector can supply a complete status and a selected record
        # without creating a review card (e.g. NC's name-only selection).
        from deployment.alerts import STATUS, SYNONYMS
        status=result.get('status')
        name=result.get('matched_registry_name')
        if (result.get('success') is True and result.get('identity_anchor')=='POSSIBLE_NAME'
                and not result.get('confirmation_required') and not result.get('_worker_identity_review')
                and not result.get('identity_review') and isinstance(status,str)
                and result.get('state')==state and result.get('app_version')==alerts.version
                and str(result.get('ein','')).replace('-','')==org['ein']
                and SYNONYMS.get(status,status) in STATUS
                and status not in {'Not Registered','Not Registered / Non-Compliant'}
                and selected_key
                and isinstance(name,str) and name.strip()):
            return {**result,'identity_anchor':'user_reviewed'}, {'identifier':selected_key,'name':name}
        return result,None
    try:
        signed=master.identity_review_unpack(review['token'],EMAIL,device)
        base=signed['base']
        if (base['state']!=state or master.canonical_ein_digits(base['ein'])!=org['ein']
                or base.get('source_truth_conflict')):
            return result,None
        records=signed['records']
        # Match the presentation order of the signed review cards. A prior
        # user rejection is sticky; the next eligible card can be selected.
        for row in records:
            identifier = row.get('identifier') or ''
            selected_key = match_identifier(state, identifier, row.get('name'))
            if row.get('reviewable') and selected_key and selected_key not in blocked:
                break
        else:
            return result,None
        token=review['token']
        if len(records)>1 and not signed.get('exclusive'):
            # Only the unattended decision selects one record here. Keep
            # the signed candidates and the ordinary status resolver intact.
            token=master.identity_review_pack({**signed,'exclusive':True})
        resolved=master.resolve_identity_review({'token':token,'candidate_id':row['id'],
            'action':'accept','state':state,'ein':base['ein']},EMAIL,device)
        if not isinstance(resolved,dict):
            return result,None
        chosen=resolved.get('matched_registry_identifier') or ''
        accepted=any(d.get('candidate_id')==row['id'] and d.get('decision')=='accept'
                     for d in resolved.get('identity_review_history',[]))
        if identifier:
            if chosen!=identifier and (chosen or not accepted or resolved.get('success') is True):
                return result,None
        elif (chosen or not accepted or (resolved.get('success') is True and
                match_identifier(state, '', resolved.get('matched_registry_name')) != selected_key)):
            return result,None
        clean={k:v for k,v in resolved.items() if k not in ('identity_review','_worker_identity_review')}
        clean.update(confirmation_required=False,checked_at_epoch=result.get('checked_at_epoch'))
        return clean,{'identifier':selected_key,'name':row['name']}
    except (TypeError,ValueError,KeyError):
        return result,None


def record(c, key, match, workflow, checked, previous):
    c.execute('INSERT INTO cc_alert_auto_matches '
              '(account,ein,state,workflow,identifier,name,checked,previous) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
              (*key,workflow,match['identifier'],match['name'],checked,Jsonb(previous)))


def correct(alerts,c,account,payload):
    ein,state,identifier,workflow=(payload.get(k) for k in ('ein','state','identifier','workflow'))
    if (not isinstance(ein,str) or not re.fullmatch(r'\d{9}',ein) or state not in alerts.states
            or not isinstance(identifier,str) or not 1<=len(identifier)<=200
            or not isinstance(workflow,str) or not 1<=len(workflow)<=100):
        raise ValueError('Invalid match correction.')
    key=(account,ein,state)
    org=c.execute('SELECT enrolled FROM cc_alert_orgs WHERE account=%s AND ein=%s AND stopped IS NULL FOR UPDATE',
                  (account,ein)).fetchone()
    if not org:
        return False
    chosen=c.execute('SELECT m.* FROM cc_alert_auto_matches m '
                     'WHERE m.account=%s AND m.ein=%s AND m.state=%s AND m.identifier=%s AND m.workflow=%s AND NOT m.corrected AND m.checked>=%s '
                     'AND NOT EXISTS (SELECT 1 FROM cc_alert_auto_matches n WHERE n.account=m.account '
                     'AND n.ein=m.ein AND n.state=m.state AND n.checked>m.checked AND NOT n.corrected) '
                     'AND NOT EXISTS (SELECT 1 FROM cc_alert_confirmed s WHERE s.account=m.account '
                     'AND s.ein=m.ein AND s.state=m.state AND s.checked>m.checked)',
                     (*key,identifier,workflow,org['enrolled'])).fetchone()
    if not chosen:
        return False
    current=c.execute('SELECT m.checked,m.previous FROM cc_alert_auto_matches m JOIN cc_alert_confirmed s '
                      'ON s.account=m.account AND s.ein=m.ein AND s.state=m.state AND s.checked=m.checked '
                      'WHERE m.account=%s AND m.ein=%s AND m.state=%s AND m.identifier=%s AND NOT m.corrected',
                      (*key,identifier)).fetchone()
    c.execute('INSERT INTO cc_alert_rejected_matches VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING',
              (*key,identifier))
    c.execute('UPDATE cc_alert_auto_matches SET corrected=true WHERE account=%s AND ein=%s AND state=%s AND identifier=%s',
              (*key,identifier))
    if current:
        c.execute('DELETE FROM cc_alert_confirmed WHERE account=%s AND ein=%s AND state=%s AND checked=%s',
                  (*key,current['checked']))
        prior=current['previous']
        if prior:
            c.execute('INSERT INTO cc_alert_confirmed VALUES (%s,%s,%s,%s,%s,%s)',
                      (*key,prior['status'],prior['evidence'],prior['checked']))
    now=alerts.now(c)
    c.execute('UPDATE cc_alert_orgs SET due=least(due,%s) WHERE account=%s AND ein=%s',(now,account,ein))
    return True
