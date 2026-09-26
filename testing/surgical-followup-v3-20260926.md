# Targeted follow-up after live .2 validation and user source review

Staging candidate: 2026.09.26.3-staging / connector 0.5.6.

- Live First Responders / GA completed 36 commands, then the frontend stopped.
  The prior backend-capacity change was necessary but insufficient. IL/GA now
  follow master continuation until completion, with a five-minute UI deadline;
  NY's existing ten-command bound is unchanged. Executable frontend tests cover
  42/61 commands, master inconclusive completion, and timeout cleanup.
- Air Force Academy / GA returned Exempt with 0.5.5; the unnumbered exemption
  is now supported. Air Force Academy / IL instead failed form readiness on
  a late fallback, after repeated fresh navigations. Reuse the ordinary public
  form within a lookup, clear every public filter before each query, and reload
  after detail navigation or a failed command. No verification is bypassed.
- User corrected ACOEL / GA to Exempt. The independently inspected primary
  exemption record explicitly says Exempt (issued May 22, 2019; no expiration).
  Confirmed GA Exempt records now take priority over ordinary filing dates.
  Identity and suspension/revocation conflict checks remain mandatory. Other
  same-entity records are retained in comments. This does not change RI policy.
- DC now includes license category and other confirmed records in comments,
  and directs freshness verification to BOSS. A Charitable Exempt category
  whose status is Expired - Enforcement does not establish a current exemption.
- Independent BOSS detail pages confirm Colorectal Cancer Alliance license
  400220000131 Active, issue 09/02/2026, expiration 09/30/2028, and American
  Public Gardens 400224000701 Active, issue 08/20/2026, expiration 08/31/2028.
  Those match the September 25 public extract. SCOUT displays older dates and
  itself directs users to BOSS. Prior 'expected sheet drift' conclusions are
  reopened and documented against these source comparisons.

Original spreadsheet expectations remain unchanged. Production is not
authorized. Full test results, pinned deployment metadata, and live regression
must be reported before recommending promotion.
