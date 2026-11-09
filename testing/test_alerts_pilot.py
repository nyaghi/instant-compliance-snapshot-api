"""State transitions and account isolation using the same Alerts SQL operations."""
from contextlib import contextmanager
import io
import json
import sqlite3
from types import SimpleNamespace
import unittest

from psycopg.types.json import Jsonb
from deployment.alerts import Alerts, DAY, SCHEMA, digest, handle

NOW = 1794230000
VERSION = 'fixture'
EIN = '012345678'
URL = '/state-snapshots/'+'a'*64+'.pdf'
HISTORY = '/state-evidence/'+'b'*64+'/search-history.pdf'
ORIGIN = 'https://staging.example'
ACCOUNT = 'owner@example.org'
OTHER = 'other@example.org'


class Connection:
    def __init__(self):
        self.db = sqlite3.connect(':memory:')
        def postgres_rows(cursor, values):
            row=dict(zip((field[0] for field in cursor.description), values))
            for key in ('aliases','previous','results'):
                if isinstance(row.get(key),str) and row[key].startswith(('{','[','null')):
                    row[key]=json.loads(row[key])
            return row
        self.db.row_factory = postgres_rows
        self.db.create_function('greatest',2,lambda a,b: max((v for v in (a,b) if v is not None),default=None))
        self.db.create_function('least',2,min)
        self.db.execute('CREATE TABLE cc_state_snapshots(id text PRIMARY KEY)')
        self.db.executescript(SCHEMA.replace('bigserial PRIMARY KEY','integer PRIMARY KEY'))
        self.db.execute('CREATE TABLE cc_lab_workflows (id text, finished double precision)')
        self.db.execute('CREATE TABLE cc_lab_jobs (workflow_id text, result text)')

    def execute(self, statement, params=()):
        if statement.startswith('SELECT pg_try_advisory_xact_lock'):
            return self.db.execute('SELECT 1 AS ok')
        return self.db.execute(statement.replace('%s','?').replace(' FOR UPDATE',''),
                               tuple(json.dumps(x.obj) if isinstance(x,Jsonb) else x for x in params))


class Service(Alerts):
    def __init__(self, queue):
        super().__init__(queue, ['CO'], VERSION)
        self.c = Connection()
        self.clock = NOW

    def now(self, _):
        return self.clock

    @contextmanager
    def transaction(self):
        with self.c.db:
            yield self.c


def run(label, at, status, **overrides):
    result = {'ein':EIN, 'state':'CO','status':status,'evidence_url':URL,'success':True,
              'app_version':VERSION,'checked_at_epoch':at+1} | overrides
    return {'id':label,'ein':EIN,'phase':'completed','kind':'registration',
            'source_version':VERSION,'submitted':at,'finished':at+2,
            'jobs':[{'state':'CO','phase':'done','finished':at+2,'result':result}]}


class FakeQueue:
    def __init__(self):
        self.submissions = []
        self.result = None

    def submit(self, scope, key, payload, version):
        self.submissions.append((scope,key,payload,version))
        return 'scheduled', True

    def status(self, scope, identifier):
        assert scope=='alerts:'+ACCOUNT and identifier=='scheduled'
        return self.result or {'phase':'active'}


class Handler:
    def __init__(self, token='', payload=None, origin=ORIGIN):
        body=json.dumps(payload).encode() if payload is not None else b''
        self.command='POST' if payload is not None else 'GET'
        self.headers={'Content-Length':str(len(body)),'Origin':origin,'Cookie':'__Host-cc_alerts='+token}
        self.rfile=io.BytesIO(body)

    def _send_json(self,code,payload,headers):
        return code,payload,headers


