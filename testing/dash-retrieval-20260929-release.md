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

Live plan: 16 organizations in both modes for GA, RI and mature EIN-first CO;
then a reproducibly random set of 30 from all 179 populated entries of the
refreshed Fresh Test sheet, both Standard and Sales, all 34 states. Expected
spreadsheet values are frozen and not edited. Source evidence and initial
results are retained separately from retries. Production is not a target.
