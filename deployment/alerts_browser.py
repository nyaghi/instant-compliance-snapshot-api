"""Run scheduled connector checks in an enrolled customer's Chrome profile."""
import json
import re
import secrets

from psycopg.types.json import Jsonb

from deployment.alerts import TERMINAL, digest, observation

STATES = frozenset(('AL', 'GA', 'IL', 'MS', 'NC', 'NM', 'NV', 'NY', 'TN'))
FINAL_FOUR = frozenset(('AL', 'MS', 'NC', 'NM', 'NV', 'TN'))
LEASE_SECONDS = 420
TOKEN = re.compile(r'[A-Za-z0-9_-]{43}')
EMAIL = 'alerts-runner@compliance-express.com'
SCHEMA = """
CREATE TABLE IF NOT EXISTS cc_alert_browser_profiles (
    secret text PRIMARY KEY, account text NOT NULL REFERENCES cc_alert_accounts,
    created double precision NOT NULL
);
CREATE TABLE IF NOT EXISTS cc_alert_browser_runs (
    workflow text PRIMARY KEY, account text NOT NULL, ein text NOT NULL,
    secret text NOT NULL UNIQUE, expires double precision NOT NULL,
    finished boolean NOT NULL DEFAULT false, results jsonb NOT NULL,
    FOREIGN KEY(account, ein) REFERENCES cc_alert_orgs
);
"""


def enable(alerts,c,account):
    secret=secrets.token_urlsafe(32)
    now=alerts.now(c)
    c.execute('DELETE FROM cc_alert_browser_profiles WHERE account=%s AND created<%s',
              (account,now-90*86400))
    c.execute('INSERT INTO cc_alert_browser_profiles VALUES (%s,%s,%s)',(digest(secret),account,now))
    c.execute('UPDATE cc_alert_accounts SET monitoring=true WHERE account=%s',(account,))
    return {'profile':secret}


def claim(alerts, c, account, profile):
    if (not isinstance(profile,str) or not TOKEN.fullmatch(profile)
            or not c.execute('SELECT 1 FROM cc_alert_browser_profiles WHERE account=%s AND secret=%s AND created>=%s',
                             (account,digest(profile),alerts.now(c)-90*86400)).fetchone()):
        raise ValueError('This Chrome profile is not connected to Alerts.')
    from deployment.durable_queue import normalize_submission
    if not c.execute('SELECT pg_try_advisory_xact_lock(824527332) AS ok').fetchone()['ok']:
        return {'retry': True}
    now = alerts.now(c)
    org = c.execute('SELECT o.* FROM cc_alert_orgs o JOIN cc_alert_accounts a USING(account) '
                    'WHERE o.account=%s AND a.monitoring AND o.due<=%s ORDER BY o.due,o.ein LIMIT 1',
                    (account, now)).fetchone()
    if not org:
        return {}
    if c.execute('SELECT 1 FROM cc_alert_orgs WHERE workflow IS NOT NULL LIMIT 1').fetchone():
        return {'retry': True}
    if c.execute('SELECT 1 FROM cc_lab_workflows WHERE finished IS NULL LIMIT 1').fetchone():
        return {'retry': True}
    states = alerts.states & STATES
    payload = normalize_submission(dict(organization_name=org['name'], ein=org['ein'],
        alternate_names=org['aliases'], states=sorted(alerts.states - states),
        state_concurrency=10), alerts.states)
    key = f"browser:{org['ein']}:{int(org['due']*1000)}"
    ident, _ = alerts.queue.submit('alerts:'+account, key, payload, alerts.version)
    token = secrets.token_urlsafe(32)
    c.execute('INSERT INTO cc_alert_browser_runs (workflow,account,ein,secret,expires,results) '
              'VALUES (%s,%s,%s,%s,%s,%s)',
              (ident, account, org['ein'], digest(token), now+LEASE_SECONDS, Jsonb({})))
    c.execute('UPDATE cc_alert_orgs SET workflow=%s WHERE account=%s AND ein=%s',
              (ident, account, org['ein']))
    return {'lease':token, 'name':org['name'], 'ein':org['ein'], 'aliases':org['aliases'],
            'states':sorted(states)}


def lease(alerts, c, account, token):
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        return None
    return c.execute('SELECT b.*,o.name,o.aliases FROM cc_alert_browser_runs b '
                     'JOIN cc_alert_orgs o ON o.account=b.account AND o.ein=b.ein AND o.workflow=b.workflow '
                     'WHERE b.account=%s AND b.secret=%s AND NOT b.finished AND b.expires>%s',
                     (account, digest(token), alerts.now(c))).fetchone()


