# Georgia / Rhode Island literal dash retrieval

The entered name `Wild Ones — Natural Landscapers` and the EIN-confirmed alias
`WILD ONES -- NATURAL LANDSCAPERS, LTD.` were present, but the three generated
probes per name prioritized word permutations. Rhode Island's literal search
finds the single-hyphen spelling; Georgia finds its no-space double-dash record
with the prefix `Wild Ones`. Full-name identity scoring already accepted both
official spellings. Standard therefore returned a false negative at retrieval.

The master licensed-charity query planner now tries a literal single-hyphen
form and a distinctive prefix before speculative word permutations. The prefix
is retrieval-only and never added to accepted identities. All reviewed names
still precede generated queries, and the existing three-probe bound remains.
Ordinary compounds such as Make-A-Wish and Warrior-Scholar keep their old plan.

No state classification, date calculation, identity acceptance, timeout,
discovery, concurrency, connector, or worker-capacity changes are included.
The shared planner also serves DC and Illinois; both are in post-validation.

Pre-deployment: 142 Python controls passed (including Pennsylvania, chapter,
wrong-EIN, address conflict, incomplete-response and original plan controls),
and 15 JavaScript workflow/deadline tests passed. The original failure and
first preservation-test failure remain in the audit directory. The historical
Aurora preservation assertion exempts this intentionally changed planner;
the new test checks all other existing master functions against release 1ba90bd.

Live validation completed: 16 organizations in both modes for GA, RI and
mature EIN-first CO, followed by the same random 30 from all 179 populated
entries of the refreshed Fresh Test sheet, both modes across all 34 states.
Seed: 15432262051253100775. Expected spreadsheet values were not edited.
Source evidence and first attempts are preserved separately from follow-ups.

Wild Ones now returns GA Current (CH016436) and RI Upcoming Filing
(CO.9904011) in both modes. Standard controls matched 48/48; Sales 47/48.
PEN America/RI is a pre-existing Sales alias-coverage failure reproduced
against both the old and new planner. The random sample contains additional
Sales alias gaps: YWCA/AR and CurePSP/GA/RI. CurePSP's old/new plans are
identical; Arkansas and Sales identity code are unchanged. No broad alias
acceptance change was folded into this release.

Random Standard: 1020/1020 checks recorded, 1019 conclusive, 999 exact
normalized sheet matches. Mean execution 42.068s, range 17.028-102.130s;
mean full discovery 22.682s. Random Sales: 1020/1020 checks recorded,
1013 conclusive, 991 exact sheet matches. Mean execution 34.850s,
range 20.592-60.208s. Conclusiveness is not independently verified accuracy.
One organization ran at a time; this is not a concurrent-load benchmark.

Other open findings: Tides Network/KY appears as "Tides Newwork" in the
state PDF itself (likely false negative); YWCA/DC retains an unresolved
address conflict; six Sales checks stopped at their deadline or returned
incomplete source/browser responses. Ceres/WA changed because the state
record shows a renewal filed today, confirmed in the official UI.

Final automated checks: 155 Python and 15 JavaScript tests passed. The extra
13 Python controls cover the staging workflow. The validation page received
an explicit persistent download link after automatic downloads failed; the
link exported and preserved all 2136 control and post-validation results.

Live frontend and all backend roles were verified on the September 29
release. Runtime code commit: e73988d36046956412be907a8d1f62a7570e9282.
Latest frontend deploy: 6abbe48de46b40ed75247577. Capacity and limits unchanged;
only version-label environment values changed. Production untouched.

Recommendation: Needs review. The dash repair is verified on staging;
the complete release must not be described as spotless. Full evidence,
workbook and categorized differences: project outputs/wild-ones-ga-ri-20260929.
