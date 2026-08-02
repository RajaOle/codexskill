#!/usr/bin/env python3
"""
davina_leads.py - non-sensitive local lead ledger for Davina HeloWedding.

This is a lightweight CRM store for Wedding Organizer customer-service
continuity. It must not store raw transcripts, secrets, OTPs, passwords, full
payment credentials, government IDs, ID photos, or unnecessary private details.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HOME = Path("/home/olekamole")
WORKSPACE = HOME / ".openclaw/workspace-davina-helowedding"
INTERNAL_TEAM_CONTACTS = WORKSPACE / "knowledge/INTERNAL_TEAM_CONTACTS.md"
ESCALATION_CONTACTS = WORKSPACE / "knowledge/ESCALATION_CONTACTS.md"
STATE_DIR = Path(os.environ.get("DAVINA_LEADS_STATE_DIR", str(HOME / ".openclaw/davina-leads")))
DB_PATH = STATE_DIR / "leads.sqlite"

PHONE_RE = re.compile(r"^\+[1-9][0-9]{7,15}$")
E164_RE = re.compile(r"\+[1-9][0-9]{7,15}")
MAX_NAME = 120
MAX_SHORT = 160
MAX_SUMMARY = 420
MAX_NEXT_ACTION = 260
MAX_TAGS = 12

LEAD_STAGES = {
    "new",
    "qualified",
    "package_interest",
    "appointment_requested",
    "awaiting_team",
    "follow_up_consented",
    "follow_up_declined",
    "vendor_proposal",
    "complaint",
    "closed",
    "other",
}

SERVICE_INTERESTS = {
    "unknown",
    "wedding_planner",
    "all_in_package",
    "wo_day",
    "custom",
    "vendor_or_partner",
    "complaint",
    "other",
}

VENUE_STATUSES = {
    "unknown",
    "not_selected",
    "shortlisted",
    "selected",
    "booked",
}

FOLLOW_UP_CONSENTS = {
    "unknown",
    "granted",
    "declined",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def text_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def normalize_phone(value: Any) -> str:
    phone = str(value or "").strip()
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if phone.startswith("62") and phone.isdigit():
        phone = f"+{phone}"
    if phone.startswith("0") and phone[1:].isdigit():
        phone = f"+62{phone[1:]}"
    if not phone.startswith("+") and phone.isdigit():
        phone = f"+{phone}"
    if not PHONE_RE.match(phone):
        raise ValueError("invalid phone format")
    return phone


def mask_phone(phone: str) -> str:
    if len(phone) <= 7:
        return "***"
    return f"{phone[:4]}***{phone[-3:]}"


def clean_text(value: Any, max_len: int, required: bool = False) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if required and not text:
        raise ValueError("required text field is empty")
    if len(text) > max_len:
        text = text[:max_len]
    return text


def clean_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("guest_estimate must be an integer") from exc
    if number < 0 or number > 100000:
        raise ValueError("guest_estimate is outside allowed range")
    return number


def normalize_enum(value: Any, allowed: set[str], default: str, field_name: str) -> str:
    normalized = str(value or default).strip().lower()
    if normalized not in allowed:
        raise ValueError(f"{field_name} is not allowed")
    return normalized


def normalize_tags(value: Any) -> str:
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        raw_items = [str(item).strip() for item in value]
    else:
        raw_items = []

    tags: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        tag = re.sub(r"[^a-zA-Z0-9_.-]", "", raw.lower())[:32]
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
        if len(tags) >= MAX_TAGS:
            break
    return json.dumps(tags, ensure_ascii=False)


def read_text_safely(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def load_authorized_requesters() -> dict[str, str]:
    contacts: dict[str, str] = {}

    for line in read_text_safely(INTERNAL_TEAM_CONTACTS).splitlines():
        if not line.strip().startswith("|") or "normalized_e164" in line or "---" in line:
            continue
        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(parts) < 2:
            continue
        name, phone = parts[0], parts[1]
        if PHONE_RE.match(phone):
            contacts[phone] = name or "Internal Team"

    escalation_text = read_text_safely(ESCALATION_CONTACTS)
    fifi_match = re.search(r"Internal WhatsApp:\s*(\+[1-9][0-9]{7,15})", escalation_text)
    if fifi_match:
        contacts[fifi_match.group(1)] = "Fifi"

    return contacts


def validate_requester(phone: Any) -> str:
    normalized = normalize_phone(phone)
    requester = load_authorized_requesters().get(normalized)
    if not requester:
        raise PermissionError("requester is not an authorized Helo Wedding internal team member")
    return requester


def connect() -> sqlite3.Connection:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(STATE_DIR, 0o700)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        os.chmod(DB_PATH, 0o600)
    except FileNotFoundError:
        pass
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'whatsapp',
            chat_kind TEXT NOT NULL DEFAULT 'direct',
            chat_id TEXT NOT NULL,
            contact_phone TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            customer_name TEXT NOT NULL DEFAULT '',
            event_date_text TEXT NOT NULL DEFAULT '',
            event_date_iso TEXT NOT NULL DEFAULT '',
            event_month TEXT NOT NULL DEFAULT '',
            venue_name TEXT NOT NULL DEFAULT '',
            venue_area TEXT NOT NULL DEFAULT '',
            venue_status TEXT NOT NULL DEFAULT 'unknown',
            guest_estimate INTEGER,
            ceremony_format TEXT NOT NULL DEFAULT '',
            service_interest TEXT NOT NULL DEFAULT 'unknown',
            package_interest TEXT NOT NULL DEFAULT '',
            budget_range TEXT NOT NULL DEFAULT '',
            lead_stage TEXT NOT NULL DEFAULT 'new',
            follow_up_consent TEXT NOT NULL DEFAULT 'unknown',
            preferred_follow_up_at TEXT NOT NULL DEFAULT '',
            owner TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            next_action TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '[]',
            last_message_at TEXT NOT NULL,
            interaction_count INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_channel_phone
        ON leads(channel, contact_phone)
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_stage_updated ON leads(lead_stage, updated_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_followup ON leads(follow_up_consent, preferred_follow_up_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_event_date ON leads(event_date_iso)")
    conn.commit()


def row_to_public(row: sqlite3.Row, reveal_phone: bool = False) -> dict[str, Any]:
    phone = str(row["contact_phone"])
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "channel": str(row["channel"]),
        "chat_kind": str(row["chat_kind"]),
        "chat_id": str(row["chat_id"]),
        "contact_phone": phone if reveal_phone else mask_phone(phone),
        "display_name": str(row["display_name"] or ""),
        "customer_name": str(row["customer_name"] or ""),
        "event_date_text": str(row["event_date_text"] or ""),
        "event_date_iso": str(row["event_date_iso"] or ""),
        "event_month": str(row["event_month"] or ""),
        "venue_name": str(row["venue_name"] or ""),
        "venue_area": str(row["venue_area"] or ""),
        "venue_status": str(row["venue_status"] or ""),
        "guest_estimate": row["guest_estimate"],
        "ceremony_format": str(row["ceremony_format"] or ""),
        "service_interest": str(row["service_interest"] or ""),
        "package_interest": str(row["package_interest"] or ""),
        "budget_range": str(row["budget_range"] or ""),
        "lead_stage": str(row["lead_stage"] or ""),
        "follow_up_consent": str(row["follow_up_consent"] or ""),
        "preferred_follow_up_at": str(row["preferred_follow_up_at"] or ""),
        "owner": str(row["owner"] or ""),
        "summary": str(row["summary"] or ""),
        "next_action": str(row["next_action"] or ""),
        "tags": json.loads(str(row["tags"] or "[]")),
        "last_message_at": str(row["last_message_at"]),
        "interaction_count": int(row["interaction_count"] or 0),
    }


def record_lead(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    contact_phone = normalize_phone(payload.get("contact_phone"))
    channel = clean_text(payload.get("channel", "whatsapp"), 40) or "whatsapp"
    chat_kind = clean_text(payload.get("chat_kind", "direct"), 20) or "direct"
    if chat_kind not in {"direct", "group"}:
        raise ValueError("chat_kind must be direct or group")
    chat_id = clean_text(payload.get("chat_id", contact_phone), 140) or contact_phone
    display_name = clean_text(payload.get("display_name", ""), MAX_NAME)
    customer_name = clean_text(payload.get("customer_name", ""), MAX_NAME)
    event_date_text = clean_text(payload.get("event_date_text", ""), MAX_SHORT)
    event_date_iso = clean_text(payload.get("event_date_iso", ""), MAX_SHORT)
    event_month = clean_text(payload.get("event_month", ""), MAX_SHORT)
    venue_name = clean_text(payload.get("venue_name", ""), MAX_SHORT)
    venue_area = clean_text(payload.get("venue_area", ""), MAX_SHORT)
    venue_status = normalize_enum(payload.get("venue_status"), VENUE_STATUSES, "unknown", "venue_status")
    guest_estimate = clean_int(payload.get("guest_estimate"))
    ceremony_format = clean_text(payload.get("ceremony_format", ""), MAX_SHORT)
    service_interest = normalize_enum(payload.get("service_interest"), SERVICE_INTERESTS, "unknown", "service_interest")
    package_interest = clean_text(payload.get("package_interest", ""), MAX_SHORT)
    budget_range = clean_text(payload.get("budget_range", ""), MAX_SHORT)
    lead_stage = normalize_enum(payload.get("lead_stage"), LEAD_STAGES, "new", "lead_stage")
    follow_up_consent = normalize_enum(
        payload.get("follow_up_consent"),
        FOLLOW_UP_CONSENTS,
        "unknown",
        "follow_up_consent",
    )
    preferred_follow_up_at = clean_text(payload.get("preferred_follow_up_at", ""), MAX_SHORT)
    owner = clean_text(payload.get("owner", ""), MAX_NAME)
    summary = clean_text(payload.get("summary", ""), MAX_SUMMARY, required=True)
    next_action = clean_text(payload.get("next_action", ""), MAX_NEXT_ACTION)
    tags = normalize_tags(payload.get("tags", []))
    now = utc_iso(utc_now())

    cursor = conn.execute(
        """
        INSERT INTO leads (
            created_at, updated_at, channel, chat_kind, chat_id, contact_phone,
            display_name, customer_name, event_date_text, event_date_iso,
            event_month, venue_name, venue_area, venue_status, guest_estimate,
            ceremony_format, service_interest, package_interest, budget_range,
            lead_stage, follow_up_consent, preferred_follow_up_at, owner,
            summary, next_action, tags, last_message_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(channel, contact_phone)
        DO UPDATE SET
            updated_at = excluded.updated_at,
            chat_kind = excluded.chat_kind,
            chat_id = excluded.chat_id,
            display_name = CASE WHEN excluded.display_name != '' THEN excluded.display_name ELSE leads.display_name END,
            customer_name = CASE WHEN excluded.customer_name != '' THEN excluded.customer_name ELSE leads.customer_name END,
            event_date_text = CASE WHEN excluded.event_date_text != '' THEN excluded.event_date_text ELSE leads.event_date_text END,
            event_date_iso = CASE WHEN excluded.event_date_iso != '' THEN excluded.event_date_iso ELSE leads.event_date_iso END,
            event_month = CASE WHEN excluded.event_month != '' THEN excluded.event_month ELSE leads.event_month END,
            venue_name = CASE WHEN excluded.venue_name != '' THEN excluded.venue_name ELSE leads.venue_name END,
            venue_area = CASE WHEN excluded.venue_area != '' THEN excluded.venue_area ELSE leads.venue_area END,
            venue_status = excluded.venue_status,
            guest_estimate = COALESCE(excluded.guest_estimate, leads.guest_estimate),
            ceremony_format = CASE WHEN excluded.ceremony_format != '' THEN excluded.ceremony_format ELSE leads.ceremony_format END,
            service_interest = excluded.service_interest,
            package_interest = CASE WHEN excluded.package_interest != '' THEN excluded.package_interest ELSE leads.package_interest END,
            budget_range = CASE WHEN excluded.budget_range != '' THEN excluded.budget_range ELSE leads.budget_range END,
            lead_stage = excluded.lead_stage,
            follow_up_consent = excluded.follow_up_consent,
            preferred_follow_up_at = CASE WHEN excluded.preferred_follow_up_at != '' THEN excluded.preferred_follow_up_at ELSE leads.preferred_follow_up_at END,
            owner = CASE WHEN excluded.owner != '' THEN excluded.owner ELSE leads.owner END,
            summary = excluded.summary,
            next_action = excluded.next_action,
            tags = excluded.tags,
            last_message_at = excluded.last_message_at,
            interaction_count = leads.interaction_count + 1
        """,
        (
            now,
            now,
            channel,
            chat_kind,
            chat_id,
            contact_phone,
            display_name,
            customer_name,
            event_date_text,
            event_date_iso,
            event_month,
            venue_name,
            venue_area,
            venue_status,
            guest_estimate,
            ceremony_format,
            service_interest,
            package_interest,
            budget_range,
            lead_stage,
            follow_up_consent,
            preferred_follow_up_at,
            owner,
            summary,
            next_action,
            tags,
            now,
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM leads WHERE channel = ? AND contact_phone = ?",
        (channel, contact_phone),
    ).fetchone()
    return {
        "ok": True,
        "lead_id": int(row["id"] if row else cursor.lastrowid or 0),
        "contact_phone_masked": mask_phone(contact_phone),
        "lead_stage": lead_stage,
        "service_interest": service_interest,
        "follow_up_consent": follow_up_consent,
        "lead": row_to_public(row) if row else None,
    }


def list_leads(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    requester_name = validate_requester(payload.get("requester_phone"))
    lead_stage = str(payload.get("lead_stage", "") or "").strip().lower()
    service_interest = str(payload.get("service_interest", "") or "").strip().lower()
    follow_up_consent = str(payload.get("follow_up_consent", "") or "").strip().lower()
    owner = clean_text(payload.get("owner", ""), MAX_NAME)
    search = clean_text(payload.get("search", ""), MAX_SHORT)
    limit = max(1, min(int(payload.get("limit", 25) or 25), 100))
    reveal_phone = bool(payload.get("reveal_phone", False))

    clauses: list[str] = []
    params: list[Any] = []
    if lead_stage:
        if lead_stage not in LEAD_STAGES:
            raise ValueError("lead_stage is not allowed")
        clauses.append("lead_stage = ?")
        params.append(lead_stage)
    if service_interest:
        if service_interest not in SERVICE_INTERESTS:
            raise ValueError("service_interest is not allowed")
        clauses.append("service_interest = ?")
        params.append(service_interest)
    if follow_up_consent:
        if follow_up_consent not in FOLLOW_UP_CONSENTS:
            raise ValueError("follow_up_consent is not allowed")
        clauses.append("follow_up_consent = ?")
        params.append(follow_up_consent)
    if owner:
        clauses.append("owner = ?")
        params.append(owner)
    if search:
        like = f"%{search}%"
        clauses.append(
            "(display_name LIKE ? OR customer_name LIKE ? OR venue_name LIKE ? OR venue_area LIKE ? OR summary LIKE ?)"
        )
        params.extend([like, like, like, like, like])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM leads {where} ORDER BY updated_at DESC, id DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return {
        "ok": True,
        "requested_by": requester_name,
        "count": len(rows),
        "leads": [row_to_public(row, reveal_phone=reveal_phone) for row in rows],
    }


def get_lead(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    requester_name = validate_requester(payload.get("requester_phone"))
    contact_phone = normalize_phone(payload.get("contact_phone"))
    channel = clean_text(payload.get("channel", "whatsapp"), 40) or "whatsapp"
    reveal_phone = bool(payload.get("reveal_phone", False))
    row = conn.execute(
        "SELECT * FROM leads WHERE channel = ? AND contact_phone = ?",
        (channel, contact_phone),
    ).fetchone()
    return {
        "ok": True,
        "requested_by": requester_name,
        "lead": row_to_public(row, reveal_phone=reveal_phone) if row else None,
    }


def health(conn: sqlite3.Connection) -> dict[str, Any]:
    count = conn.execute("SELECT COUNT(*) AS count FROM leads").fetchone()["count"]
    return {
        "ok": True,
        "db_path": str(DB_PATH),
        "lead_count": int(count),
    }


def load_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.payload_b64:
        raw = base64.b64decode(args.payload_b64.encode("utf-8")).decode("utf-8")
        payload = json.loads(raw)
    elif args.payload:
        payload = json.loads(args.payload)
    else:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    return payload


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("record-json", "Record/update one non-sensitive Davina lead"),
        ("list-json", "List Davina leads for verified Helo internal requesters"),
        ("get-json", "Get one Davina lead for verified Helo internal requesters"),
        ("health-json", "Check ledger database health"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--payload")
        command.add_argument("--payload-b64")

    args = parser.parse_args()
    try:
        with connect() as conn:
            init_db(conn)
            payload = load_payload(args)
            if args.command == "record-json":
                result = record_lead(conn, payload)
            elif args.command == "list-json":
                result = list_leads(conn, payload)
            elif args.command == "get-json":
                result = get_lead(conn, payload)
            elif args.command == "health-json":
                result = health(conn)
            else:
                raise ValueError("unknown command")
        print(text_result(result))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
