"""FDACS Check-A-Charity migration coverage for Aurora staging."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import date, datetime
from html import unescape
from html.parser import HTMLParser
import hashlib
import re
from threading import Event
import time
from urllib.parse import urlencode
from urllib.request import Request, build_opener


URL = "https://consumercompliance.fdacs.gov/Check-A-Charity/"
MAX_BYTES = 2_000_000
EMPTY = "No licenses found matching your search."
FIELD_EIN = {"ein", "fein", "federal employer identification number"}
NUMBER = re.compile(r"CH[0-9]+")
LICENSE_EVIDENCE_NOTE = ("Original new FDACS card for the license number. "
                         "Aurora verified the organization and license in a recent Florida check.")


class CharityPage(HTMLParser):
    """Read only the official form, result count and public license cards."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.criteria = []
        self.scopes = 0
        self.cards = []
        self.depth = 0
        self.scope = None
        self.card_scope = None
        self.card = None
        self.text = []
        self.alerts = []
        self.alert = None
        self.part = None
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set((a.get("class") or "").split())
        if tag == "input" and a.get("name") == "search_name":
            self.criteria.append(a.get("value"))
        if tag == "div":
            self.depth += 1
            if "lr-scope" in classes:
                self.scopes += 1
                self.scope = self.depth
            if self.scope and {"alert", "alert-warning"} <= classes:
                self.alert = self.depth, []
            if self.scope and "license-item" in classes:
                self.card_scope = self.depth
                self.card = (a, {})
                self.cards.append(self.card)
        if tag in {"script", "style"}:
            return
        if self.card is not None and tag in {"h3", "dt", "dd"}:
            self.part, self.buffer = tag, []

    def handle_endtag(self, tag):
        if tag == self.part:
            fields = self.card[1]
            value = " ".join("".join(self.buffer).split())
            if tag == "dt":
                self.label = value.rstrip(":").casefold()
            else:
                key = self.label if tag == "dd" and hasattr(self, "label") else "heading"
                fields.setdefault(key, []).append(value)
            self.part = None
        if tag == "div":
            if self.alert and self.depth == self.alert[0]:
                self.alerts.append(" ".join("".join(self.alert[1]).split()))
                self.alert = None
            if self.card_scope == self.depth:
                self.card = self.card_scope = self.part = None
            if self.scope == self.depth:
                self.scope = None
            self.depth -= 1

    def handle_data(self, data):
        if self.scope:
            self.text.append(data)
        if self.alert:
            self.alert[1].append(data)
        if self.part:
            self.buffer.append(data)


def parse(source, query):
    if not re.search(r"</html>(?:\s*<!--[^<>]*-->)*\s*$", source, re.I):
        raise ValueError("Incomplete FDACS response")
    page = CharityPage()
    page.feed(source)
    text = " ".join(" ".join(page.text).split())
    # FDACS sometimes encodes punctuation before escaping the form attribute.
    # Accept one extra entity decode only when it reproduces the exact query.
    bound_query = (len(page.criteria) == 1 and page.criteria[0] is not None
                   and (page.criteria[0] == query or unescape(page.criteria[0]) == query))
    if (not bound_query or page.scopes != 1 or page.scope is not None
            or "Search Licenses" not in text
            or re.search(r"verify you are human|access denied|unable to load licenses", text, re.I)):
        raise ValueError("FDACS response was not bound to the submitted search")
    counts = re.findall(r"\b(\d+) record\(s\)", text)
    if not page.cards and not counts and page.alerts == [EMPTY]:
        return ()
    total = len(page.cards)
    if (page.alerts or not 1 <= total <= 50 or counts != [str(total)]
            or not re.search(rf"\bShowing 1 to {total} of {total} results\b", text)):
        raise ValueError("FDACS result count or pagination incomplete")
    cards = []
    for attrs, fields in page.cards:
        name, identifier, status, expiration, location = (
            (attrs.get("data-print-" + key) or "").strip()
            for key in ("name", "reg", "status", "expiration", "location")
        )
        # Bind the visible fields as well as the attributes backing Print.
        registered = fields.get("registration number", [])
        if (not NUMBER.fullmatch(identifier) or not name or not status
                or fields.get("heading") != [name] or len(registered) != 1
                or re.sub(r"\s+", "", registered[0]) != re.sub(r"\s+", "", identifier + status)
                or fields.get("expiration date") != [expiration or "N/A"]
                or fields.get("location") != [location or "N/A"]):
            raise ValueError("FDACS license card fields do not agree")
        tax_ids = [v for k in FIELD_EIN for v in fields.get(k, []) if v not in {"", "N/A", "-"}]
        if tax_ids and (len(tax_ids) != 1 or not re.fullmatch(r"\d{2}-?\d{7}", tax_ids[0])):
            raise ValueError("FDACS license card has ambiguous EIN")
        cards.append((identifier, name, status, expiration, location, tax_ids[0] if tax_ids else ""))
    if len({card[0] for card in cards}) != total:
        raise ValueError("FDACS repeated a license card")
    return tuple(cards)


