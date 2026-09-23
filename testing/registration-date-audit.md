# Registration Date audit — September 22, 2026

This column records evidence from the selected registration. It does not infer a registration date from a renewal, filing, fiscal period, incorporation, approval or expiration. No extra registry requests are added for this field.

Confirmed dates use ISO YYYY-MM-DD plus the source label and meaning. A generic state label **Registration Date** is preserved as generic: it is not renamed **Initial Registration Date**. An unconfirmed identity or ambiguous selection cannot supply the field.

| State | Current extracted evidence / handling |
|---|---|
| AK | Registration year/expiration and selected record; no confirmed initial date retained. Unavailable. |
| AR | Matched search row has Registration Date. Exposed with the exact generic meaning. |
| CA | Selected registration's initialRegistrationDate, tied to registrationNumber. Exposed as Initial Registration Date. YWCA source control: 2005-08-31, distinct from 2025-11-15 current expiration. |
| CO | Approval/renewal/expiration fields are not an initial registration date. Unavailable. |
| CT | Credential status/expiration; no confirmed initial charitable registration date retained. Unavailable. |
| FL | Selected Check-A-Charity status/expiration; no confirmed initial date retained. Unavailable. |
| HI | Filing periods and registration category; no confirmed initial date retained. Unavailable. |
| KS | Downloaded registration/status data does not supply a confirmed initial date in the current extraction. Unavailable. |
| KY | Name, DBA and last-filed tax year do not establish the initial registration date. Unavailable. |
| LA | Current registered-charities export extraction lacks a confirmed initial date. Unavailable. |
| MA | Form PC periods and submission dates are not initial registration dates. Unavailable. |
| MD | Registration status/renewal evidence; no confirmed initial date retained. Unavailable. |
| ME | Credential issue/renewal dates must not be substituted for an initial charitable registration date. Unavailable pending source-label verification. |
| MI | Solicitation and trust registration fields must remain separate; no confirmed initial charitable registration date retained. Unavailable. |
| MN | Exact FederalID-linked detail and aliases; no confirmed initial date retained. Unavailable. |
| MS | Filing status/expiration; no confirmed initial date retained. Unavailable. |
| ND | Selected completed detail has Registration Date. Exposed with exact generic meaning. Multiple equally inactive records do not supply one record's date. |
| NH | Report due date in downloaded list is not a registration date. Unavailable. |
| NJ | Filed fiscal periods and submission dates are not registration dates. Unavailable. |
| NM | Charity Added, tax year and open registration period are distinct from initial registration. Unavailable. |
| NY | Confirmed EIN/category/filing periods; no initial registration date retained by the current connector response. Unavailable. |
| OH | Research detail/status/filing dates; no confirmed initial date retained. Unavailable. |
| OK | Renewal registration filings and certificates prove renewal/expiration, not initial registration. Unavailable. |
| OR | Report periods and next deadline are not initial registration. Unavailable. |
| PA | Status, certificate and expiration evidence; no confirmed initial date retained. Unavailable. |
| SC | Status/expiration from selected record; no confirmed initial date retained. Unavailable. |
| VA | Initial issue/approval fields may concern the selected certificate; they are not substituted for initial charitable registration. Unavailable. |
| WA | Registration/renewal status and date; no confirmed initial date retained. Unavailable. |
| WI | Credential issuance/location/status does not establish the original charitable registration date. Unavailable. |
| WV | Filing/certificate/expiration from selected record; no confirmed initial date retained. Unavailable. |

“Unavailable” describes the confirmed data returned by the current lookup, not a claim that the state never publishes the date elsewhere. The master retains candidate date labels encountered in already-retrieved page text as audit observations; those observations never populate the field or alter status without a record-specific semantic rule.

Validation: date-source controls cover selected-record binding, conflicting CA dates, false/uncertain identity, future/invalid dates, and prevention of renewal/expiration substitution across all 30 states. Report tests preserve the date and its meaning; report generation does not re-query registries.
