# Florida verified certificate-chain recovery — staging 2026.09.24.4

## Problem and implementation

The FDACS Check-A-Charity endpoint presents a September 18, 2026 GoDaddy OV R1 certificate but omits the R1-to-G2 cross certificate. Staging 2026.09.24.3 failed before searching with `net::ERR_CERT_AUTHORITY_INVALID`; a fresh America's Charities check reproduced it in 71.49 seconds including existing semantic retries.

The master backend now activates a Florida-only verified HTTPS transport after that browser authority failure. The existing browser form submission, reviewed aliases, candidate selection and status calculation remain in use. The cross certificate is supplied to a private SSL context; hostname verification and certificate verification remain required, and partial-chain trust is disabled. No trust store, infrastructure setting, global timeout, browser engine, name-discovery path, concurrency setting, or New York connector was changed. The route is removed after the lookup. Certificate recovery failures receive a specific public explanation and do not repeat futile semantic retries.

The optional Florida license-issue date lookup uses the same verified chain only after curl certificate error 60, within its existing six-second allowance. A failed optional date read still cannot alter the registration status.

## Predeployment evidence

- 139 Python regression/control tests passed, including real local TLS handshakes rejecting expired, wrong-host and untrusted certificates; POST/session preservation; redirects; incomplete reads; route cleanup; existing FL no-record and matching controls; shared matching, comments, discovery capacity, dates, DC/RI and Standard/Sales controls.
- 20 JavaScript tests passed for Sales selection, 15-state lanes, the 60-second deadline, Standard transport and NY cancellation isolation. Registration-date UI/Excel/syntax validation passed.
- Live controls used fresh discovered names and the approved sheet export retrieved September 24 at 14:32:58Z. Eight Florida and three Colorado EIN-first controls completed: 10 matched the sheet. National Marrow Donor Program matched exact-name record CH4033 expiring August 3, 2027 and returned Current against sheet Delinquent. The original, unmodified matcher given the verified connection returned the same record and status. Categorized as expected sheet drift; spreadsheet unchanged.
- Florida live local controls: 6.56–29.47 seconds, covering Current, Upcoming Filing, Suspended and completed Not Registered. No certificate failures remained in these controls. This is not a new full-platform capacity claim.
- Optional-date live test recovered America's Charities CH689's March 17, 1992 issue date in 2.06 seconds and preserved Upcoming Filing.

## Rollout and postvalidation

Staging deployment completed. Both existing Render services run backend version `2026.09.24.4-staging`, pinned to runtime commit `9092827346f7ebc677f143f8c83671b7475e5649`. Environment variables and instance counts were verified unchanged. Netlify staging deployment `6ab5490601d7acf7af6d5942` preserves other assets and both functions; the main HTML differs only in the footer version. Live Sales and discovery JavaScript hashes are unchanged, both API targets are staging, and all three application/validation HTML pages show the new release label. UI footer follow-up commit: `8a5dbb0`.

Postdeployment: all 11 API controls returned definitive results, with 10 sheet matches and the same documented National Marrow Donor Program discrepancy. Florida checks took 13.75–31.84 seconds. Initial registration dates were recovered where available.

Actual browser UI smoke used three concurrent isolated organization contexts (America's Charities, Make-A-Wish Foundation of America, Junior Achievement USA). Each ran fresh discovery, Standard, then Sales for Florida and Colorado. All six UI runs / 12 state results passed; no Sales cutoff or certificate failures occurred. Standard elapsed times: 19.27, 19.84 and 55.51 seconds. Sales: 16.04, 14.29 and 28.90 seconds. These are two-state controls, not a new 15-organization/32-state capacity benchmark.

Known issues: one expected-sheet discrepancy pending user review; no unresolved Florida code failure in these controls. Recommendation: Needs review for the sheet correction; staging fix is verified. Full evidence and exact commands are in `REPORT.md` in the evidence directory below.

Production touched: No. No production promotion is authorized.

Evidence: `C:/Users/nyagh/OneDrive/Desktop/Compliance Express/Projects/CharityClarity/outputs/fl-certificate-fix-20260924`.
