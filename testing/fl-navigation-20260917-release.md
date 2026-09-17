# Florida navigation recovery follow-up

The 2026.09.17.10 random post-validation found Florida requests that timed out after 245 seconds without a result. The first six Florida attempts failed while the other 256 completed state checks matched the frozen spreadsheet. All original evidence remains under `outputs/or-ma-ny-repair-20260917` outside the checkout.

A traced local run reproduced the stall in `search_fl.load_fl_search_page`: after navigation timed out, `page.evaluate("window.stop()")` waited for the failed document's execution context without a deadline. Removing this evaluation lets the existing 3-second navigation to `about:blank` perform recovery. The live follow-up completed with Site Not Reachable while Florida remained unavailable. It did not convert missing evidence into a negative registration result.

The only functional change from .10 is this Florida navigation recovery path. Search variants, EIN/address checks, candidate ranking, status rules, retry counts, connector 0.3.3, downloadable data, and deployment targets remain unchanged. Four new tests cover recovery, repeated failures, a completed negative, and rejection of an unrelated record. The two recovery tests fail against the prior implementation and pass after the change.

Release .11 requires the normal shared regression, live controls, staging smoke, and completion of the same frozen 30-organization sample from the first 111 rows. Retain discovery evidence obtained on .10 because the complete name-discovery and matching functions are unchanged; record this provenance explicitly. Run all registration checks against .11. Never rewrite sheet expectations or count unavailable registries as passing checks.

Production is excluded. No extension reload is required for this follow-up.
