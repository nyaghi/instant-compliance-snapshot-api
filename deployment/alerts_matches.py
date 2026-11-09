"""Conservative automatic confirmation and reversible Alerts match decisions."""
import re

from psycopg.types.json import Jsonb


def auto_confirm(alerts, c, org, state, workflow, result):
    master=alerts.master
    if master is None or not result or result.get('source_truth_conflict'):
        return result, None
    from deployment.alerts_browser import EMAIL
    key=(org['account'],org['ein'],state)
    blocked={r['identifier'] for r in c.execute(
        'SELECT identifier FROM cc_alert_rejected_matches WHERE account=%s AND ein=%s AND state=%s',key).fetchall()}
    if result.get('matched_registry_identifier') and result['matched_registry_identifier'] in blocked:
        return {**result,'confirmation_required':True}, None
    device='alerts-'+workflow
    review=result.get('identity_review')
    if not review and result.get('_worker_identity_review'):
        public={k:v for k,v in result.items() if not k.startswith(('_worker_','lab_'))}
        master.attach_identity_review(public,result['_worker_identity_review'])
        review=public.get('identity_review')
    if not isinstance(review,dict) or not review.get('token'):
        return result,None
    try:
        signed=master.identity_review_unpack(review['token'],EMAIL,device)
        base=signed['base']
        if (base['state']!=state or master.canonical_ein_digits(base['ein'])!=org['ein']
                or base.get('source_truth_conflict')):
            return result,None
        records=signed['records']
        exact=[r for r in records if r.get('ein') and
               master.canonical_ein_digits(r['ein'])==org['ein']]
        # When a registry doesn't expose EINs, accept its sole proposed
        # match. Never choose among competing records without a unique EIN.
        if len(exact)==1:
            row=exact[0]
        elif not exact and len(records)==1 and not records[0].get('ein'):
            row=records[0]
        else:
            return result,None
        identifier=row.get('identifier')
        if (not row.get('reviewable') or not identifier or identifier in blocked
                or row.get('group_identity')):
            return result,None
        resolved=master.resolve_identity_review({'token':review['token'],'candidate_id':row['id'],
            'action':'accept','state':state,'ein':base['ein']},EMAIL,device)
        if (not isinstance(resolved,dict) or resolved.get('success') is not True
                or resolved.get('matched_registry_identifier')!=identifier):
            return result,None
        clean={k:v for k,v in resolved.items() if k not in ('identity_review','_worker_identity_review')}
        clean.update(confirmation_required=False,checked_at_epoch=result.get('checked_at_epoch'))
        return clean,{'identifier':identifier,'name':row['name']}
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
    org=c.execute('SELECT ein FROM cc_alert_orgs WHERE account=%s AND ein=%s FOR UPDATE',
                  (account,ein)).fetchone()
    if not org:
        return False
    chosen=c.execute('SELECT m.* FROM cc_alert_auto_matches m JOIN cc_alert_confirmed s '
                     'ON s.account=m.account AND s.ein=m.ein AND s.state=m.state AND s.checked=m.checked '
                     'WHERE m.account=%s AND m.ein=%s AND m.state=%s AND m.identifier=%s AND m.workflow=%s',
                     (*key,identifier,workflow)).fetchone()
    if not chosen:
        return False
    c.execute('INSERT INTO cc_alert_rejected_matches VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING',
              (*key,identifier))
    c.execute('UPDATE cc_alert_auto_matches SET corrected=true WHERE account=%s AND ein=%s AND state=%s AND identifier=%s',
              (*key,identifier))
    c.execute('DELETE FROM cc_alert_confirmed WHERE account=%s AND ein=%s AND state=%s AND checked=%s',
              (*key,chosen['checked']))
    prior=chosen['previous']
    if prior:
        c.execute('INSERT INTO cc_alert_confirmed VALUES (%s,%s,%s,%s,%s,%s)',
                  (*key,prior['status'],prior['evidence'],prior['checked']))
    now=alerts.now(c)
    c.execute('UPDATE cc_alert_orgs SET due=least(due,%s) WHERE account=%s AND ein=%s',(now,account,ein))
    return True
