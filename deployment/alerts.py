"""Persistent, account-scoped CharityClarity Alerts pilot."""
from contextlib import contextmanager
from datetime import datetime
from hashlib import sha256
import json
import re
import secrets
from http.cookies import CookieError, SimpleCookie
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

DAY = 86400
HISTORY_DAYS = 10
COOKIE = '__Host-cc_alerts'
ET = ZoneInfo('America/New_York')
SNAPSHOT = re.compile(r'/state-snapshots/[a-f0-9]{64}\.pdf\Z')
HISTORY = re.compile(r'/state-evidence/[a-f0-9]{64}/search-history\.pdf\Z')
TERMINAL = {'completed', 'expired', 'canceled'}
STATUS = {
    'Current': 0, 'Exempt': 0, 'Upcoming Filing': 1,
    'Pending': 2, 'Pending / In Process': 2,
    'Delinquent': 3, 'Failed to Renew': 3, 'Not Registered': 3,
    'Not Registered / Non-Compliant': 3,
    'Closed / Withdrawn / Canceled': 4,
    'Revoked / Suspended': 4, 'Revoked': 4, 'Suspended': 4,
}
SYNONYMS = {'Pending / In Process': 'Pending',
            'Closed / Withdrawn / Canceled / Inactive': 'Closed / Withdrawn / Canceled',
            'Not Registered / Non-Compliant': 'Not Registered / Non-Compliant'}
SCHEMA = """
CREATE TABLE IF NOT EXISTS cc_alert_accounts (
    account text PRIMARY KEY, monitoring boolean NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS cc_alert_sessions (
    secret text PRIMARY KEY, account text NOT NULL REFERENCES cc_alert_accounts,
    expires double precision NOT NULL, claim boolean NOT NULL
);
CREATE TABLE IF NOT EXISTS cc_alert_orgs (
    account text REFERENCES cc_alert_accounts, ein text, name text NOT NULL,
    aliases jsonb NOT NULL, enrolled double precision NOT NULL,
    due double precision NOT NULL, workflow text,
    PRIMARY KEY(account, ein)
);
CREATE TABLE IF NOT EXISTS cc_alert_checks (
    account text, ein text, state text, workflow text, checked double precision NOT NULL,
    status text, evidence text, failure text,
    PRIMARY KEY(account, ein, state, workflow),
    FOREIGN KEY(account, ein) REFERENCES cc_alert_orgs,
    CHECK ((status IS NULL) <> (failure IS NULL))
);
CREATE TABLE IF NOT EXISTS cc_alert_confirmed (
    account text, ein text, state text, status text NOT NULL, evidence text NOT NULL,
    checked double precision NOT NULL, PRIMARY KEY(account, ein, state),
    FOREIGN KEY(account, ein) REFERENCES cc_alert_orgs
);
CREATE TABLE IF NOT EXISTS cc_alert_changes (
    id bigserial PRIMARY KEY, account text, ein text, state text NOT NULL, workflow text NOT NULL,
    previous text NOT NULL, status text NOT NULL, evidence text NOT NULL,
    direction text NOT NULL, checked double precision NOT NULL, seen double precision,
    UNIQUE(account, ein, state, workflow), FOREIGN KEY(account, ein) REFERENCES cc_alert_orgs
);
CREATE TABLE IF NOT EXISTS cc_alert_artifacts (
    id text PRIMARY KEY REFERENCES cc_state_snapshots ON DELETE CASCADE,
    workflow text NOT NULL, state text NOT NULL, created double precision NOT NULL
);
CREATE TABLE IF NOT EXISTS cc_alert_auto_matches (
    account text, ein text, state text, workflow text, identifier text NOT NULL,
    name text NOT NULL, checked double precision NOT NULL, previous jsonb,
    corrected boolean NOT NULL DEFAULT false,
    PRIMARY KEY(account,ein,state,workflow), FOREIGN KEY(account,ein) REFERENCES cc_alert_orgs
);
CREATE TABLE IF NOT EXISTS cc_alert_rejected_matches (
    account text, ein text, state text, identifier text,
    PRIMARY KEY(account,ein,state,identifier), FOREIGN KEY(account,ein) REFERENCES cc_alert_orgs
);
CREATE INDEX IF NOT EXISTS cc_alert_artifacts_group ON cc_alert_artifacts(workflow,state);
CREATE INDEX IF NOT EXISTS cc_alert_artifacts_age ON cc_alert_artifacts(created);
CREATE INDEX IF NOT EXISTS cc_alert_confirmed_evidence ON cc_alert_confirmed(evidence);
CREATE INDEX IF NOT EXISTS cc_alert_changes_evidence ON cc_alert_changes(evidence);
CREATE INDEX IF NOT EXISTS cc_alert_changes_account ON cc_alert_changes(account,id DESC);
CREATE INDEX IF NOT EXISTS cc_alert_checks_account_time ON cc_alert_checks(account,checked DESC);
"""


