# Massachusetts and Michigan surgical follow-up

Candidate version: **2026.09.14.3-staging**.
Baseline commit: **66634867c42b75bda3f75fa8883b7f170f970510**.

## Behavior

- Massachusetts maps the matched charity's primary In-Progress / In Progress /
  Pending status to Pending before annual-filing inference. A pending filing
  document does not create a pending charity status.
- The exact Massachusetts activity description Not Doing Business in Mass no
  longer blocks inference from a confirmed empty annual history or Schedule A2
  only. Delinquent remains explicitly described as inferred. Submitted filing
  calculations and actual adverse status handling remain unchanged.
- Michigan has a 100-second attempt budget, including time already spent
  before entering its source lookup. EIN recovery remains capped at 55 seconds
  and reserves at least 45 seconds for name fallback. Search submissions allow
  up to 25 seconds, bounded by the remaining time. Two patient EIN submissions
  replace three shorter submissions.
- Michigan transport and name-budget failures qualify for the existing bounded
  second lookup. Its short delay is staggered by EIN. Attempt history preserves
  initial failures, including when later recovery succeeds.
- Michigan's direct batch path uses the same recovery routine without leaving
  timed-out worker threads running. Its HTTP fanout allowance is 230 seconds,
  enclosing both attempts and cleanup within the web request's 240 seconds.
- EIN-first lookup, name variants, candidate matching, status rules outside the
  two approved MA corrections, global concurrency and other state budgets are
  unchanged. NY connector, report generator, downloadable data, environment
  variables and production configuration are unchanged.

## Validation record

Evidence is retained in `outputs/ma-mi-followup-20260914` in the parent project.
Initial 90-second timing candidate passed ten-way but failed two of fifteen
simultaneous Michigan checks; deployment was held. Their original response
files remain retained. The final 100-second candidate must independently pass
controls, deterministic regression and ten/fifteen-way validation before release.

Massachusetts controls also exposed existing In-Progress primary statuses for
Reading Is Fundamental (52-0976257, AGO 031615) and National Arbor Day
Foundation (23-7169265, AGO 014011). Their Pending results follow the same
user-approved primary-status rule. Original Current sheet expectations and
the source evidence are preserved in the validation corrections. The sheet
itself is not edited.

Post-validation is a new uniform sample without replacement: 30 organizations
from the first 70, seed **9222021237988978409**, fixed before validation. Check
all 30 states (900 checks), including NY through the unchanged browser
connector. Investigate retrieval/identity errors before resuming. Preserve and
list approved date drift and other corrections; never hide initial failures.

Deployment and final post-validation outcomes are recorded in the external
release review after the corresponding gates pass. Production deployment is
not authorized.
