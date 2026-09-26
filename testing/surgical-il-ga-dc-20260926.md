# IL / GA / DC targeted correction — September 26, 2026

User requested resolution of First Responders/GA, Air Force Academy/GA and IL,
American Independent Media/IL, American Veterans/IL, plus investigation of
Zearn/DC's recovered timeout. Staging only; source expectations stay unchanged.

Root causes and corrections:

- GA: 35-command protocol bound was smaller than the valid reviewed-name plan.
  Capacity now follows all planned name queries plus 100 candidate details;
  the existing five-minute expiry remains enforced.
- GA: unnumbered legacy exemption rows were visible but unsupported by detail
  transport. Refresh the public detail link by bound name and location, verify
  explicit exemption and selected name in the master, and retain ordinary
  cross-state identity checks. Missing license number alone is not delinquency.
- IL: the Veterans fallback has 154 records, exceeding the old 100-row/10-page
  bound. Collect up to 1,000 rows/100 pages, verifying complete pagination.
- IL: distinguish unavailable search controls from an unanswered search. Observe
  result rendering and attribute-only loading cycles; retry those failures once
  on a fresh public form. An initial empty grid is never negative evidence.
- DC: initial Zearn failure used two 15-second reads. Allow 15/20/25-second
  attempts with short pauses within the existing 75-second deadline, recording
  which read failed or recovered. RI retains its original two-read behavior.
- User reaffirmed blank filing-date policy: confirmed loaded IL Good Standing
  and GA active Charity records with absent filing deadlines become Delinquent,
  with comments identifying this as CharityClarity's policy. Explicit Exempt
  remains Exempt. Unopened/blank unidentified panels and invalid dates remain
  inconclusive. This is not a change to the other 32 state adapters.

Candidate: 2026.09.26.2-staging / connector 0.5.5. Validation/deployment evidence
is saved in the workspace output directory surgical-il-ga-dc-20260926. Live
verification must complete before reporting success. Production not authorized.