def digest(value):
    return sha256(value.encode()).hexdigest()


def classify_change(previous, status):
    if previous is None or previous == status:
        return None
    if STATUS[status] > STATUS[previous]:
        return 'adverse'
    if STATUS[status] < STATUS[previous]:
        return 'favorable'
    return 'other'


def observation(job, ein, submitted, finished, version):
    result = job.get('result') or {}
    checked = job.get('finished') or finished
    captured = result.get('checked_at_epoch')
    if type(captured) in (int, float) and submitted-1 <= captured <= checked+1:
        checked = captured
    status = result.get('status', '')
    status = SYNONYMS.get(status, status)
    if job.get('error') or job.get('phase') != 'done' or not result:
        return checked, None, None, 'Check did not complete'
    if (str(result.get('ein', '')).replace('-', '') != ein or result.get('state') != job['state']
            or result.get('app_version') != version):
        return checked, None, None, 'Result identity could not be verified'
    if (result.get('confirmation_required') or result.get('_worker_identity_review')
            or result.get('identity_review') or result.get('source_truth_conflict')
            or result.get('identity_anchor') == 'POSSIBLE_NAME'):
        return checked, None, None, 'Identity or source needs confirmation'
    if (result.get('success') is not True or result.get('error') or status not in STATUS):
        return checked, None, None, 'Registry unavailable or result unconfirmed'
    snapshot = str(result.get('evidence_url') or '')
    history = str(result.get('search_history_url') or '')
    if status in {'Not Registered', 'Not Registered / Non-Compliant'}:
        evidence = history if HISTORY.fullmatch(history) else snapshot if SNAPSHOT.fullmatch(snapshot) else ''
    else:
        evidence = snapshot if SNAPSHOT.fullmatch(snapshot) else ''
    return checked, status, evidence, None