def query_url(name):
    return URL + "?" + urlencode({"search_name": name, "sort": "name_asc"})


def fetch(master, name, deadline):
    url = query_url(name)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("FDACS migration budget ended")
    opener = build_opener(master.FloridaNoRedirect())
    headers = {"Accept": "text/html", "Accept-Encoding": "identity", "User-Agent": master.BROWSER_USER_AGENT}
    with opener.open(Request(url, headers=headers), timeout=min(3, remaining)) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError("Unexpected FDACS response")
        chunks, size = [], 0
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("FDACS migration budget ended")
            chunk = response.read1(65536)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError("Oversize FDACS response")
            chunks.append(chunk)
        declared = response.headers.get("Content-Length")
        if declared and (not declared.isdigit() or int(declared) != size):
            raise ValueError("Truncated FDACS response")
    return b"".join(chunks).decode("utf-8")


class MigrationCheck:
    """A single companion reader with the same lookup deadline as legacy FL."""

    def __init__(self, master, run):
        self.master, self.run = master, run
        self.stop = Event()
        self.pool = None
        self.future = None

    def start(self, names, deadline):
        self.names = tuple(dict.fromkeys(names))
        self.deadline = deadline
        self.prior_pages = dict(getattr(self.run, "fl_modern_pages", {}))
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fdacs-migration")
        self.future = self.pool.submit(self.search, min(deadline, time.monotonic() + 18))

    def search(self, deadline):
        pages = {name: self.prior_pages[name] for name in self.names if name in self.prior_pages}
        for name in self.names:
            if name in pages:
                continue
            if self.stop.is_set() or time.monotonic() >= deadline:
                break
            try:
                source = fetch(self.master, name, deadline)
                pages[name] = parse(source, name), source
            except (OSError, ValueError):
                # An unreadable or unavailable response supplies no coverage.
                continue
        return pages

    def close(self):
        self.stop.set()
        if self.pool:
            self.pool.shutdown(wait=False, cancel_futures=True)

    def finish(self, result, org):
        legacy_negative = result.success and result.status.casefold() == "not registered"
        if self.future is None or (result.success and result.matched_registry_identifier and not legacy_negative):
            return result
        try:
            pages = self.future.result(timeout=max(0, self.deadline - time.monotonic()))
        except TimeoutError:
            pages = {}
        self.run.fl_modern_pages = pages
        from deployment.search_history import SourceQueryReceipt

        master = self.master
        allowed = {master.complete_name_identity_key(n) for n in self.names}
        primary = master.complete_name_identity_key(org.organization_name)
        ein = master.canonical_ein_digits(org.ein)
        rejected = {entry["identifier"] for entry in getattr(result, "rejected_candidates", []) or []
                    if entry.get("identifier") and entry.get("ein")
                    and master.canonical_ein_digits(entry["ein"]) != ein}
        matching, suspect = {}, set()
        for query, (cards, source) in pages.items():
            if query not in self.prior_pages:
                receipt = SourceQueryReceipt(self.run, {"state": "FL", "operation": "search", "name": query,
                    "url": query_url(query), "source_kind": "state_portal", "filter_label": "New FDACS Check a Charity"})
                receipt.complete(len(cards), rows=[dict(identifier=c[0], name=c[1], status=c[2]) for c in cards])
            for card in cards:
                identifier, name, label, expires, location, public_ein = card
                if identifier in rejected:
                    continue
                if public_ein and master.canonical_ein_digits(public_ein) != ein:
                    continue
                key = master.complete_name_identity_key(name)
                if name == identifier:
                    suspect.add(identifier)
                    continue
                if key not in allowed or not master.reviewed_name_candidate_is_safe(name, org.organization_name, org.ein):
                    continue
                office = {}
                if not public_ein and key == primary and location not in {"", "N/A", "-"} and time.monotonic() + 1 < self.deadline:
                    office = master.reconciled_registry_address(
                        org.ein, name, location, registry_state="FL", deadline=min(self.deadline, time.monotonic() + 2))
                if not public_ein and office.get("decision") != "corroborated":
                    suspect.add(identifier)
                    continue
                if identifier in matching and matching[identifier][0] != card:
                    suspect.add(identifier)
                matching[identifier] = card, query, source, office

        if len(matching) == 1 and not suspect:
            card, query, source, office = next(iter(matching.values()))
            selected = self.selected_result(org, card, query, source, office)
            if selected is not None:
                return selected
            suspect.add(card[0])

        if legacy_negative:
            completed = getattr(self.run, "fl_query_progress", {}).get("completed", {})
            if not suspect and not matching and set(self.names) <= completed.keys() & pages.keys():
                result.source_note += " The new and legacy Florida Check-A-Charity searches completed."
                return result
        elif not suspect and not matching:
            recovered = self.recover_verified_license(result, org)
            if recovered is not None:
                return recovered
            if pages:
                result.source_note += " The new Florida portal was checked. The legacy search still needs a usable response."
            return result

        result.status, result.success = "Unable to Confirm", False
        result.reason_code = "FL_MIGRATION_COVERAGE_INCOMPLETE"
        result.status_reason = result.reason_code
        result.raw_status_text = "Florida migration coverage incomplete"
        candidates = sorted(set(matching) | suspect)
        result.source_note = (
            "Florida is migrating charity records. Both databases are used to check for a registration. "
            + (f"The new portal returned {', '.join(candidates[:5])}, but the available fields did not establish one verified status. "
               if candidates else "The search could not confirm coverage in both databases. ")
            + "Use the state lookup to review the registration before relying on a negative result."
        )
        return result

    def recover_verified_license(self, legacy, org):
        from deployment.fl_license_proof import PROOF
        proof = PROOF.get()
        master = self.master
        if (not proof or legacy.success is True
                or getattr(legacy, "reason_code", "") != "FL_SOURCE_NOT_RESPONDING"
                or getattr(legacy, "matched_registry_identifier", "")
                or getattr(legacy, "rejected_candidates", None)
                or proof["expires"] <= time.time()
                or proof["ein"] != master.canonical_ein_digits(org.ein)
                or master.complete_name_identity_key(proof["name"]) != master.complete_name_identity_key(org.organization_name)):
            return None
        # Reserve time for the existing original-card capture in the same run.
        stop = min(self.deadline - 3, time.monotonic() + 3)
        if stop - time.monotonic() < 1:
            return None
        identifier = proof["id"]
        try:
            source = fetch(master, identifier, stop)
            cards = parse(source, identifier)
        except (OSError, ValueError):
            return None
        # FDACS searches license numbers by prefix. Only the unique, exact
        # previously verified identifier can supply status or evidence.
        exact = [entry for entry in cards if entry[0] == identifier]
        if len(exact) != 1 or any(not entry[0].startswith(identifier) for entry in cards):
            return None
        card = exact[0]
        number, name, _, _, _, public_ein = card
        if (number != identifier or (name != identifier and
                master.complete_name_identity_key(name) != master.complete_name_identity_key(proof["name"]))
                or (public_ein and master.canonical_ein_digits(public_ein) != proof["ein"])):
            return None
        from deployment.search_history import SourceQueryReceipt
        receipt = SourceQueryReceipt(self.run, {"state": "FL", "operation": "search", "name": identifier,
            "url": query_url(identifier), "source_kind": "state_portal", "filter_label": "New FDACS, verified license"})
        receipt.complete(len(cards), rows=[dict(identifier=c[0], name=c[1], status=c[2]) for c in cards])
        return self.selected_result(org, card, identifier, source, {}, verified_name=proof["name"])

    def selected_result(self, org, card, query, source, office, *, verified_name=None):
        identifier, name, label, expires, _, public_ein = card
        status = {"Law NA - Educational": "Exempt", "Suspended": "Suspended", "Revoked": "Revoked",
                  "Denied": "Delinquent"}.get(label)
        expiration = None
        if expires not in {"", "-", "N/A"}:
            try:
                expiration = datetime.strptime(expires, "%m/%d/%Y").date()
            except ValueError:
                return None
        if status is None:
            if label in {"Registered", "Active Small Charity"} and expiration and expiration.year >= 1990:
                status = self.master.classify_expiration_date(expiration)
            elif label == "Expired" and expiration and expiration < date.today():
                status = "Delinquent"
            else:
                return None
        url = query_url(query)
        raw = "Status: " + label
        if expiration:
            raw += " | Expiration Date " + self.master.format_date(expiration)
        result = self.master.checker.StateResult(org.organization_name, org.ein, "FL", status, url,
            raw_status_text=raw,
            source_note=f"Florida's new Check-A-Charity portal lists {name} ({identifier}) as {label}.",
            success=True)
        result.matched_registry_name, result.matched_registry_identifier = verified_name or name, identifier
        result.status_reason = "FL_MODERN_VERIFIED_LICENSE"
        if verified_name:
            result.source_note = (f"Florida's new Check-A-Charity portal lists license {identifier} as {label}. "
                                  "The license number was verified for this organization in a recent Florida check.")
            self.run.fl_modern_verified_name = verified_name
        if public_ein:
            result.source_note += " The listed EIN matches the requested organization."
        if office:
            result.address_evidence = office
            result.identity_anchor = "cross_state_name_address"
        self.run.fl_modern_selected = (url, query, source, card)
        return result


