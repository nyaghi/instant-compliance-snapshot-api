# Mississippi search-results readiness

Candidate: `2026.09.10.5-staging`.

The Mississippi portal can still display Please Wait when the old four-second result poll ends. An instrumented FoodCorps lookup returned Unable to Verify, then received the exact record approximately one second later. The failure occurs before the existing matched-detail recovery.

The master now waits directly for the existing result-table criteria or an explicit completed no-results response, for up to eight seconds. It returns as soon as ready. A visible Please Wait message keeps the response incomplete. Failed or unfinished searches remain inconclusive, with a diagnostic readiness note.

Only `ms_wait_for_search_results` (new) and `search_ms_fast` change. The existing 32-second rule for starting further Mississippi name queries is unchanged; an already-started query receives its bounded results wait. This budget is not a hard whole-lookup timeout. The first local iteration attempted to clamp an in-progress query by the remaining budget; that tightening was removed after the no-record control exposed a compatibility risk. Its evidence is retained.

Name variants, matching and active-record preference, detail recovery, classification, state routing, shared retry behavior, and all other state functions are unchanged. The staging frontend changes only its version label. No runtime sidecars, data, environment variables, or production changes.

Validation commands, run from the worktree or workspace as appropriate:

```text
../ma-selection-fix/.venv312/Scripts/python.exe -X utf8 -m py_compile registry_snapshot_server.py
../ma-selection-fix/.venv312/Scripts/python.exe -X utf8 testing/run_ms_search_readiness_guardrails.py
.codex-build/ma-selection-fix/.venv312/Scripts/python.exe -X utf8 tmp/ms_readiness_gate.py
.codex-build/ma-selection-fix/.venv312/Scripts/python.exe -X utf8 tmp/ms_release_checks.py local --label local-final
.codex-build/ma-selection-fix/.venv312/Scripts/python.exe -X utf8 tmp/ms_scope_audit.py
```

The eleven new tests cover delayed results beyond the prior cutoff, immediate results, explicit empty searches, stale results behind a loading overlay, missing documents, failed responses, table-selection compatibility, the eight-second readiness limit, conservative failure classification, and preservation of the existing query budget.

The release gate includes all 22 established suites plus the new readiness suite. Live local controls cover all 30 Mississippi organizations and ten other-state comparisons. After deployment, nine API smokes, a four-state batch, and a real FoodCorps browser submission precede refreshing the nine already-attempted Mississippi cases and continuing the 617 unstarted checks. The original failure and all prior responses remain preserved.

Detailed outcomes and deployment evidence are maintained in workspace `outputs/ms-readiness-fix-20260910/` and `FIX_TRACKER.md`. Production promotion requires explicit user approval after regression review.