class Alerts:
    def __init__(self, queue, states, version, master=None):
        self.queue, self.states, self.version = queue, frozenset(states), version
        self.master = master

    @contextmanager
    def transaction(self):
        with self.queue.pool.connection() as c, c.transaction():
            yield c

    def initialize(self):
        with self.transaction() as c:
            c.execute('SELECT pg_advisory_xact_lock(824527331)')
            c.execute(SCHEMA)
            if self.master is not None:
                from deployment.alerts_browser import SCHEMA as browser_schema
                c.execute(browser_schema)

    @staticmethod
    def now(c):
        return float(c.execute('SELECT extract(epoch FROM clock_timestamp()) AS t').fetchone()['t'])

    def enroll(self, c, account, name, ein, enrolled, aliases=()):
        if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 300 or not isinstance(ein, str)
                or not re.fullmatch(r'[0-9]{2}-?[0-9]{7}', ein) or ein.replace('-', '') == '000000000'):
            raise ValueError('Enter an organization name and a valid EIN.')
        return bool(c.execute('INSERT INTO cc_alert_orgs (account,ein,name,aliases,enrolled,due) '
                              'VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING ein',
                              (account, ein.replace('-', ''), name.strip(), Jsonb(list(aliases)), enrolled, enrolled)).fetchone())

    def apply(self, c, org, run):
        """Apply only a terminal, exact-EIN workflow. Per-state first success is silent."""
        if (run['phase'] not in TERMINAL or run['ein'] != org['ein'] or run['kind'] != 'registration'
                or run['source_version'] != self.version or run['submitted'] < org['enrolled'] - 1):
            raise ValueError('The check does not belong to this enrollment.')
        by_state = {j['state']: j for j in run['jobs']}
        if set(by_state) != self.states or len(by_state) != len(run['jobs']):
            raise ValueError('The check does not contain the enrolled state set.')
        c.execute('SELECT ein FROM cc_alert_orgs WHERE account=%s AND ein=%s FOR UPDATE',
                  (org['account'], org['ein']))
        from deployment.alerts_matches import auto_confirm, record
        for state, job in sorted(by_state.items()):
            result, match = auto_confirm(self,c,org,state,run['id'],job.get('result'))
            if result is not job.get('result'):
                job = {**job,'result':result}
            checked, status, evidence, failure = observation(job, org['ein'], run['submitted'],
                                                            run['finished'], self.version)
            org_key = (org['account'], org['ein'], state)
            inserted = c.execute('INSERT INTO cc_alert_checks VALUES (%s,%s,%s,%s,%s,%s,%s,%s) '
                                 'ON CONFLICT DO NOTHING RETURNING state',
                                 (*org_key, run['id'], checked, status, evidence, failure)).fetchone()
            if not inserted:
                continue
            previous = c.execute('SELECT status,evidence,checked FROM cc_alert_confirmed '
                                 'WHERE account=%s AND ein=%s AND state=%s', org_key).fetchone()
            if previous and previous['checked'] >= checked:
                continue
            if not status:
                if match:
                    record(c,org_key,match,run['id'],checked,None)
                continue
            identifier = (result or {}).get('matched_registry_identifier')
            prior_auto = None
            if self.master is not None and identifier and previous:
                prior_auto = c.execute('SELECT name,previous FROM cc_alert_auto_matches '
                    'WHERE account=%s AND ein=%s AND state=%s AND identifier=%s AND checked=%s AND NOT corrected',
                    (*org_key,identifier,previous['checked'])).fetchone()
            if not match and prior_auto:
                match = {'name':prior_auto['name'],'identifier':identifier}
            if match:
                prior = prior_auto['previous'] if prior_auto else previous
                record(c,org_key,match,run['id'],checked,prior)
            direction = classify_change(previous['status'] if previous else None, status)
            if direction:
                c.execute('INSERT INTO cc_alert_changes (account,ein,state,workflow,previous,status,evidence,direction,checked) '
                          'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                          (*org_key, run['id'], previous['status'], status, evidence, direction, checked))
            c.execute('INSERT INTO cc_alert_confirmed VALUES (%s,%s,%s,%s,%s,%s) '
                      'ON CONFLICT (account,ein,state) DO UPDATE SET status=excluded.status, '
                      'evidence=excluded.evidence, checked=excluded.checked', (*org_key, status, evidence, checked))
        c.execute('UPDATE cc_alert_orgs SET due=CASE WHEN (workflow=%s OR workflow IS NULL) AND due<=%s THEN %s ELSE due END,'
                  'workflow=CASE WHEN workflow=%s THEN NULL ELSE workflow END WHERE account=%s AND ein=%s',
                  (run['id'],run['submitted'],run['finished']+DAY,run['id'],org['account'],org['ein']))

    def expire_history(self):
        with self.transaction() as c:
            cutoff=self.now(c)-HISTORY_DAYS*DAY
            c.execute('DELETE FROM cc_alert_changes WHERE checked<%s',(cutoff,))
            c.execute('DELETE FROM cc_alert_checks WHERE checked<%s',(cutoff,))
            c.execute('DELETE FROM cc_alert_auto_matches AS m WHERE checked<%s AND NOT EXISTS '
                      '(SELECT 1 FROM cc_alert_confirmed s WHERE s.account=m.account AND s.ein=m.ein '
                      'AND s.state=m.state AND s.checked=m.checked)',(cutoff,))
            c.execute('DELETE FROM cc_alert_sessions WHERE expires<=%s',(self.now(c),))

    def prune_artifacts(self):
        # Only archives tagged when an Alerts-owned workflow wrote them qualify.
        # Keep paired history/snapshot assets while any retained alert or current
        # state references one of them. Never delete normal Aurora evidence.
        with self.transaction() as c:
            c.execute("SET LOCAL statement_timeout = '2s'")
            c.execute("""
                WITH expired AS (
                    SELECT a.id FROM cc_alert_artifacts a
                    JOIN cc_lab_workflows w ON w.id=a.workflow
                    WHERE a.created<%s AND w.finished IS NOT NULL
                      AND NOT EXISTS (SELECT 1 FROM cc_alert_orgs o WHERE o.workflow=a.workflow)
                      AND NOT EXISTS (
                        SELECT 1 FROM cc_alert_artifacts g
                        WHERE g.workflow=a.workflow AND g.state=a.state
                          AND (EXISTS (SELECT 1 FROM cc_alert_confirmed r WHERE r.evidence IN
                                  ('/state-snapshots/'||g.id||'.pdf','/state-evidence/'||g.id||'/search-history.pdf'))
                            OR EXISTS (SELECT 1 FROM cc_alert_auto_matches m JOIN cc_alert_confirmed s
                                        ON s.account=m.account AND s.ein=m.ein AND s.state=m.state AND s.checked=m.checked
                                        WHERE NOT m.corrected AND m.previous->>'evidence' IN
                                  ('/state-snapshots/'||g.id||'.pdf','/state-evidence/'||g.id||'/search-history.pdf'))
                            OR EXISTS (SELECT 1 FROM cc_alert_changes h WHERE h.evidence IN
                                  ('/state-snapshots/'||g.id||'.pdf','/state-evidence/'||g.id||'/search-history.pdf')))
                      )
                    ORDER BY a.created,a.id LIMIT 128
                ) DELETE FROM cc_state_snapshots s USING expired WHERE s.id=expired.id
            """,(self.now(c)-3600,))

    def tick(self):
        # A second API instance may be running during deployment. This lock is separate
        # from the queue's admission lock and protects one monitoring workflow at a time.
        with self.transaction() as c:
            if not c.execute('SELECT pg_try_advisory_xact_lock(824527332) AS ok').fetchone()['ok']:
                return
            active = c.execute('SELECT * FROM cc_alert_orgs WHERE workflow IS NOT NULL ORDER BY due LIMIT 1').fetchone()
            if active:
                status = self.queue.status('alerts:'+active['account'], active['workflow'])
                if status['phase'] in TERMINAL:
                    if self.master is not None:
                        from deployment.alerts_browser import merge
                        status = merge(self,c,status)
                        if status is None:
                            return
                    self.apply(c, active, status)
                    c.execute('UPDATE cc_lab_jobs SET result=NULL WHERE workflow_id=%s', (status['id'],))
                return
            if self.master is not None:
                return  # The opted-in Chrome profile claims new checks.
            now = self.now(c)
            org = c.execute('SELECT o.* FROM cc_alert_orgs o JOIN cc_alert_accounts a USING(account) '
                            'WHERE a.monitoring AND o.due<=%s ORDER BY o.due,o.account,o.ein LIMIT 1',(now,)).fetchone()
            if not org:
                return
            if c.execute("SELECT 1 FROM cc_lab_workflows WHERE finished IS NULL LIMIT 1").fetchone():
                return
            from deployment.durable_queue import normalize_submission
            payload = normalize_submission(dict(organization_name=org['name'], ein=org['ein'],
                alternate_names=org['aliases'], states=sorted(self.states), state_concurrency=10), self.states)
            key = f"daily:{org['ein']}:{int(org['due']*1000)}"
            ident, _ = self.queue.submit('alerts:'+org['account'], key, payload, self.version)
            c.execute('UPDATE cc_alert_orgs SET workflow=%s WHERE account=%s AND ein=%s',
                      (ident,org['account'],org['ein']))

    def account(self, c, handler):
        try:
            cookie = SimpleCookie(handler.headers.get('Cookie', ''))
            token = cookie[COOKIE].value
        except (CookieError, KeyError, ValueError):
            return None
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}',token):
            return None
        row = c.execute('SELECT account FROM cc_alert_sessions WHERE secret=%s AND NOT claim AND expires>%s',
                        (digest(token),self.now(c))).fetchone()
        return row['account'] if row else None

    def badge(self, c, account):
        return c.execute('SELECT count(*) AS n FROM cc_alert_changes a WHERE account=%s AND seen IS NULL AND checked>=%s '
                         'AND NOT EXISTS (SELECT 1 FROM cc_alert_auto_matches m WHERE m.account=a.account '
                         'AND m.ein=a.ein AND m.state=a.state AND m.workflow=a.workflow AND m.corrected)',
                         (account,self.now(c)-HISTORY_DAYS*DAY)).fetchone()['n']

    def dashboard(self, c, account, before):
        orgs = c.execute('SELECT o.ein,o.name,o.enrolled,o.due,o.workflow IS NOT NULL AS checking, '
                         '(SELECT count(*) FROM cc_alert_confirmed s WHERE s.account=o.account AND s.ein=o.ein) AS confirmed, '
                         'greatest((SELECT max(h.checked) FROM cc_alert_checks h WHERE h.account=o.account AND h.ein=o.ein), '
                         '(SELECT max(s.checked) FROM cc_alert_confirmed s WHERE s.account=o.account AND s.ein=o.ein)) AS last_checked '
                         'FROM cc_alert_orgs o WHERE o.account=%s ORDER BY o.name,o.ein', (account,)).fetchall()
        changes = c.execute('SELECT a.id,o.name,a.ein,a.state,a.previous,a.status,a.direction,a.checked,a.seen, '
                            "a.evidence<>'' AS has_evidence, coalesce(m.corrected,false) AS corrected, "
                            'm.identifier IS NOT NULL AS automatic, m.name AS match_name, m.identifier AS match_identifier '
                            'FROM cc_alert_changes a JOIN cc_alert_orgs o USING(account,ein) '
                            'LEFT JOIN cc_alert_auto_matches m ON m.account=a.account AND m.ein=a.ein AND m.state=a.state AND m.workflow=a.workflow '
                            'WHERE a.account=%s AND a.id<%s AND a.checked>=%s ORDER BY a.id DESC LIMIT 101',
                            (account,before,self.now(c)-HISTORY_DAYS*DAY)).fetchall()
        failures = c.execute('SELECT o.name,h.ein,h.state,h.checked,h.failure FROM cc_alert_checks h '
                             'JOIN cc_alert_orgs o USING(account,ein) WHERE h.account=%s AND h.failure IS NOT NULL '
                             'AND h.checked>=%s AND NOT EXISTS (SELECT 1 FROM cc_alert_checks n WHERE n.account=h.account '
                             'AND n.ein=h.ein AND n.state=h.state AND n.checked>h.checked) '
                             'AND NOT EXISTS (SELECT 1 FROM cc_alert_confirmed s WHERE s.account=h.account '
                             'AND s.ein=h.ein AND s.state=h.state AND s.checked>=h.checked) '
                             'ORDER BY h.checked DESC LIMIT 200',(account,self.now(c)-HISTORY_DAYS*DAY)).fetchall()
        matches=c.execute("SELECT m.ein,m.state,m.identifier,m.workflow,m.name,m.checked,coalesce(s.status,h.status) AS status, "
                          "coalesce(s.evidence,h.evidence,'')<>'' AS has_evidence "
                          'FROM cc_alert_auto_matches m LEFT JOIN cc_alert_checks h USING(account,ein,state,workflow) '
                          'LEFT JOIN cc_alert_confirmed s ON s.account=m.account AND s.ein=m.ein '
                          'AND s.state=m.state AND s.checked=m.checked '
                          'WHERE m.account=%s AND NOT m.corrected AND (s.checked IS NOT NULL OR h.checked IS NOT NULL) '
                          'AND NOT EXISTS (SELECT 1 FROM cc_alert_auto_matches n WHERE n.account=m.account '
                          'AND n.ein=m.ein AND n.state=m.state AND n.checked>m.checked AND NOT n.corrected) '
                          'AND NOT EXISTS (SELECT 1 FROM cc_alert_confirmed s WHERE s.account=m.account '
                          'AND s.ein=m.ein AND s.state=m.state AND s.checked>m.checked) '
                          'ORDER BY m.ein,m.state',(account,)).fetchall()
        return {'organizations':orgs,'matches':matches,'changes':changes[:100], 'next':changes[99]['id'] if len(changes)>100 else None,
                'unseen':self.badge(c,account),'states':len(self.states),'failures':failures}

    def operator(self, c, payload):
        """Private staging provisioning and import of same-day Aurora workflow IDs."""
        account = str(payload.get('account','')).strip().lower()
        if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',account) or len(account)>254:
            raise ValueError('Valid account required.')
        action = payload.get('action')
        if action=='provision':
            enrolled = payload.get('enrolled')
            now = self.now(c)
            if (type(enrolled) not in (int,float) or not now-DAY<enrolled<=now
                    or datetime.fromtimestamp(enrolled,ET).date()!=datetime.fromtimestamp(now,ET).date()):
                raise ValueError('Provide today’s signup time.')
            c.execute('INSERT INTO cc_alert_accounts(account) VALUES (%s) ON CONFLICT DO NOTHING',(account,))
            for org in payload.get('organizations',[]):
                self.enroll(c,account,org['name'],org['ein'],enrolled,org.get('alternate_names',[]))
        elif action=='bind_browser':
            token=secrets.token_urlsafe(32)
            c.execute('INSERT INTO cc_alert_sessions VALUES (%s,%s,%s,true)',
                      (digest(token),account,self.now(c)+120))
            return {'claim':token}
        elif action=='import':
            run=self.queue.status('private-performance-lab',payload['workflow'])
            org=c.execute('SELECT * FROM cc_alert_orgs WHERE account=%s AND ein=%s',
                          (account,run['ein'])).fetchone()
            if not org or datetime.fromtimestamp(run['submitted'],ET).date()!=datetime.fromtimestamp(org['enrolled'],ET).date():
                raise ValueError('Import requires a live check from the signup day.')
            self.apply(c,org,run)
        elif action=='enable':
            c.execute('UPDATE cc_alert_accounts SET monitoring=true WHERE account=%s',(account,))
        elif action!='status':
            raise ValueError('Unknown operator action.')
        return self.dashboard(c,account,2**63-1)


