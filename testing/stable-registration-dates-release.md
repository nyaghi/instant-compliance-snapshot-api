# Stable 20.6 workflow with registration dates

User scope: add Registration Date to staging 20.6 while reporting the separate Sales A/B experiments. The stable workflow is based on `06e5e53` (the deployed 20.6 backend/connector compatibility release plus authorized public-copy changes), not the Sales prototype. Release label: `2026.09.22.3-staging`.

## Change

- Master response adds state-supplied registration date, meaning, source label, URL and availability note after final classification.
- California retains registration records already fetched for the selected entity; candidate scoring and status selection are unchanged.
- Arkansas and North Dakota preserve the state label “Registration Date”; they are not relabeled as initial registration.
- California preserves “Initial Registration Date.” Filing, renewal, incorporation and expiration dates are never substituted.
- Detailed table, Excel and PDF carry the field; other currently unextracted dates are explicitly unavailable.
- Staging uses the approved contact-led page wording. The existing detailed status vocabulary, discovery and one-at-a-time non-NY state workflow are retained. New York keeps its existing independent lane.
- No extra registry requests, environment variables, capacity settings, matching rules or status rules are changed. No production deployment is part of this release.

## Controls

Run `testing/run_registration_date_guardrails.py`, `testing/run_date_release_parity.py` and the existing core matching, discovery, transport, fresh-16 identity, address, report, and NY connector suites. The parity guard checks that the only master changes are the metadata function, response insertion and version; it also checks that California only retains already-fetched data and that frontend state scheduling is unchanged.

Measured date extraction on 3,000 local calls takes about 0.007 ms median. This is computation overhead, not a claim about live registry speed. Live staging must verify both backends, the date column, source-bound dates, an unavailable-date case, a no-record control and report/export layout after deployment.

## Sales experiments are separate

Original A: 15 concurrent organizations x 16 EIN states; 212/240 reference matches, 28 flags; median 3:27. A repeat: 220/240 matches, 20 flags; median 2:55. Original A coincided with an out-of-memory restart; the repeat with a failed instance health check.

B: the same 15 organizations x 30 states after fresh name discovery; 434/450 reference matches, 15 verification flags and one conclusive Wisconsin record/status difference. Registration median 5:43; discovery median 0:42. Per-organization combined processing median 6:31 (manual review time excluded).

Both experiments use three non-NY state requests per organization. The accelerated modes are not approved for release. Preserve original results and any diagnostics separately. They do not establish reliable 15-organization performance at the higher state concurrency.

Full deployment, smoke evidence and A/B results are under the workspace output `outputs/sales-ab-browser-20260922/`.
