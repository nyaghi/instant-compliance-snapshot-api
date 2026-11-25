"""Reviewed filing identities. Each exception requires both the claimed EIN and source name."""

# The two Gate 77 filers are separate legal entities in IRS Schedule R.
_SEPARATE_NAMES = {
    "560532138": {
        "wake forest university health sciences": ("22-3849199",
            "https://apps.irs.gov/pub/epostcard/cor/223849199_202112_990_2023051221220009.pdf"),
    }
}


def separate_owner(ein, name):
    names = _SEPARATE_NAMES.get(str(ein or "").replace("-", ""))
    if names:
        return names.get(" ".join(str(name or "").casefold().split()))
    return None


# The original state PDFs show 2850 Abbey Plaza, Collegeville, MN on these
# rows. EIN 11-1630830 is the university at 8000 Utopia Parkway, NY.
# A renamed/reassigned state identifier must be reverified.
_OTHER_REGISTRATIONS = {
    ("111630830", "KY"): {"10489": "saint john's university"},
    ("111630830", "NH"): {"13524": "saint john's university"},
    # Pitt's Schedule R identifies the separate UPMC foundation, EIN 11-3708851.
    ("250965591", "KY"): {"11680": "university of pittsburgh and upmc medical and health sciences foundation"},
    ("560532138", "KY"): {"7727": "wake forest university health sciences"},
}


def excluded_registrations(ein, state):
    return _OTHER_REGISTRATIONS.get((str(ein or "").replace("-", ""), state), {})


def dc_separate_owner(ein, row, name_key):
    """Corroborated filing identity bound to this exact DC license and premises."""
    if (str(ein or "").replace("-", "") == "586033837" and not row.get("ein")
            and row.get("identifier") == "400223000134"
            and name_key(row.get("name", "")) == "university of west georgia foundation"
            and str(row.get("location", "")).casefold() == "carrollton, ga"
            and str(row.get("postal_code", ""))[:5] == "30118"
            and str(row.get("street", "")).casefold() in {"1601 maple", "1601 maple st", "1601 maple street"}):
        return ("58-6056464", "https://apps.irs.gov/pub/epostcard/cor/586056464_202306_990_2024050722386427.pdf")
    return None
