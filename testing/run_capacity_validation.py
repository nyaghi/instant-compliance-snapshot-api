"""Staging-only load observation. One serial state request per simulated web user.

Test tooling only: no runtime routing, no automatic retries, no scaling mutations.
Preserves first responses, HTTP errors, timing and concurrency for independent review.
"""
import argparse
import concurrent.futures
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc

p=argparse.ArgumentParser()
p.add_argument('--organizations',required=True)
p.add_argument('--output',required=True)
p.add_argument('--users',type=int,required=True)
p.add_argument('--states',default='')
p.add_argument('--label',required=True)
p.add_argument('--all-organizations',action='store_true',help='Queue the full organization list behind the user limit')
p.add_argument('--resume-from',help='Preserve earlier attempts and only run not-yet-attempted organization/state pairs')
args=p.parse_args()
assert 1 <= args.users <= 25
orgs=json.loads(Path(args.organizations).read_text(encoding='utf-8'))
if not args.all_organizations: orgs=orgs[:args.users]
prior=set()
if args.resume_from:
    prior={(r['ein'],r['state']) for r in (json.loads(l) for l in Path(args.resume_from).read_text(encoding='utf-8').splitlines())}
states=args.states.split(',') if args.states else cc.SUPPORTED_STATES
assert set(states)<=set(cc.SUPPORTED_STATES)
api='https://instant-compliance-snapshot-api-staging-8dnk.onrender.com/api/check'
out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
assert not out.exists(), 'Never overwrite a first-attempt run'
lock=threading.Lock(); active=0; peak=0
stop=threading.Event(); results=[]; users=[]; overall=time.time()

def run(index,org,handle):
    global active,peak
    user_start=time.time()
    for state in states:
        if (org['ein'],state) in prior: continue
        if stop.is_set(): break
        start=time.time()
        with lock:
            active+=1;peak=max(peak,active);at_start=active
        payload={'organization_name':org['organization'],'ein':org['ein'],'email':'staging-smoke@'+cc.EXEMPT_EMAIL_DOMAIN,'states':[state],'consent':True,'admin_passcode':cc.ADMIN_PASSCODE,'device_id':f'capacity-{args.label}-{index}','environment':'staging','origin':'https://staging.compliance-express.com','page_url':'https://staging.compliance-express.com/','client_user_agent':'CharityClarity staging capacity validation'}
        row={**org,'state':state,'user':index,'wave':args.label,'configured_users':args.users,'started_epoch':start,'active_requests_at_start':at_start}
        try:
            req=urllib.request.Request(api,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=240) as response:
                data=json.load(response);row['http_status']=response.status
            row['result']=(data.get('results') or [data])[0]
            row['request_id']=data.get('request_id','')
        except urllib.error.HTTPError as exc:
            row.update(http_status=exc.code,error=exc.read().decode('utf-8',errors='replace')[:1000])
        except Exception as exc:
            row.update(http_status=0,error=str(exc)[:1000])
        row['finished_epoch']=time.time();row['seconds']=round(row['finished_epoch']-start,3)
        with lock:
            active-=1;results.append(row);handle.write(json.dumps(row)+'\n');handle.flush()
            # Bound load if the application is visibly refusing/failing requests.
            recent=results[-30:]
            if len(recent)==30 and sum(bool(r.get('error')) for r in recent)>=6:stop.set()
            print(args.label,len(results),org['organization'],state,row.get('result',{}).get('status','HTTP ERROR'),row['seconds'],flush=True)
    with lock:users.append({'user':index,'organization':org['organization'],'started_epoch':user_start,'finished_epoch':time.time(),'seconds':round(time.time()-user_start,3)})

with out.open('w',encoding='utf-8') as handle,concurrent.futures.ThreadPoolExecutor(max_workers=args.users) as pool:
    futures=[pool.submit(run,i,org,handle) for i,org in enumerate(orgs)]
    for f in futures:f.result()
summary={'label':args.label,'configured_users':args.users,'states':states,'planned_checks':sum((o['ein'],s) not in prior for o in orgs for s in states),'completed_checks':len(results),'peak_active_requests':peak,'started_epoch':overall,'finished_epoch':time.time(),'seconds':round(time.time()-overall,3),'stopped_for_errors':stop.is_set(),'users':users,'http_errors':sum(bool(r.get('error')) for r in results)}
out.with_suffix('.summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k!='users'}),flush=True)
