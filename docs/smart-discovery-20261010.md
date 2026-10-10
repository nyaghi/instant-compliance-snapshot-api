# Smart name discovery — October 10, 2026

The current master discovery code was run sequentially for the same 30 organizations as the earlier shadow study: 15 named controls and 15 fixed-seed selections from the first 190 records. This was discovery only; it did not run state registration checks or modify source records. Raw current results and per-source timing evidence are in `validation21/discovery_current_20261010.jsonl`.

| Measure | Current full deadline | Shadow 28-second deadline |
|---|---:|---:|
| Organizations | 30 | 30 |
| Mean time | 18.36 s | 17.70 s estimated |
| Median / p90 | 17.08 / 22.42 s | — |
| Runs over 30 s | 2 | 0 expected |
| Distinct names retained | 116 | 116 estimated |

Michigan was the only source finishing after 30 seconds in the current sample (2/30; maximum 38.0 s). New Jersey's p90 was 15.6 seconds, but it had been late in the earlier 30-organization study. Both supplied one unique name in the current sample, so removing either source entirely would discard evidence. Washington supplied 20 unique names, Ohio 11, IRS 9, and Pennsylvania 8; these sources remain valuable. New Mexico returned incomplete on all 30 current discoveries, but it finished within 6.5 seconds and did not drive the long tail. The older sample had 7/30 runs over 30 seconds and also retained all 116 names at a shadow 30-second boundary.

The surgical change keeps all existing sources in parallel, accepts their partial EIN-linked evidence until a 28-second server deadline, and stops the browser request at 30 seconds. It does not alter Sales mode, reviewed-name selection, identity safeguards, or registry matching. A partial source is still disclosed as limited; it is never treated as a negative registry result.

After the change, fresh discovery controls for National Parks Traveler, United Animal Nations — RedRover, and Chemical Coaters Foundation finished in 28.019, 28.005, and 23.082 seconds. All three retained the same normalized name sets as their full-deadline baselines, including Chemical Coaters' Michigan-only name. The 28-second comparison is a source-timing estimate plus these live controls. It does not prove that no future organization will have a valuable name arrive after 28 seconds; users can rerun discovery or add a verified name manually when a source is reported incomplete.