def merge(alerts, c, run):
    row = c.execute('SELECT * FROM cc_alert_browser_runs WHERE workflow=%s FOR UPDATE',
                    (run['id'],)).fetchone()
    if row is None:
        return run
    now = alerts.now(c)
    if not row['finished'] and row['expires']>now:
        return None
    finished = max(run['finished'], min(now,row['expires']))
    jobs = [{'state':state,'phase':'done','finished':result.get('checked_at_epoch',finished),
             'result':result} for state,result in row['results'].items()]
    jobs.extend({'state':state,'phase':'done','finished':finished,'result':None}
                for state in (alerts.states & STATES) - set(row['results']))
    c.execute('DELETE FROM cc_alert_browser_runs WHERE workflow=%s',(run['id'],))
    return {**run,'finished':finished,'jobs':[*run['jobs'],*jobs]}


def lookup(alerts, master, handler, origin):
    """Run the normal signed collector API using the account-bound lease."""
    if handler.headers.get('Origin') != origin:
        return handler._send_json(403, {'error':'Invalid request origin.'})
    from deployment.state_snapshots import PostgresStore, STORE_OVERRIDE
    try:
        length = int(handler.headers.get('Content-Length','0'))
        if not 0 < length <= 8100000:
            raise ValueError('Invalid connector input.')
        payload = json.loads(handler.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError('Invalid connector input.')
        with alerts.transaction() as c:
            account = alerts.account(c, handler)
            row = lease(alerts,c,account,payload.pop('alert_lease',None)) if account else None
        if not row:
            return handler._send_json(403,{'error':'This scheduled check has expired.'})
        state = payload.pop('alert_state',None)
        if state not in alerts.states & STATES:
            raise ValueError('Unsupported connector state.')
        device = 'alerts-'+row['workflow']
        action = payload.get('action')
        if action == 'start':
            # The lease supplies all organization and identity fields.
            payload = {k:payload[k] for k in ('action','evidence_protocol','recovery_protocol','connector_version')
                       if k in payload}
            payload.update(state=state,ein=row['ein'],organization_name=row['name'],
                           alternate_names=row['aliases'],mode='standard',purpose='registration')
        else:
            record = master.ny_connector_unpack(payload.get('check_token'),EMAIL,device)
            if record['state'] != state or master.canonical_ein_digits(record['ein']) != row['ein']:
                raise ValueError('Connector check scope changed.')
        payload.update(email=EMAIL,device_id=device,admin_passcode=master.ADMIN_PASSCODE)
        override=STORE_OVERRIDE.set(PostgresStore(alerts.queue.pool,alerts_owner=(row['workflow'],state)))
        try:
            handler_fn = master.final_four_connector_request if state in FINAL_FOUR else master.ny_connector_request
            code,response = handler_fn(payload,origin)
        finally:
            STORE_OVERRIDE.reset(override)
        result=response.get('result')
        if code==200 and response.get('phase')=='complete' and isinstance(result,dict):
            retain(alerts,row,state,result)
        return handler._send_json(code,response,{'Cache-Control':'no-store'})
    except (ValueError, TypeError, KeyError, UnicodeError):
        return handler._send_json(400,{'error':'Invalid or expired connector check.'})
    except Exception as exc:
        master.log_error('Alerts connector failed: '+type(exc).__name__)
        return handler._send_json(503,{'error':'The scheduled registry check could not finish.'})


def retain(alerts, lease_row, state, result):
    fields = ('ein','state','app_version','status','success','error','confirmation_required','identity_review',
              'identity_anchor','source_truth_conflict','matched_registry_identifier','matched_registry_name','evidence_url',
              'search_history_url')
    with alerts.transaction() as c:
        now=alerts.now(c)
        row=c.execute('SELECT * FROM cc_alert_browser_runs WHERE workflow=%s AND NOT finished AND expires>%s FOR UPDATE',
                      (lease_row['workflow'],now)).fetchone()
        if not row:
            return
        candidate={key:result[key] for key in fields if key in result}
        candidate['checked_at_epoch']=now
        prior=row['results'].get(state)
        # A follow-up snapshot may complete Alabama's initial result. A failed
        # follow-up must never displace a result with verified evidence.
        def confirmed(value):
            return observation({'state':state,'phase':'done','result':value},row['ein'],0,now,alerts.version)[1]
        if prior and (confirmed(prior) or prior.get('identity_review')) and not (
                confirmed(candidate) or candidate.get('identity_review')):
            return
        rows={**row['results'],state:candidate}
        c.execute('UPDATE cc_alert_browser_runs SET results=%s WHERE workflow=%s',(Jsonb(rows),row['workflow']))
