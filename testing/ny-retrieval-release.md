# New York retrieval correction — 2026.09.06.2-staging

Scope: master backend NY retrieval only, plus NY evidence-note deduplication. No shared matching, calendar rules, global browser waits, state datasets, environment variables, or production targets changed.

Root cause: the registry React search clears its rows before awaiting RegistrySearch. The old browser checker capped its network-idle wait at 1.5 seconds and its requested three-second pause at 1.5 seconds, then treated the loading table as completed search evidence. With controlled four-second network latency, four No rows available reads preceded successful search responses; that controlled run eventually recovered after 52.32 seconds. Separately, unchanged live staging reproduced two unconfirmed NY detail-link failures in 20 requests.

Correction: EIN-first official RegistrySearch JSON followed by identity-confirmed RegistryDetail JSON, inside the master backend. Complete schema and filing collection checks; fiscalYearEnd exclusively, never received date. Shared name variants are bounded fallback after a completed EIN search. Unique accepted identity required. HTTP errors, timeouts, malformed responses, and ambiguous identities remain inconclusive. No application-level NY retries or browser fallback. Explicit registry exemption and the existing latest-FYE/next-cycle interpretation retained.

Local validation: 14 NY contract/timing tests including a real HTTP response delayed four seconds; 16 reconciliation tests; 30 mature matching fixtures; nine downloadable-data guardrails; compile. Five live NY organization checks agreed with previously confirmed records. A unique synthetic NY no-record name returned Not Registered. Colorado Make-A-Wish returned Current as mature EIN-first control. Batch logic unchanged.

Staging deployment and postdeployment repeatability evidence will be recorded in the final report under outputs/ny-root-cause-20260906. Approved regression baseline expectations remain unchanged. Full 150-state matrix is not repeated for this NY-only retrieval correction; five NY organizations plus MI/OK/CO repeated controls cover the changed path and nearby retrieval regressions.

Production promotion remains subject to review and explicit user approval. No production changes authorized.
