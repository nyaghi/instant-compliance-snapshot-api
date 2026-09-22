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
