# Reported-state corrections — 2026.09.08.2-staging

The rollback experiment reproduced preexisting identity/parsing problems. These corrections are in the master backend with no organization-specific runtime exceptions.

- MN: a conflicting FederalID cannot be overridden by an alias/name match. Reject conflicting links before ranking and verify the detail EIN.
- MS/shared matching: ignore only a trailing comma-delimited nonprofit corporate description. Preserve the remaining legal name, jurisdiction/chapter distinctions, aliases, and conflicting-EIN rejection. Keep the original registry name visible.
- NH: retain all status-code rows. Under the user's explicit rule, C uses the listed report-due date. G/X/S retain their existing interpretation. Unknown codes and C/G without dates remain inconclusive. Preserve source freshness notes.
- MA: restore identity-confirmed, completed all-filings response observation. Infer Delinquent only from a completed empty history without a contrary status. Loading/failed/filtered tables do not prove emptiness. Preserve explicit inactive/exempt/adverse status handling and disclose inference.
- MD: use the automatic extension whenever the registry explicitly says Current, including before the base due date. Official deadline: 15th day of the 11th month after fiscal year-end. Source: https://sos.maryland.gov/Charity/Pages/Registering-Charity.aspx
- ME: an unparsed response or partially failed name-query set cannot establish a completed no-record direct search.
- ND: wait for the completed FirstStop search response and read the selected detail through the existing browser session. Rank returned candidates with master identity helpers. This replaces the premature-zero/limited DOM scan; no separate runtime service/script.
- NY: retain original 12-second response and 35-second overall allocations, allowing one transient retry inside that total. Transport failures/blocks report Site Not Reachable; incomplete identity/documents remain Unable to Confirm. Separate 50-second diagnostics still received no detail bytes for ELI and Accion. No empty-record inference from timeouts. Preserve filing-history/exemption calculations.
- Web: restore email variable scope fix; display new staging version.

Final validation/deployment evidence is in outputs/open-state-fixes-20260908 in the parent workspace. Approved expectations remain unchanged. Staging only; no production/environment-variable changes. Do not promote with material unresolved mismatches.
