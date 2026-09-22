# Production parity, sales mode, and registration dates

User authorization: September 22, 2026 attached implementation priorities. Production promotion and production-appropriate effective configuration changes are explicitly authorized. Work follows the stated priority order.

## Reference and scope

- Reference staging release: 2026.09.20.6-staging, commit fc9f5e3b00c16926717548f9cc5b4bd90e1a3db7; verify deployed versions and source assets before promotion.
- Preserve current detailed workflow and state identity/status safeguards.
- Remove the $49 trial from the CharityClarity experience; replace with info@compliance-express.com contact.
- Do not implement the separately deferred customer workspace/billing project.
- No organization-specific hardcoded outcomes.

## Ordered work and completion gates

1. Audit live staging and production code, web assets, worker resources, effective environment, source data, New York dependencies, timeouts, retry settings, authentication and report behavior. Save rollback identifiers and private configuration backups.
2. Resolve production readiness gaps, validate controls, benchmark the same representative organizations (including YWCA USA and Partnership for Civil Justice Fund) and 15 concurrent workflows, then promote the verified baseline and verify live production. Attribute residual differences to infrastructure, code, or state response variation.
3. Profile the detailed workflow; compare simplified all-state, direct-EIN scope, and combined sales modes on repeated representative cases. Implement the fastest defensible selectable offering with progressive results and explicit checked/unchecked scope, while retaining evidence internally.
4. Audit registration-date evidence by state; expose only semantically supported registration dates with labels/source evidence. Update relevant result, export and report surfaces, and measure overhead.
5. Complete focused controls, smoke tests, regression against the approved current spreadsheet, live staging/production verification as appropriate, and an evidence-backed completion report. Never describe an unmeasured performance target as achieved.

## Current progress

- Attachment and root AGENTS.md/release checklist read.
- Isolated branch created from the staging reference.
- Initial read-only hosting inventory saved under outputs/production-sales-dates-20260922.
- Initial inventory: staging uses two Standard Render services with 6 instances each. Production has an active 4-instance Standard service and a suspended 12-instance Standard public service. Effective frontend routing and environments must be audited before deciding what to enable.
- NY connector 0.3.6 is presently scoped to the staging domain. Production readiness requires explicit handling and validation; copying frontend files alone cannot establish parity.
- No production configuration or deployments changed yet.

## September 22 measured validation and implementation

- Compatibility release 2026.09.22.1-staging is live on both Render services and the staging Netlify site (b13ee52). Existing CE authentication is retained. Production builds include the same protected discovery/report endpoints and exact-origin NY continuations; the trial CTA is replaced with contact information.
- Reference benchmark: 15 simultaneous organizations, 435 non-NY state checks, 535.856 seconds wall time. Name discovery median 54.461 seconds, maximum 60.486 seconds. Separate NY controls all completed; these were sequential connector controls, not a measured 15-tab NY concurrency test.
- The baseline retains two known Wisconsin identity reviews (American Farriers and Dressage); neither was turned into a definitive negative. All other non-NY results matched the refreshed spreadsheet.
- Live compatibility smoke: both demo organizations (YWCA and Partnership for Civil Justice Fund), discovery, eight state checks, two PDFs and two NY checks succeeded. Unauthorized discovery/report requests were denied. The initial NY authorization probe omitted Origin and correctly received 404; a corrected approved-origin/unauthorized probe received 403. This was a test-input correction, not a registry failure.
- New sales UI preserves Operations mode and adds Sales all-state and Sales quick EIN modes. Sales uses three bounded non-NY requests, while Operations retains sequential non-NY ordering. Both progressively display completed states. Quick EIN scope covers 16 current implementations and retains required in-state identity/fallback checks; it skips broad pre-discovery. Canonical backend statuses and supporting evidence remain unchanged.
- Early experiments (five representative organizations, two repetitions each): 14 non-NY EIN states at three lanes completed in 82.828–104 seconds, all 140 results matching. All 29 non-NY states with reviewed names at three lanes took 118.688–163.985 seconds, all 290 results matching. These times exclude pre-discovery and NY. Adding VA to the 15-state non-NY sequential EIN comparison gave 176.406–235.640 seconds. Full-scope, 15-session and NY confirmation remain required before claiming final performance.
- Registration Date metadata reuses selected AR row, CA registration and ND detail evidence. Other dates are never substituted. The field includes exact source meaning in UI, Excel and PDF. See registration-date-audit.md. Timing diagnostics separate registry/wait, final identity checks, status, explanation and date extraction; no state timeout was reduced.
- Local date safeguards, sales queue/status controls and UI fixture walkthrough pass. Report preview was rendered and inspected on all three pages. Existing report-intelligence control required only its expected template version to follow the intentional 1.3.0 bump; all retained evidence checks continue unchanged.
- Production resources/environment mapping is prepared locally: two six-instance Standard services, production-only URLs and signing/lookup secrets, old conflicting state overrides removed, existing lead-log configuration preserved. No production mutation has been made. The old main branch is not an ancestor of the staging release; no force-push will be used. The proposed deployment pins the reviewed release branch with automatic deployment off.
- Connector 0.4.0 files installed in the existing Downloads test folder with rollback copy saved. Activation and live 0.4.0 testing await Chrome Reload. Customer distribution remains Chrome Web Store; dashboard access/account and Store review are not yet resolved. No claim of customer installation readiness or production parity has been made.