class AlertsTests(unittest.TestCase):
    def setUp(self):
        self.q=FakeQueue()
        self.a=Service(self.q)
        self.c=self.a.c
        self.addCleanup(self.c.db.close)
        for account in (ACCOUNT, OTHER):
            self.c.execute('INSERT INTO cc_alert_accounts VALUES (%s,true)',(account,))
        self.a.enroll(self.c,ACCOUNT,'Example Organization',EIN,NOW)
        self.org=self.c.execute('SELECT * FROM cc_alert_orgs WHERE account=%s',(ACCOUNT,)).fetchone()
        self.session='a'*43
        self.other='b'*43
        for account,token in [(ACCOUNT,self.session),(OTHER,self.other)]:
            self.c.execute('INSERT INTO cc_alert_sessions VALUES (%s,%s,%s,false)',(digest(token),account,NOW+20*DAY))
        self.c.db.commit()

    def check(self, label, day, status, **kw):
        self.a.clock=NOW+day*DAY+5
        with self.a.transaction():
            self.a.apply(self.c,self.org,run(label,NOW+day*DAY,status,**kw))
        return self.a.dashboard(self.c,ACCOUNT,2**63-1)

    def test_signup_first_confirmed_then_adverse_favorable_and_no_change(self):
        self.assertEqual(self.check('first',0,'Current')['unseen'],0)
        adverse=self.check('worse',1,'Delinquent')
        self.assertEqual([(x['previous'],x['status'],x['direction']) for x in adverse['changes']],
                         [('Current','Delinquent','adverse')])
        self.assertEqual(self.check('worse',1,'Delinquent')['unseen'],1)
        self.assertEqual(self.check('unchanged',2,'Delinquent')['unseen'],1)
        good=self.check('better',3,'Current')
        self.assertEqual(good['unseen'],2)
        self.assertEqual(good['changes'][0]['direction'],'favorable')
        self.assertEqual(self.check('unchanged-again',4,'Current')['unseen'],2)

    def test_failures_and_late_baseline(self):
        start=self.check('first',0,'Site Not Reachable',success=False,evidence_url='')
        self.assertEqual(start['organizations'][0]['confirmed'],0)
        self.assertEqual(start['unseen'],0)
        self.assertEqual(len(start['failures']),1)
        self.assertEqual(self.check('recovery',1,'Current')['unseen'],0)
        for i,kw in enumerate([{'confirmation_required':True},{'identity_anchor':'POSSIBLE_NAME'},
                               {'ein':'999999999'},{'source_truth_conflict':True},{'success':False}],2):
            self.assertEqual(self.check(str(i),i,'Delinquent',**kw)['unseen'],0)
        status=self.c.execute('SELECT status FROM cc_alert_confirmed').fetchone()['status']
        self.assertEqual(status,'Current')
        change=self.check('valid-negative',7,'Not Registered',evidence_url='',search_history_url=HISTORY)
        self.assertEqual(change['changes'][0]['previous'],'Current')

    def test_status_only_baseline_and_change_with_optional_evidence(self):
        initial=self.check('first',0,'Current',evidence_url='')
        self.assertEqual(initial['organizations'][0]['confirmed'],1)
        self.assertEqual(initial['unseen'],0)
        change=self.check('worse',1,'Delinquent',evidence_url='https://example.org/file')
        self.assertEqual(change['unseen'],1)
        alert,=change['changes']
        self.assertFalse(alert['has_evidence'])
        self.assertEqual((alert['previous'],alert['status']),('Current','Delinquent'))
        self.assertEqual(handle(self.a,Handler(self.session),f"/api/alerts/evidence/{alert['id']}",
                                origin=ORIGIN)[0],404)
        self.assertEqual(self.check('same',2,'Delinquent',evidence_url='')['unseen'],1)

    def test_badge_seen_idempotent_and_tenant_scope(self):
        self.check('first',0,'Current')
        model=self.check('worse',1,'Delinquent')
        ident=model['changes'][0]['id']
        self.assertEqual(handle(self.a,Handler(self.other),'/api/alerts',origin=ORIGIN)[1]['organizations'],[])
        self.assertEqual(handle(self.a,Handler(),'/api/alerts',origin=ORIGIN)[0],401)
        self.assertEqual(handle(self.a,Handler(self.other,{'id':ident}),'/api/alerts/seen',origin=ORIGIN)[0],404)
        self.assertEqual(handle(self.a,Handler(self.other),f'/api/alerts/evidence/{ident}',origin=ORIGIN)[0],404)
        self.assertEqual(handle(self.a,Handler(self.session,{'id':ident},'https://other.example'),
                                '/api/alerts/seen',origin=ORIGIN)[0],403)
        self.assertEqual(handle(self.a,Handler(self.session),'/api/alerts/badge',origin=ORIGIN)[1]['unseen'],1)
        for _ in range(2):
            self.assertEqual(handle(self.a,Handler(self.session,{'id':ident}),'/api/alerts/seen',origin=ORIGIN)[1]['unseen'],0)
        self.assertEqual(len(self.a.dashboard(self.c,ACCOUNT,2**63-1)['changes']),1)

    def test_retention_keeps_latest_confirmed_and_rejects_out_of_order(self):
        self.check('first',0,'Current')
        self.check('worse',1,'Delinquent')
        self.check('late',0,'Exempt')
        self.assertEqual(self.c.execute('SELECT status FROM cc_alert_confirmed').fetchone()['status'],'Delinquent')
        self.a.clock=NOW+12*DAY
        self.a.expire_history()
        model=self.a.dashboard(self.c,ACCOUNT,2**63-1)
        self.assertEqual((model['unseen'],model['changes'],model['organizations'][0]['confirmed']),(0,[],1))
        self.assertEqual(self.check('better',13,'Current')['changes'][0]['previous'],'Delinquent')

    def test_add_organization_uses_authenticated_tenant_and_ein_is_idempotent(self):
        body={'name':'Another example','ein':'01-2345679','account':OTHER}
        for expected in (201,200):
            code,_,_=handle(self.a,Handler(self.session,body),'/api/alerts/organizations',origin=ORIGIN)
            self.assertEqual(code,expected)
        self.assertEqual(self.a.dashboard(self.c,OTHER,2**63-1)['organizations'],[])
        model=self.a.dashboard(self.c,ACCOUNT,2**63-1)
        self.assertEqual(len(model['organizations']),2)
        self.assertEqual(model['unseen'],0)

    def test_scheduler_due_immediately_then_roughly_24_hours(self):
        self.a.tick()
        self.assertEqual(len(self.q.submissions),1)
        self.assertEqual(self.q.submissions[0][2]['states'],['CO'])
        self.a.tick()
        self.assertEqual(len(self.q.submissions),1)
        self.q.result=run('scheduled',NOW,'Current')
        self.a.tick()
        next_due=self.c.execute('SELECT due FROM cc_alert_orgs').fetchone()['due']
        self.assertEqual(next_due,NOW+DAY+2)
        self.a.clock=next_due-1
        self.a.tick()
        self.assertEqual(len(self.q.submissions),1)
        self.a.clock=next_due
        self.a.tick()
        self.assertEqual(len(self.q.submissions),2)