def handle(alerts, handler, path, *, origin, operator=False, include_body=True):
    headers={'Cache-Control':'no-store'}
    def reply(code, payload, extra=None):
        return (code,payload,headers|(extra or {}))
    def dispatch():
        parsed=urlsplit(path)
        try:
            payload={}
            if handler.command=='POST':
                n=int(handler.headers.get('Content-Length','0'))
                if not 0<n<=32768:raise ValueError('Invalid request.')
                payload=json.loads(handler.rfile.read(n))
                if not isinstance(payload,dict):raise ValueError('Invalid request.')
            with alerts.transaction() as c:
                if parsed.path=='/api/alerts/operator' and handler.command=='POST' and operator:
                    return reply(200,alerts.operator(c,payload))
                if handler.command=='POST' and handler.headers.get('Origin')!=origin:
                    return reply(403,{'error':'Invalid request origin.'})
                if parsed.path=='/api/alerts/session' and handler.command=='POST':
                    token=payload.get('claim','')
                    if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',token):
                        return reply(403,{'error':'Account session unavailable.'})
                    now=alerts.now(c)
                    row=c.execute('DELETE FROM cc_alert_sessions WHERE secret=%s AND claim AND expires>%s RETURNING account',
                                  (digest(token),now)).fetchone()
                    if not row:return reply(403,{'error':'Account session unavailable.'})
                    session=secrets.token_urlsafe(32)
                    c.execute('DELETE FROM cc_alert_sessions WHERE expires<=%s',(now,))
                    c.execute('INSERT INTO cc_alert_sessions VALUES (%s,%s,%s,false)',(digest(session),row['account'],now+7*DAY))
                    return reply(200,{'ok':True},{'Set-Cookie':f'{COOKIE}={session}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={7*DAY}'})
                account=alerts.account(c,handler)
                if not account:return reply(401,{'error':'An authenticated account session is required.'})
                if handler.command=='POST' and alerts.master is not None:
                    from deployment.alerts_browser import claim, enable, lease
                    if parsed.path=='/api/alerts/runner/claim':
                        return reply(200,claim(alerts,c,account,payload.get('profile')))
                    if parsed.path=='/api/alerts/runner/enable':
                        return reply(200,enable(alerts,c,account))
                    if parsed.path=='/api/alerts/runner/finish':
                        row=lease(alerts,c,account,payload.get('lease'))
                        if row:
                            c.execute('UPDATE cc_alert_browser_runs SET finished=true WHERE workflow=%s',
                                      (row['workflow'],))
                        return reply(200,{'ok':True})
                if handler.command=='GET' and parsed.path=='/api/alerts/badge':
                    return reply(200,{'unseen':alerts.badge(c,account)})
                if handler.command=='GET' and parsed.path=='/api/alerts':
                    from urllib.parse import parse_qs
                    before=int(parse_qs(parsed.query).get('before',[2**63-1])[0])
                    if not 1<=before<2**63:raise ValueError('Invalid history cursor.')
                    return reply(200,alerts.dashboard(c,account,before))
                if handler.command=='POST' and parsed.path=='/api/alerts/organizations':
                    added=alerts.enroll(c,account,payload.get('name'),payload.get('ein'),alerts.now(c))
                    return reply(201 if added else 200,{'added':added})
                if handler.command=='POST' and parsed.path=='/api/alerts/change-match' and alerts.master is not None:
                    from deployment.alerts_matches import correct
                    return (reply(200,{'ok':True}) if correct(alerts,c,account,payload)
                            else reply(409,{'error':'The match changed. Refresh and review the latest result.'}))
                if handler.command=='POST' and parsed.path=='/api/alerts/seen':
                    ident=payload.get('id')
                    if type(ident) is not int or not 1<=ident<2**63:raise ValueError('Invalid alert.')
                    row=c.execute('UPDATE cc_alert_changes SET seen=coalesce(seen,%s) WHERE account=%s AND id=%s AND checked>=%s RETURNING id',
                                  (alerts.now(c),account,ident,alerts.now(c)-HISTORY_DAYS*DAY)).fetchone()
                    return reply(200,{'unseen':alerts.badge(c,account)}) if row else reply(404,{'error':'Alert not found.'})
                match=re.fullmatch(r'/api/alerts/match-evidence/(\d{9})/([A-Z]{2})',parsed.path)
                if handler.command in {'GET','HEAD'} and match:
                    row=c.execute('SELECT s.evidence FROM cc_alert_confirmed s JOIN cc_alert_auto_matches m '
                                  'ON m.account=s.account AND m.ein=s.ein AND m.state=s.state AND m.checked=s.checked '
                                  'WHERE s.account=%s AND s.ein=%s AND s.state=%s AND NOT m.corrected',
                                  (account,*match.groups())).fetchone()
                    if row and row['evidence']:
                        return row['evidence']
                match=re.fullmatch(r'/api/alerts/evidence/([0-9]{1,19})',parsed.path)
                if handler.command in {'GET','HEAD'} and match and int(match[1])<2**63:
                    row=c.execute('SELECT evidence FROM cc_alert_changes WHERE account=%s AND id=%s AND checked>=%s',
                                  (account,int(match[1]),alerts.now(c)-HISTORY_DAYS*DAY)).fetchone()
                    if row and row['evidence']:
                        return row['evidence']
                return reply(404,{'error':'Not found.'})
        except (ValueError,TypeError,KeyError):
            return reply(400,{'error':'Check the organization name and EIN or refresh the page.'})

    response=dispatch()
    if isinstance(response,tuple):
        return handler._send_json(*response)
    from deployment import search_history,state_snapshots
    prior=handler.path
    try:
        handler.path=response
        handler.cc_alerts_evidence_authorized=True
        if HISTORY.fullmatch(response):return search_history.serve(handler,include_body)
        if SNAPSHOT.fullmatch(response):return state_snapshots.serve(handler,include_body)
    finally:
        handler.path=prior
        handler.cc_alerts_evidence_authorized=False
    return handler._send_json(404,{'error':'Not found.'},headers)
