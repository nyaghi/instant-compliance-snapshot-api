from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


FUNNEL_EVENTS = {
    "landing_page_viewed",
    "free_search_form_started",
    "free_search_form_submitted",
    "free_search_repeat_rejected",
    "free_search_completed",
    "free_result_viewed",
    "paid_offer_viewed",
    "stripe_checkout_started",
    "purchase_completed",
    "search_error",
    "checkout_error",
}

ATTRIBUTION_FIELDS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "gclid",
    "source",
    "medium",
    "campaign",
    "ad_group",
    "keyword",
    "match_type",
    "referrer",
    "landing_page",
    "session_id",
}


def normalize_email(value: str) -> str:
    return str(value or "").strip().lower()


def clean_attribution(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, str] = {}
    for key in ATTRIBUTION_FIELDS:
        raw = str(value.get(key) or "").strip()
        if raw:
            cleaned[key] = raw[:500]
    return cleaned


@dataclass(frozen=True)
class EligibilityDecision:
    eligible: bool
    reason: str
    request_id: str = ""


class FunnelStore:
    """Concurrency-safe, first-party storage for the free-search pilot."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        self._schema_lock = threading.Lock()
        self._ensure_schema()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
        finally:
            connection.close()

    def _ensure_schema(self) -> None:
        with self._schema_lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS free_searches (
                    normalized_email TEXT PRIMARY KEY,
                    original_email TEXT NOT NULL DEFAULT '',
                    request_id TEXT NOT NULL UNIQUE,
                    organization_name TEXT NOT NULL DEFAULT '',
                    ein TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '',
                    completion_status TEXT NOT NULL,
                    allowance_consumed INTEGER NOT NULL DEFAULT 0,
                    failure_category TEXT NOT NULL DEFAULT '',
                    attribution_json TEXT NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    completed_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS funnel_events (
                    event_id TEXT PRIMARY KEY,
                    event_name TEXT NOT NULL,
                    occurred_at INTEGER NOT NULL,
                    session_id TEXT NOT NULL DEFAULT '',
                    request_id TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '',
                    error_category TEXT NOT NULL DEFAULT '',
                    revenue_cents INTEGER NOT NULL DEFAULT 0,
                    attribution_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_funnel_events_occurred_at
                    ON funnel_events(occurred_at);
                CREATE INDEX IF NOT EXISTS idx_funnel_events_request
                    ON funnel_events(request_id);
                """
            )

    def reserve_free_search(
        self,
        email: str,
        original_email: str,
        organization_name: str,
        ein: str,
        state: str,
        attribution: object,
        stale_after_seconds: int = 900,
    ) -> EligibilityDecision:
        normalized = normalize_email(email)
        if not normalized or "@" not in normalized:
            return EligibilityDecision(False, "invalid_email")
        now = int(time.time())
        request_id = uuid.uuid4().hex
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT completion_status, allowance_consumed, updated_at FROM free_searches WHERE normalized_email = ?",
                (normalized,),
            ).fetchone()
            if row and int(row["allowance_consumed"] or 0):
                connection.execute("COMMIT")
                return EligibilityDecision(False, "already_used")
            if row and row["completion_status"] == "processing" and now - int(row["updated_at"]) < stale_after_seconds:
                connection.execute("COMMIT")
                return EligibilityDecision(False, "in_progress")
            values = (
                str(original_email or "").strip()[:320],
                request_id,
                str(organization_name or "").strip()[:500],
                str(ein or "").strip()[:32],
                str(state or "").strip().upper()[:2],
                json.dumps(clean_attribution(attribution), sort_keys=True),
                now,
                now,
                normalized,
            )
            if row:
                connection.execute(
                    """UPDATE free_searches
                       SET original_email=?, request_id=?, organization_name=?, ein=?, state=?,
                           status='', completion_status='processing', allowance_consumed=0,
                           failure_category='', attribution_json=?, created_at=?, updated_at=?, completed_at=NULL
                       WHERE normalized_email=?""",
                    values,
                )
            else:
                connection.execute(
                    """INSERT INTO free_searches
                       (original_email, request_id, organization_name, ein, state, attribution_json,
                        created_at, updated_at, normalized_email, completion_status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'processing')""",
                    values,
                )
            connection.execute("COMMIT")
        return EligibilityDecision(True, "eligible", request_id)

    def complete_free_search(self, request_id: str, status: str) -> bool:
        now = int(time.time())
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE free_searches SET status=?, completion_status='completed', allowance_consumed=1,
                   failure_category='', updated_at=?, completed_at=?
                   WHERE request_id=? AND allowance_consumed=0""",
                (str(status or "").strip()[:200], now, now, request_id),
            )
        return cursor.rowcount == 1

    def fail_free_search(self, request_id: str, category: str) -> bool:
        now = int(time.time())
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE free_searches SET completion_status='failed', allowance_consumed=0,
                   failure_category=?, updated_at=? WHERE request_id=? AND allowance_consumed=0""",
                (str(category or "search_error").strip()[:100], now, request_id),
            )
        return cursor.rowcount == 1

    def record_event(
        self,
        event_name: str,
        event_id: str,
        *,
        session_id: str = "",
        request_id: str = "",
        state: str = "",
        status: str = "",
        error_category: str = "",
        attribution: object = None,
        revenue_cents: int = 0,
    ) -> bool:
        if event_name not in FUNNEL_EVENTS:
            raise ValueError("Unsupported funnel event")
        safe_event_id = str(event_id or "").strip()[:160]
        if not safe_event_id:
            raise ValueError("event_id is required")
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO funnel_events
                   (event_id, event_name, occurred_at, session_id, request_id, state, status,
                    error_category, revenue_cents, attribution_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    safe_event_id,
                    event_name,
                    int(time.time()),
                    str(session_id or "")[:160],
                    str(request_id or "")[:160],
                    str(state or "").strip().upper()[:2],
                    str(status or "").strip()[:200],
                    str(error_category or "").strip()[:100],
                    max(0, int(revenue_cents or 0)),
                    json.dumps(clean_attribution(attribution), sort_keys=True),
                ),
            )
        return cursor.rowcount == 1

    def report(self, start_epoch: int, end_epoch: int) -> dict:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT event_name, COUNT(*) AS count, SUM(revenue_cents) AS revenue_cents
                   FROM funnel_events WHERE occurred_at >= ? AND occurred_at < ? GROUP BY event_name""",
                (int(start_epoch), int(end_epoch)),
            ).fetchall()
            sources = connection.execute(
                """SELECT json_extract(attribution_json, '$.utm_source') AS source,
                          json_extract(attribution_json, '$.utm_campaign') AS campaign,
                          COUNT(*) AS count
                   FROM funnel_events WHERE occurred_at >= ? AND occurred_at < ?
                   GROUP BY source, campaign ORDER BY count DESC LIMIT 100""",
                (int(start_epoch), int(end_epoch)),
            ).fetchall()
        counts = {name: 0 for name in FUNNEL_EVENTS}
        revenue_cents = 0
        for row in rows:
            counts[row["event_name"]] = int(row["count"] or 0)
            if row["event_name"] == "purchase_completed":
                revenue_cents = int(row["revenue_cents"] or 0)
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "start_epoch": int(start_epoch),
            "end_epoch": int(end_epoch),
            "events": counts,
            "revenue_cents": revenue_cents,
            "source_campaign_breakdown": [dict(row) for row in sources],
        }
