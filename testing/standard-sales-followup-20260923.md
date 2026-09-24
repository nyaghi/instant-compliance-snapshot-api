# Mixed-mode follow-up release

Scope: staging only. Backend 2026.09.23.4-staging; UI 2026.09.23.6.

- Validation sample preparation damaged a UTF-8 apostrophe in Trust for America's Health. The native Sheet and exported source are correct. Refresh sample values directly with explicit UTF-8 and compare all primary names to source rows. Narrow punctuation normalization also tolerates recognized misdecoded punctuation at the master lookup entry; letters, EINs, address checks and chapter rejection are preserved.
- Maine's six-query plan omitted the ordinary AND spelling when the input used an ampersand and no discovered names. Put this literal equivalent before generated hyphen searches, retaining the existing query cap and identity rules.
- Massachusetts completed EIN-bound public histories with only old documents were held up by unreadable identity text inside a legacy scan. Completed stale-history inference is independent of that optional scan. Incomplete public lists, recent/unknown years and observed foreign document EINs continue to prevent inference. No exact fiscal date is invented from an old year label.
- Kentucky fiscal-period resolution invoked full IRS historical-name discovery and could reuse a partial name cache lacking a filing. Read the filer header separately, retry one failed read within the existing 14-second caller budget, and reuse confirmed period evidence. Retrieval failures cannot become assumed calendar years. A fresh Earthjustice cold lookup completed successfully, so the original remote failure cannot be attributed to a specific network event; the partial-cache and failed-header path is covered deterministically.
- ACOEL and National Credit Union Foundation have newer active charity licenses in D.C. BOSS. Actual portal details were checked: 400226030242 (ACOEL, issued 08/13/2026, expires 08/31/2028); 400225000034 (NCUF, issued 10/25/2024, expires 09/30/2026). No D.C. classification change is needed. Sales groups Upcoming Filing as Current as designed.

No organization-specific runtime exceptions, scheduler/concurrency changes, NY connector changes, environment changes or production deployment.

Controls: Massachusetts history/scan rules; fiscal-period/short-year/foreign-EIN rules; CT/ND name lookup; Maine query budget and address guards; KY/HI completion; reviewed/historical aliases; mature-state matching; DC/RI selection; Sales grouping, progressive results, exact 15 lanes; discovery/connector and Standard scripts unchanged.

Post-validation: reuse the random 15 Standard + 15 Sales sample, refreshed against the native Fresh Test Sheet; FL and WI excluded by user instruction. Preserve first attempts and report later diagnostics separately. Detailed evidence and execution logs live under outputs/standard-sales-fixes-20260923 in the main project workspace.
