# Oklahoma verified certificate fallback — 2026.09.06.7-staging

User authorized reuse within 24 hours. The master first searches the live registry and selects the latest qualifying filing for the matched organization. It still requests a fresh certificate. If transport fails, a previously identity-verified certificate expiration may be reused only for the identical detail URL, document number, and registry name, with a valid live document action. Public comments disclose the original retrieval time in UTC and the same document number. Reuse does not extend the lifetime. No filing anniversary inference or organization-specific overrides.

The bounded, locked cache holds at most 256 verified results in process memory. It starts empty on restart/deployment and is not shared between backend instances. Cold-cache upstream failures can still return Site Not Reachable. Invalid fresh PDFs invalidate cached evidence. Expired or future timestamps cannot be reused. This is a resilience improvement, not a guarantee of state availability.

Local validation: 19 Oklahoma tests, 16 manual-reconciliation tests, 14 NY tests, 30 mature matching fixtures, 10 downloadable-data tests, and 17 report tests. Live-source local smoke: Reading Is Fundamental OK Current (34.48s), synthetic no-record OK Not Registered (52.97s), Make-A-Wish CO Current (6.39s). No batch or matching changes. Approved baseline unchanged.

Staging deployment and first-attempt results are recorded under outputs/cogency-clients-20260906. The new cohort uses ten national nonprofit entities with official public registered-agent evidence naming Cogency Global. This establishes registered-agent relationships, not the scope of charitable-filing services. Production is not authorized and must remain untouched.
