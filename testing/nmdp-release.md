# NMDP state evidence corrections — 2026.09.07.2 staging

User authorized the five fixes after the September 7 investigation. All runtime changes are in the master backend; no organization-specific status overrides, satellite services, timeout increases, production changes, or environment changes.

- AK: search the next solicitation cycle once it opens July 1; use confirmed registration-cycle evidence and September 1 of that cycle year, rather than the financial year plus one. PDF fallback reads the registration heading, not its accounting period. Newer-year retries require a confirmed row year.
- NM: centralize the six-month state deadline plus granted six-month extension, preserving month-end behavior in the state's examples. Map the newer granted tax year from the actual submitted fiscal period. Final normalization preserves the computed explicit deadline. Open/requested events remain insufficient evidence. Explanations include the granted extension and fiscal period.
- OK: use a structured document-delivery outcome in the runtime, recognizing explicit document-unavailable HTML even with HTTP 200. Generic HTML, rejected records, invalid certificates, mismatched identity and incomplete filing history cannot use the anniversary fallback. Existing two-value evidence consumers remain compatible. The 24-hour verified certificate cache is preserved.
- VA: Expired/Lapsed plus Not Authorized to Solicit becomes Delinquent, including final normalization, while the restriction remains in the comment. Explicit Suspended remains Suspended; unexplained restrictions cannot become Current.
- WI: inspect the primary name and credential number when an exact-name row conflicts with another name on the same credential. Unconfirmed conflicts remain inconclusive, not a clean negative. Separate entity extensions still require a safe target match. The extra identity check is limited to conflicting credentials.
- Web staging: version label updated from 2026.09.07.1 to 2026.09.07.2; staging API target preserved.

Validation before deployment: 144 offline guardrails passed across NMDP, NM history, OK certificate recovery, manual reconciliation, core matching, filing evidence and comments. Compilation and diff whitespace checks passed. Unit date assertions reflecting the former NM arithmetic were corrected; the approved regression spreadsheet/export was not changed.

Live local NMDP smoke: AK Current; NM Upcoming Filing; OK Upcoming Filing; VA Delinquent after correcting the final normalization override; WI Revoked. Make-A-Wish CO remained Current; a synthetic WI no-record search returned Not Registered. A standalone VA probe initially lacked the local Playwright browser-path setting; rerunning with the documented process-only path completed normally. No deployed environment setting changed.

The 25 affected-state checks for the original five organizations produced 24 matches to the saved baseline. Prevent Child Abuse America AK now uses confirmed registration cycle 2026 and September 1, 2026 expiration, yielding Delinquent instead of baseline Current. Categorization: prior code bug / expected sheet drift under the corrected cycle rule. Keep the baseline unchanged and flag for review. No other baseline status changes. This is targeted regression, not a new 750-state-check or capacity benchmark.

Evidence and final deployment/verification records: `outputs/nmdp-fixes-20260907` under the workspace root. The earlier investigation remains in `outputs/nmdp-investigation-20260907`.

Known limitations: Oklahoma's original failed live response was not captured; the demonstrable HTTP-200 fallback gap is fixed, but registry retrieval is not guaranteed under all failures. Proposed dates derived from approved rules remain labeled as inferred/calculated. Production promotion remains unapproved and is not recommended until the flagged baseline difference is reviewed.
