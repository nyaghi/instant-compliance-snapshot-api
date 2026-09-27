# September 27 feedback — staging only

- Accept match is disabled and gray on an accepted candidate; Reject match is disabled on a rejected candidate. The opposite decision and Undo match remain enabled. Pending requests lock all controls; errors restore the prior selection. Candidate decisions remain independent. The UI does not alter master status calculations.
- Preliminary discovery finishes after the existing 14 EIN-capable backend state sources and IRS return. The appended Illinois connector identity lookup is removed as requested. Illinois, Georgia and New York registration checks remain available and unchanged. No extension update is needed.
- Incorporates the validated September 27 KS/KY/LA/NH/OR dataset commit cefa0a9. D.C. continues querying the official public data service during checks; it is not a scheduled local weekly download.
- Scope: front-end behavior, source version, and refreshed data. No matching, status, timeout, concurrency, permissions, production, or environment-variable changes.

Validation: 730 backend tests across 39 suites plus 30 matching fixtures (one obsolete discovery parity assertion updated to permit exactly the requested removed block); 69 Node tests; 12 downloadable-data integrity checks; 16 reconciliation checks; 27 local weekly smoke checks. Live staging verification and retained-output post-validation are required before release completion.

Timing audit uses the product request functions and 15-slot scheduler verbatim, the same version and reviewed names, and reversed 32/34 scope order between YWCA and Consumer Credit of Des Moines. Florida must be excluded symmetrically while its public site returns a Runtime Error. Preliminary backend discovery and the former Illinois step are timed separately. These are controlled current-version comparisons, not historical-release performance claims.

The refreshed source sheet has only 25 new organizations after the previously validated group: rows 151–177, excluding previously checked MCE Social Capital and one blank row. Expectations remain unchanged. Do not imply a full 50 new organizations or 1,700 checks.
