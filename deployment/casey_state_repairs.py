"""Narrow Mississippi retrieval for an initial-bearing personal foundation name."""
import re


def ms_personal_foundation_probe(name, reviewed):
    # First M. Last Foundation has a stable index word even where the portal
    # moves Last to the front. Exclude common organizational phrases and any
    # reviewed alias not covered by the same public name search.
    m = re.fullmatch(
        r"(?:The )?[A-Za-z]{3,} [A-Z]\.? ([A-Za-z]{5,}) Foundation(?:,? Inc\.?)?",
        name.strip(), re.I)
    if not m:
        return ""
    token = m[1]
    if token.casefold() in {"america", "american", "charity", "community", "family", "foundation",
                            "health", "international", "memorial", "national", "public", "united"}:
        return ""
    literal = re.compile(r"\b" + re.escape(token) + r"\b", re.I)
    return token if all(literal.search(value) for value in reviewed) else ""
