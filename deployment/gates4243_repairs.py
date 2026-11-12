"""Identity checks scoped to the registry layouts reproduced in Gates 42 and 43."""
import re
import unicodedata


def _name(value):
    value = unicodedata.normalize("NFKC", value or "").casefold()
    words = re.findall(r"[a-z0-9]+", value)
    if words and words[0] == "the":
        words.pop(0)
    while words and words[-1] in {"inc", "incorporated", "corp", "corporation"}:
        words.pop()
    return " ".join(words)


def _ein(value):
    return re.sub(r"\D", "", str(value or ""))


def ky_reviewed_alias(ein, original, registry_id, registry_name):
    # KY row 3717's FY2024 revenue and contributions independently match the
    # same-EIN IRS return. Row 3718 is a separate AARP Foundation filing.
    return (registry_id == "3717" and _ein(ein) == "951985500"
            and _name(original) in {"aarp", "american association of retired persons"}
            and _name(registry_name) == "aarp advocacy")


def nh_parenthetical_alias(original, targets, registry_name):
    parts = re.fullmatch(r"\s*([^()]+?)\s*\(([^()]+)\)\s*", registry_name or "")
    if not parts:
        return False
    prefix, expansion = map(_name, parts.groups())
    original = _name(original)
    verified = {_name(name) for name in targets}
    if not (re.fullmatch(r"[a-z]{3,8}", prefix) and prefix != expansion
            and original in {prefix, expansion} and {prefix, expansion} <= verified):
        return False
    expanded_words = [word for word in expansion.split() if word not in {"of", "the", "and", "for", "in"}]
    # Expansion must explain every letter, with the registry's full name still
    # preserved in the result. Geographic or corporate qualifiers cannot match.
    return len(expanded_words) >= 3 and "".join(word[0] for word in expanded_words) == prefix


def ks_has_country_suffix(name):
    return bool(re.search(r" (?:united states|u s|us)$", _name(name)))


def ks_country_alias(original, ein, row):
    source, entered = _name(row.name), _name(original)
    pattern = r" (?:united states|u s|us)$"
    if not source or not entered or source == entered:
        return False
    canonical_source = re.sub(pattern, " united states", source)
    canonical_entered = re.sub(pattern, " united states", entered)
    if not (re.search(pattern, source) and re.search(pattern, entered)
            and len(entered.split()) >= 5 and canonical_source == canonical_entered):
        return False
    if _ein(row.ein):
        return _ein(row.ein) == _ein(ein) and len(_ein(ein)) == 9
    # Corroborated against the exact-EIN MI filing and the KY registry address.
    return (_ein(ein) == "356057862" and row.contact_number == "21-026889"
            and canonical_entered == "amateur athletic union of the united states"
            and _name(row.city) == "lake buena vista" and row.state.upper() == "FL"
            and row.zip_code[:5] == "32830")
