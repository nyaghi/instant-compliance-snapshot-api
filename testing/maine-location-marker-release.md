# Maine location-marker correction — 2026.09.16.2-staging

The first organization in the frozen random 30-of-101 post-validation sample, Christian Research Institute (22-6063412), failed Maine because the new address comparison treated `*MULTIPLES IN CHARLOTTE, NC` as a city different from `Charlotte, NC`.

The master address helper now accepts the originating registry state and strips only Maine's anchored `*MULTIPLES IN` display marker before city/state comparison. It preserves the original location in evidence. Maine supplies its state context; other states retain their existing behavior. Exact EIN and different-EIN decisions, real location conflicts, missing locations, agent addresses, matching/ranking, and status normalization are unchanged.

The direct live-source reproduction now selects CO2293 and reads `Canceled; expiration date 04/04/2025`, producing Closed / Withdrawn / Canceled. Three focused tests cover the marker, preservation of genuine location/EIN conflicts, and state-specific scope; the existing reviewed-case guardrail suite now has thirty tests.

The release QA group has eighteen cases: ten Maine cases (including the reported organization and the corrected NAACP CO5572 identity), six Wisconsin controls, one mature EIN-first Florida control, and a California no-record control. Logs, source hashes, controls, and deployment evidence are under `outputs/random30-post-20260916/maine-marker-fix`. The complete existing regression suite is required by the release gate.

The internal NY validation driver additionally stops on an expected-status mismatch, in support of the user's post-validation stop/investigate workflow. It does not alter the connector, public lookup, identity, or status behavior. Connector remains 0.3.1.

Resume the same saved random sample and retain the original failed evidence. Do not redraw the sample or silently edit spreadsheet expectations. Production promotion is not authorized.
