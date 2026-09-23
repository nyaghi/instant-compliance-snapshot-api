# All 30 states: original registration and last renewal dates

Both columns apply to every supported state. Missing/unverified values, labels and notes remain BLANK in the UI, Excel and PDF, per the user's September 23 instruction. Blank does not mean unregistered.

Source labels stay visible. Issue/effective/filing dates retain their meaning; submission does not establish approval. Expiration, deadlines, incorporation dates, fiscal periods and guessed January 1 dates never fill either column. Generic Registration Date is not silently described as first-ever registration.

## Audit coverage

All 30 master lookup paths were exercised. Additional public-source checks covered Florida Business License Lookup, Colorado History, Massachusetts charity details/Form PC, Oregon live detail, NY RegistryDetail, PA entity-detail API, CT credential detail, VA registrations, and actual KY/LA download headers. This describes the sources inspected, not every historical paper record a state may hold. Field availability varies by organization and retrieval path.

| State | Initial/original source | Last renewal/current period source | Treatment |
|---|---|---|---|
| AK | No complete initial date in cycle evidence | Cycle year/expiry only | Blank; no year-to-date inference. |
| AR | Selected row Registration Date | No distinct last renewal in row | Retain generic label. |
| CA | initialRegistrationDate | currentIssuanceDate, if different from initial | Preserve Current Issuance Date; exclude renewalEvaluationDate. |
| CO | Initial registration | History Renewal/Reinstate renewal Filed Date | Bind selected ID/name; exclude notices, extensions and financial reports. |
| CT | No initial date in inspected detail | PUBLIC CHARITY credential Effective Date | Exact selected CHR ID; preserve current-effective meaning. |
| FL | Separate license lookup Issued | Application/financial document receipts do not independently establish completed renewal | Bind issuance to same accepted CH number and name. |
| HI | Registration year/URS, no verified complete date | Annual document years | Blank; no inferred month/day or signature-date substitution. |
| KS | Downloaded list ID/expiration | No last-renewal date in list | Blank; expiry not substituted. |
| KY | PDF ID/Name/Contributions/Revenue/Yr Last Filed/Address/DBA | No full renewal date | Blank; tax year is not renewal date. |
| LA | Excel Charity/Registered Through/Program Services percentage | Registered Through is expiry | Both blank. |
| MA | Public charity formation/determination dates | Form PC fiscal periods/submitted status | Both blank; formation/First Charity Engage Date is not registration. |
| MD | Public OneStop identity/status/year/financial data | No explicit last renewal in inspected entry | Both blank. |
| ME | Incomplete history cannot prove original date | Active history periods can span multiple annual renewals | Both blank; Purpose/OTHER Issue Date excluded. AFAR receipt not relabeled completed renewal. |
| MI | Search/summary file number/foundation date/expiry | Renewal Pending is status, not date | Both blank. |
| MN | EIN detail status and fiscal periods | Extension is not completed renewal | Both blank. |
| MS | Selected panel Initial Date Filed, sometimes empty | No explicit last-renewal date | Preserve filing meaning, not approval. |
| ND | Selected Registration Date | AR Due/AR Extended Due are deadlines | Initial column generic label; no date from duplicate status-only consensus. |
| NH | Downloaded report due date | No last-renewal date in list | Both blank. |
| NJ | Public detail/iframe identity and annual history | No explicit completed registration renewal date identified | Both blank; fiscal period not substituted. |
| NM | Charity Added not verified registration approval | Latest annual Registration Submitted | Preserve submission meaning; exclude Open/Extension Requested. |
| NY | RegistryDetail ID/EIN/type/address/documents, no original field | CHAR500 annual documents not registration renewal | Both blank; no connector change or extra requests. |
| OH | Date Founded is formation | Annual financial year not renewal date | Both blank. |
| OK | Charitable record Original Filing Date | Latest Renewal Registration Filing Date | Selected ID/name; exclude amendments/cancellations; retain filing meaning. |
| OR | Live EIN detail ID/status, no initial date | Reports show fiscal periods | Both blank; no export/FYE substitution. |
| PA | API EstablishedDate is formation | ExpirationDate/FYE not last renewal | Both blank. |
| SC | Selected Public ID/status, no initial date | Due Date and financial period | Both blank. |
| VA | initialIssueDate | issueDate when distinct from initial | Preserve issue labels; exclude expiry/extension. |
| WA | No initial date in inspected detail | Renewal Date is upcoming deadline | Both blank; past deadline also cannot become last renewal. |
| WI | Accepted credential row Granted | No explicit last renewal | Preserve Granted; fallback responses omitting it remain blank. No extra financial/human-verification requests. |
| WV | Initial Registration Date, sometimes N/A | Last Registration Date | Selected ID/name; exclude Legally Established Date. |

## Safeguards

Common formatting is pure, with no I/O. VA/CT/WI retain already-fetched evidence. Existing source bodies supply AR/CA/ND/WV/OK/MS/NM dates. Florida adds at most two 3-second public requests after status classification. Colorado reads the selected History with bounded waits after the primary lookup. Date failures cannot change status, comments, matching, discovered names, budgets or retry decisions. No sidecar, environment or shared-concurrency changes.

The initial YWCA source audit omitted reviewed aliases; its no-matches are not regression results. Release controls use reviewed aliases and approved baseline expectations. Evidence: project outputs/registration-dates-30state-20260923/.
