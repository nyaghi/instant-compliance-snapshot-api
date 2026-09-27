# Final 50 validation release — 2026.09.26.8-staging

Authorized scope: PA, KY, DC and GA investigation fixes, control regression, then Fresh Test Orgs!A102:AM151 (50 organizations × 34 states). Expected spreadsheet values remain read-only. Production is not authorized.

- PA name fallback now reads the same completed public API response used by the official page and existing EIN name discovery. It no longer treats a temporarily empty Angular table as a completed response. Literal contains coverage removes redundant longer queries within the existing bound. Response counts must reconcile before interpretation. An exact/safe matching loaded record with blank filing fields remains Delinquent; zero returned matching records, a foreign EIN, or a failed request cannot trigger that rule. No organization exceptions.
- KY/HI period lookup distinguishes an alternate Hawaii organization page returning 404 (no public record) from a missing linked filing or a blocked/failed request (incomplete evidence). The existing disclosed calendar-period assumption is unchanged. Failure comments now identify the failing source step. Live CMI investigation confirmed the former 404 case.
- DC related-name candidates can be excluded only when the entire normalized registered name, street, state and ZIP agree with official Colorado charity records containing one different EIN. Source failure, partial names, ambiguous EINs or addresses retain review. The cross-check uses existing official source data, not hard-coded organization identifiers. Excluded-record evidence is retained in results.
- GA full-name matches without usable address evidence retain the existing classification and expose optional signed Accept/Reject identity controls. The comments explain the evidence limit. User decisions remain snapshot-bound and cannot supply statuses or override a foreign EIN.
- No connector update, environment-variable changes, production changes, new runtime sidecars or batch scheduler changes.

Validation commands: `python -m py_compile registry_snapshot_server.py`; `python testing/run_final_validation_guardrails.py`; existing `run_pa_completion_guardrails.py`; audit-output `run_regression.py final-tests`; Node `--check` for both audit clients; `git diff --check`.

Local results: 721 tests in 39 suites and 30 matching fixtures pass. Two source-scope parity allowlists explicitly cover the authorized functions. The older annual/short-period fixture was repaired to mock the current `irs_latest_period` entry point; its expected period assertions were preserved.

Live control and post-validation evidence is saved outside the repository under `outputs/final50-all34-postvalidation-20260926`. Staging deployment and those checks must be verified before completion. Do not promote while material findings remain unresolved.