def capture(run, result, page, deadline):
    """Capture the unchanged response that supplied the matched license."""
    url, query, source, card = run.fl_modern_selected
    identifier, name, *_ = card
    verified_name = getattr(run, "fl_modern_verified_name", None)
    if (result.get("source_url"), result.get("matched_registry_identifier"),
            result.get("matched_registry_name")) != (url, identifier, verified_name or name):
        return
    stop = min(deadline - 0.5, time.monotonic() + 8)

    def budget():
        remaining = stop - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("FDACS original capture deadline")
        return max(1, int(remaining * 1000))

    loaded = []

    def original(route):
        if loaded or route.request.url != url or route.request.method != "GET" or route.request.resource_type != "document":
            route.abort()
            return
        loaded.append(True)
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body=source)

    page.route(url, original)
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=budget())
        if not loaded or response is None or response.status != 200 or page.url != url:
            return
        locator = page.locator(f'.license-item[data-print-reg="{identifier}"]')
        if locator.count() != 1 or card not in parse(page.content(), query):
            return
        text = locator.inner_text(timeout=budget())
        raw = locator.screenshot(type="jpeg", quality=82, timeout=budget())
        if page.url == url and locator.inner_text(timeout=budget()) == text and card in parse(page.content(), query):
            note = "Original card from the new FDACS Check-A-Charity response."
            if verified_name:
                note = LICENSE_EVIDENCE_NOTE
                run.fl_verified_license_image = (
                    hashlib.sha256(raw).digest(), url, run.ein, identifier,
                    verified_name, result.get("raw_status_text"))
            run.document(url, raw, "image", text, note=note)
    finally:
        page.unroute(url, original)


def verified_license_image_bound(run, result, url, raw, kind):
    """The live card may display the verified license number in place of its name."""
    return (kind == "image" and result.get("status_reason") == "FL_MODERN_VERIFIED_LICENSE"
            and result.get("source_url") == url
            and getattr(run, "fl_verified_license_image", None) == (
                hashlib.sha256(raw).digest(), url, re.sub(r"[^0-9]", "", result.get("ein") or ""),
                result.get("matched_registry_identifier"), result.get("matched_registry_name"),
                result.get("raw_status_text")))
