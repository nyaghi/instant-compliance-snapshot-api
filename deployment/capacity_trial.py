"""Read-only planning/measurement helpers for the next private lab capacity trial.

This module neither provisions infrastructure nor changes the state engine.
The proposed scale action needs the user's separate recurring-cost approval.
"""
import statistics
import time

API_ID = 'srv-d8u0hsu7r5hc73aqfsg0'
WORKER_ID = 'srv-dar7adgu01pc738fsmgg'
VERSION = '2026.09.25.perf.11-performance-lab'
COMMIT = '36a8c466d814b9090fa811ba4f894484264a96c4'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fresh_workers(metrics, expected, now=None):
    now = time.time() if now is None else now
    workers = [w for w in metrics['workers']
               if not w['retired'] and 0 <= now-w['heartbeat'] < 20]
    require(len(workers) == expected, 'Unexpected live worker count')
    require(len({w['id'] for w in workers}) == expected, 'Duplicate worker identity')
    require(all(w['slots'] == 12 for w in workers), 'Unexpected physical slot ceiling')
    require(sum(w['id'].startswith(API_ID+'-') for w in workers) == 1,
            'Expected exactly one API worker')
    require(sum(w['id'].startswith(WORKER_ID+'-') for w in workers) == expected-1,
            'Unexpected background worker service')
    return workers


def scale_plan(services, deployments, metrics, target_instances=2, now=None):
    """Only propose 1<->2 replicas of the existing background service, idle."""
    require(target_instances in (1, 2), 'Only the bounded third-worker trial is supported')
    current = 3-target_instances
    require(set(services) == {API_ID, WORKER_ID}, 'Unexpected service set')
    for sid, service in services.items():
        details = service['serviceDetails']
        require(service['id'] == sid, 'Service identity mismatch')
        require(service['branch'] == 'performance-lab-20260924', 'Wrong branch')
        require(service['autoDeployTrigger'] == 'off', 'Automatic deploy must stay off')
        require(service['suspended'] == 'not_suspended', 'Service suspended')
        require(details['plan'] == 'pro', 'Unexpected compute plan')
        require(details['region'] == 'oregon', 'Unexpected region')
        require(not details.get('disk'), 'Persistent disk prevents replica scaling')
        require(not details.get('autoscaling'), 'Manual trial requires no autoscaling config')
        require(details['numInstances'] == (1 if sid == API_ID else current),
                'Instance count already changed; inspect before retry')
        deploy = deployments[sid]
        require(deploy['status'] == 'live' and deploy['commit']['id'] == COMMIT,
                'Both services must run the unchanged tested code')
    require(services[API_ID]['type'] == 'web_service', 'Wrong API service type')
    require(services[WORKER_ID]['type'] == 'background_worker', 'Wrong worker type')
    require(services[WORKER_ID]['name'] == 'charityclarity-performance-lab-worker-1',
            'Wrong background service name')
    settings = metrics['settings']
    require(settings['source_version'] == VERSION, 'Wrong queue source version')
    require(settings['workflow_limit'] == 15, 'Global organization ceiling changed')
    require(settings['registry_limits'].get('NY') == 2, 'NY registry ceiling changed')
    require(not any(j['count'] and j['phase'] != 'done' for j in metrics['jobs']),
            'Queue must drain before scaling')
    require(not any(w['count'] and w['phase'] not in ('completed', 'expired', 'canceled')
                    for w in metrics['workflows']), 'Workflow still unfinished')
    fresh_workers(metrics, current+1, now)
    return {'service_id': WORKER_ID, 'method': 'POST',
            'path': '/services/'+WORKER_ID+'/scale',
            'body': {'numInstances': target_instances},
            'version': VERSION, 'code_commit': COMMIT,
            'expected_workers': target_instances+1,
            'total_cpu': 2*(target_instances+1), 'total_memory_gb': 4*(target_instances+1),
            'monthly_compute_usd': 85*(target_instances+1),
            'monthly_compute_delta_usd': 85*(target_instances-current),
            'billing': 'Prorated by the second; workspace and other charges unchanged'}


def summarize_series(data):
    """Keep replica measurements distinct; sum only aligned, complete samples."""
    instances = {}
    for series in data:
        labels = {r['field']: r['value'] for r in series.get('labels', [])}
        instance = labels.get('instance')
        require(bool(instance), 'Instance label required to compare replica capacity')
        require(instance not in instances, 'Duplicate metric series for instance')
        values = {r['timestamp']: r['value'] for r in series.get('values', [])}
        require(len(values) == len(series.get('values', [])), 'Duplicate metric timestamps')
        instances[instance] = values
    per_instance = {k: {'peak': max(v.values()), 'sampled_mean': statistics.mean(v.values()),
                        'samples': len(v)} if v else None for k, v in instances.items()}
    aligned = set.intersection(*(set(v) for v in instances.values())) if instances else set()
    sums = [sum(v[t] for v in instances.values()) for t in aligned]
    return {'per_instance': per_instance, 'aligned_total':
            {'peak': max(sums), 'sampled_mean': statistics.mean(sums), 'samples': len(sums)}
            if sums else None,
            'unaligned_samples': sum(len(v)-len(aligned) for v in instances.values())}
