# WV and SC surgical selection fixes

WV: prefer an Active row among safe organization matches before comparing name scores. Preserve closed-only results, identity validation, bounded queries, and existing status/date interpretation.

SC: both the official HTTP candidate gate and browser fallback extension gate accept an exact recognized legal-name/alias target from the master name generator. The existing master identity gate still runs. Other state call sites and shared matching behavior are unchanged.

Predeployment: 12 new offline regression tests pass, including reversed duplicate order, active alias, unrelated active row, closed-only record, mismatched detail, completed no results, registry timeout, SC combined/separate aliases, fallback, unrelated extension rejection and terminal statuses. Core matching (30 approved fixture rows) and the existing manual reconciliation, filing evidence, comments, MA Form PC, FL/NJ/ND, reported-state, NJ/OK recovery suites pass. NMDP suite: 9/10 pass; its Oklahoma certificate assertion fails identically against unchanged origin/staging f10b803. No expected fixture values were changed.

Local live smoke: Comic Relief WV Current (5533); combined Eckerd SC Upcoming Filing (P35089); Make-A-Wish WV Current and SC Upcoming Filing; Junior Achievement USA WV/SC Not Registered; Make-A-Wish CO Current. Five unaffected controls match live staging before deployment.

Regression source: Fresh Test, Orgs A1:AG31, https://docs.google.com/spreadsheets/d/15McQtRw3pSbV_Bck_DC_nWaTcmnP1KWQJZ11iGfeamQ/edit . Source expected values are preserved. The requested first 30 rerun and postdeployment verification are recorded separately under the parent workspace outputs/wv-sc-fix-20260910. This document is the predeployment gate, not proof of deployment or the completed rerun.

Production not authorized. Stage only; do not promote while material unexplained differences or inherited failures remain.
