# Sunday downloadable data release - staging only

Scope: KS, KY, LA, NH, OR. Run every Sunday at 6 a.m. America/New_York. The existing Codex desktop automation executes this procedure; the computer must be available. Delayed/missed execution is not successful refresh.

## Prepare

Use a fresh isolated worktree from the latest origin/staging. Do not use or commit the dirty saved checkout, overwrite unrelated work, push main, change production, or change environment variables. The saved project has other uncommitted work. Fetch origin staging and create a uniquely named maintenance branch/worktree. Use the project's pinned Python and requirements, and Playwright Chromium. Credentials already available must never be printed.

## Download and validate

Run `python refresh_downloadable_state_data.py --states KS,KY,LA,NH,OR`. Require exit 0, no errors, and all five manifest entries present and usable. This command downloads actual source files, validates/parses them, preserves old files on a state failure, and writes downloadable-state-data.json. It downloads KS's published Excel into its existing packaged module, KY PDF plus parsed rows, LA Excel export, NH PDF, and OR ZIP converted to the existing TSV schema. Source dates are distinct from download timestamps; an unchanged source still records a successful check.

Run these commands:

```text
python -m py_compile registry_snapshot_server.py KS_weekly_checker.py refresh_downloadable_state_data.py
python testing/run_downloadable_data_guardrails.py
python testing/run_manual_reconciliation_guardrails.py
python testing/run_core_matching_guardrails.py
git diff --check
```

Run `python testing/run_weekly_data_smoke.py --output testing/weekly-data-evidence/local.jsonl` and inspect every result for errors/inconclusive statuses and differences; the harness retains raw results and does not decide whether differences are acceptable. Compare the original five organizations in the five downloadable states against the approved regression export. Also smoke one expected no-record case and a mature EIN-first live state. Preserve original expectations and categorize changes. If a download, parser, integrity check, smoke test, or material unexplained regression fails, do not deploy that release; report the exact blocker and retained source dates. Do not treat file presence as a refresh or a changed local file as a deployment.

## Deploy without another permission request

The user authorizes automatic STAGING deployment of validated weekly data. Stage only KS_weekly_checker.py, registered-charities.pdf, Charity_OR.txt, downloadable-data/KY.pdf, downloadable-data/KY-records.json, downloadable-data/LA.xlsx, and downloadable-state-data.json. Do not sweep unrelated changes into a commit. Respect .gitattributes so asset checksums survive checkout. Commit and push HEAD:staging after confirming origin/staging has not advanced; reconcile safely if it has. Never force push. Code fixes outside routine data maintenance require their normal local regression checks.

Wait for both staging Render services to deploy that exact commit:
- public: srv-d8a38lnavr4c73d4ib30
- internal: srv-d82afqjrjlhs738j7or0

The live public API is https://instant-compliance-snapshot-api-staging-8dnk.onrender.com/ . The UI is https://staging.compliance-express.com/ . These are the only deployment targets authorized by this procedure. Do not deploy production. A data-only release does not require changing static frontend files or bumping the code version.

## Prove deployment

GET /health on the public staging backend. Compare all five downloadable_data entries and every asset checksum to the local manifest; require usable=true, current downloaded_at, matching record_count and source_date. Verify the staging frontend responds and targets the staging API, with no production API target. Run `python testing/run_weekly_data_smoke.py --staging --output testing/weekly-data-evidence/staging.jsonl` and inspect all results. This covers all five file states plus the live-state and no-record controls. Record commit, Render deploy IDs, source dates/download times/counts/checksums, smoke statuses, and failures. Report completion only after this proof. If deployment or runtime verification fails, report it explicitly; never describe local success as live success.

Keep the execution evidence in the automation memory and release artifacts. Notify on completed deployment, failure, missed/late refresh, or action required. Production promotion is never part of this job.
