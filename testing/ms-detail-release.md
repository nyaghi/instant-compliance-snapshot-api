# Mississippi detail recovery — staging 2026.09.09.7

An already matched Mississippi row could return before its detail-page expiration was readable, invoking the existing default date. The master backend now polls for usable Filing Status and expiration fields with two bounded read windows and a shared eight-second limit. A failed detail click may be retried once; a successful click is not repeated. Ready pages return immediately. Exempt/closed detail statuses do not wait for an unnecessary date. Click/read failures and exhausted field-read windows are retained as diagnostics.

Scope: Mississippi detail retrieval only. Name/EIN matching, existing classification and fallback rules, other states, batch/concurrency settings, infrastructure and environment variables remain unchanged. Frontend modification is the staging version label only. Production is not authorized.

Predeployment: 9 synthetic MS recovery controls and 249 existing regression checks passed (258 total, including 30 core-matching fixture rows). Ten live controls passed: MS Arbor Day, Accion, Firehouse, Canine Assistants, National Marrow Donor Program, Focus on the Family, FoodCorps; CO Firehouse and FoodCorps; MI Reading Is Fundamental. Both originally affected organizations exposed explicit expiration dates. Original baseline expectations retained. Evidence lives in the parent workspace outputs/ms-detail-recovery-20260909.

After deployment: verify both staging backends and frontend version/API targets, run hosted controls, then repeat first 25 organizations across 29 states excluding NY. Pause and investigate new status discrepancies; preserve first observations. The prior verified ND baseline drift and Proteus UTC date-boundary change are documented reference findings, not changed expectations.
