"""Same master engine, isolated task lifetime. No state-specific logic lives here."""
import os
from pathlib import Path
import sys
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def execute(master, job):
    if job['version'] != master.APP_VERSION:
        raise ValueError('Master version mismatch')
    p = job['payload']
    if job['state'] == '@discovery':
        return master.discover_organization_names(p['organization_name'], p['ein'])
    if job['state'] == 'NY':
        raise ValueError('Isolated NY collector not configured')
    if job['state'] not in master.SUPPORTED_STATES:
        raise ValueError('Unsupported state')
    organizations = master.normalize_organization_requests(p, privileged=False)
    if len(organizations) != 1: raise ValueError('Exactly one organization required')
    results = master.run_state_lookups_parallel(organizations, [job['state']])
    if len(results) != 1: raise ValueError('Unexpected result count')
    return results[0]


def main():
    from deployment.performance_lab import validate_environment, install_http_egress_guard
    validate_environment(os.environ)
    install_http_egress_guard()
    job = json.load(sys.stdin)
    if os.name != 'nt':
        import threading, time, signal
        parent = os.getppid()
        deadline = time.monotonic()+job['run_seconds']
        def guard():
            while time.monotonic() < deadline and os.getppid() == parent:
                time.sleep(.25)
            os.killpg(os.getpgrp(), signal.SIGKILL)
        threading.Thread(target=guard, daemon=True).start()
    import registry_snapshot_server as master
    # The child has a private result file. Logs never mix into the result payload.
    result = execute(master, job)
    output = Path(sys.argv[1])
    temp = output.with_suffix('.partial')
    temp.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    temp.replace(output)
    # Discovery can leave deadline-exceeded executor threads alive. The parent
    # kills/reaps the process tree before accepting this saved result.


if __name__ == '__main__': main()
