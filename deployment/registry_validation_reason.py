"""Finite public explanations; never expose arbitrary exception or page text."""

_REASONS = {
    "NC": {
        "North Carolina matching unsupported category needs scope confirmation":
            "North Carolina returned a potentially matching record whose category or denied application does not establish current charitable-registration standing. Review the official record to resolve its registration scope.",
        "North Carolina result is not an identified charity license":
            "North Carolina returned a result card with a license/category combination that could not be interpreted safely. The lookup stopped without treating that record as registered or absent.",
        "North Carolina profile does not belong to the selected charity":
            "North Carolina's opened profile did not agree with the selected result's identity. No status or image from the differing record was used.",
    },
    "NV": {
        "Nevada filing history is incomplete or belongs to another entity":
            "Nevada's required filing history was incomplete or did not match the selected entity. Charitable-registration standing could not be established from that history.",
        "Nevada charitable solicitation scope is unconfirmed":
            "Nevada's complete filing history did not contain a qualifying charitable-solicitation registration or exemption filing. The record alone does not establish charitable-registration standing.",
        "Nevada charitable solicitation renewal deadline is unconfirmed":
            "Nevada did not provide a usable renewal deadline for the selected active charitable-registration record. No deadline or current standing was inferred.",
        "Nevada detail differs from the selected search identity":
            "Nevada's opened detail did not agree with the selected search record. The differing record was not used to determine status.",
        "Nevada entity details are incomplete":
            "Nevada's selected entity detail did not contain all required public fields, so its registration standing could not be established.",
    },
}


def public_validation_reason(state, diagnostic):
    from deployment.lab_identity import trial_identity
    if not trial_identity() or not isinstance(diagnostic, str):
        return ""
    return _REASONS.get(state, {}).get(diagnostic, "")
