# Illinois bounded fresh-page recovery

The 0.5.10 live acceptance run completed 12 checks: 10 matched expectations,
and two Illinois checks stopped at verification before search submission. One
failed while hidden and the other while visible, so visibility alone is not a
sufficient explanation. A subsequent normal Chrome visit reproduced a visible
Cloudflare "Verifying..." stall with Search hidden. A single ordinary reload
then exposed Search without any challenge interaction. This establishes a
recoverable verification stall, not its internal Cloudflare cause.

The master now authorizes one fresh browser transport after
`NY_CONNECTOR_IL_VERIFICATION_PENDING`, using the installed 0.5.10 connector's
existing finish/acquire/search protocol. The frontend opts into the recovery
contract. Old clients, other errors, other states, and name discovery retain
their previous behavior. No extension package update is required.

The signed continuation retains completed public evidence, organization,
reviewed names, and the original deadline. The pending query is unchanged and
its response ID rotates, rejecting late evidence from the failed transport.
Recovery requires more than 120 seconds remaining and is allowed once per
continuation. Queue waiting and the second transport consume the original
five-minute budget. Both success and failure preserve the original stall in
`connector_recovery`; unresolved searches stay inconclusive. There are no
organization-specific overrides or changed expected results.

No verification tokens, cookies, or challenge state are read or altered. No
hidden controls are enabled. The ordinary state page must enable Search.
The source of a persistent verification failure remains a source limitation.

Release evidence and live results are recorded in
`outputs/illinois-verification-recovery-20260927` in the primary project.
Production is not authorized. Live repeated acceptance is required before any
promotion recommendation.
