# Verified bracket acronym regression cases

Observed September 15, 2026 for End Violence Against Women International, EIN 75-3095110. The user confirmed entering the full name without an acronym.

- Florida's completed search returns `END VIOLENCE AGAINST WOMEN (EVAW) INTERNATIONAL`, registration CH50868, Suspended. The row was discarded by numeric name ranking.
- Kansas's September 13 download contains `End Violence Against Women International (EVAWI)`, registration 25-007849, Registered, expiration June 30, 2026. Its EIN field is empty. The embedded exact-name gate discarded the row before the master identity check.
- Oregon's live detail record 80938 (registration 70296) supplies the same EIN and `End Violence Against Women (EVAW) International`. The downloadable file omits the organization. The completed live detail contains an empty Reports section; the existing reader infers Delinquent. The new explanation labels that inference and the live source accurately.
- West Virginia finds the active record C250226037226 and returns Upcoming Filing through February 26, 2027. The reported miss was not reproduced; no West Virginia-specific function was changed.

Full read-only reproduction evidence is in the workspace `outputs/evawi-acronym-20260915`, including the completed Oregon response HTML, Florida search trace, source screenshots, initial staging results and the analysis reviewed by the user. `testing/run_bracket_acronym_guardrails.py` exercises the recorded name pairs and fabricated negative/control rows. Fabricated rows are not registry evidence.

The new equivalence requires uppercase bracketed letters to repeat the initials of the full preceding phrase. After removal, the complete identities must be equal, apart from existing punctuation/corporate suffix normalization. Wrong EINs, arbitrary brackets, geographic distinctions and substantive extensions do not qualify. Exact original name ranking remains stronger than acronym equivalence.
