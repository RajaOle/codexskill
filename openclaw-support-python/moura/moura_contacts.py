#!/usr/bin/env python3
"""
moura_contacts.py - non-sensitive contact ledger for Moura Alexandra.

This is a narrow coordination store for CS/sales context. It is not a raw chat
history export and must not store secrets, account numbers, OTPs, passwords, IDs,
or private medical details.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HOME = Path("/home/olekamole")
STATE_DIR = HOME / ".openclaw/moura-contacts"
DB_PATH = STATE_DIR / "contacts.sqlite"
OPENCLAW = "/home/olekamole/.npm-global/bin/openclaw"
ACCOUNT_ID = "moura-alexandra"
CHANNEL = "whatsapp"
ALLOWED_MEDIA_ROOTS = (
    HOME / ".openclaw/media/inbound",
    HOME / ".openclaw/media/outbound",
)

PHONE_RE = re.compile(r"^\+[1-9][0-9]{7,15}$")
MAX_SUMMARY = 320
MAX_NEXT_ACTION = 220
MAX_NAME = 120
MAX_MESSAGE = 1200
MAX_TAGS = 10

AUTHORIZED_DIRECTORS = {
    "+685643497070": "Ibnu",
    "+6285643497070": "Ibnu",
    "+6281231152992": "Apin",
    "+62895379652424": "Apin",
}

TOPICS = {
    "general",
    "cs",
    "sales",
    "lead",
    "order",
    "complaint",
    "reseller",
    "campaign",
    "wellness",
    "other",
}

STAGES = {
    "new",
    "in_progress",
    "waiting_customer",
    "needs_followup",
    "escalated",
    "done",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def text_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def normalize_phone(value: str) -> str:
    phone = str(value or "").strip()
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if not phone.startswith("+") and phone.isdigit():
        phone = "+" + phone
    if not PHONE_RE.match(phone):
        raise ValueError("invalid phone format")
    return phone


def validate_director(phone: str) -> str:
    normalized = normalize_phone(phone)
    name = AUTHORIZED_DIRECTORS.get(normalized)
    if not name:
        raise PermissionError("requester is not an authorized Mouru business director")
    return name


def clean_text(value: Any, max_len: int, required: bool = False) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if required and not text:
        raise ValueError("required text field is empty")
    if len(text) > max_len:
        text = text[:max_len]
    return text


def normalize_topic(value: Any) -> str:
    topic = str(value or "general").strip().lower()
    return topic if topic in TOPICS else "other"


def normalize_stage(value: Any) -> str:
    stage = str(value or "in_progress").strip().lower()
    if stage not in STAGES:
        raise ValueError("stage is not allowed")
    return stage


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


def mask_phone(phone: str) -> str:
    if len(phone) <= 6:
        return "***"
    return f"{phone[:4]}***{phone[-3:]}"


def safe_media_path(value: Any) -> str:
    raw = clean_text(value, 500)
    if not raw:
        return ""
    media_path = Path(raw).expanduser().resolve()
    allowed_roots = [root.resolve() for root in ALLOWED_MEDIA_ROOTS]
    if not any(media_path == root or root in media_path.parents for root in allowed_roots):
        raise PermissionError("media path is outside approved Moura media directories")
    if not media_path.is_file():
        raise FileNotFoundError("media path does not exist")
    return str(media_path)


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
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            channel TEXT NOT NULL,
            chat_kind TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            contact_phone TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            topic TEXT NOT NULL DEFAULT 'general',
            stage TEXT NOT NULL DEFAULT 'in_progress',
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
        CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_channel_phone
        ON contacts(channel, contact_phone)
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_contacts_stage_updated ON contacts(stage, updated_at)"
    )
    conn.commit()


def record_contact(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    contact_phone = normalize_phone(str(payload.get("contact_phone", payload.get("requester_phone", ""))))
    channel = clean_text(payload.get("channel", "whatsapp"), 40) or "whatsapp"
    chat_kind = clean_text(payload.get("chat_kind", "direct"), 20) or "direct"
    if chat_kind not in {"direct", "group"}:
        raise ValueError("chat_kind must be direct or group")
    chat_id = clean_text(payload.get("chat_id", contact_phone), 120) or contact_phone
    display_name = clean_text(payload.get("display_name", ""), MAX_NAME)
    topic = normalize_topic(payload.get("topic"))
    stage = normalize_stage(payload.get("stage"))
    summary = clean_text(payload.get("summary", ""), MAX_SUMMARY, required=True)
    next_action = clean_text(payload.get("next_action", ""), MAX_NEXT_ACTION)
    tags = normalize_tags(payload.get("tags", []))
    now = utc_iso(utc_now())

    cursor = conn.execute(
        """
        INSERT INTO contacts (
            created_at, updated_at, channel, chat_kind, chat_id, contact_phone,
            display_name, topic, stage, summary, next_action, tags, last_message_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(channel, contact_phone)
        DO UPDATE SET
            updated_at = excluded.updated_at,
            chat_kind = excluded.chat_kind,
            chat_id = excluded.chat_id,
            display_name = CASE WHEN excluded.display_name != '' THEN excluded.display_name ELSE contacts.display_name END,
            topic = excluded.topic,
            stage = excluded.stage,
            summary = excluded.summary,
            next_action = excluded.next_action,
            tags = excluded.tags,
            last_message_at = excluded.last_message_at,
            interaction_count = contacts.interaction_count + 1
        """,
        (
            now,
            now,
            channel,
            chat_kind,
            chat_id,
            contact_phone,
            display_name,
            topic,
            stage,
            summary,
            next_action,
            tags,
            now,
        ),
    )
    conn.commit()
    return {
        "ok": True,
        "contact_id": int(cursor.lastrowid or 0),
        "contact_phone_masked": mask_phone(contact_phone),
        "topic": topic,
        "stage": stage,
    }


def row_to_public(row: sqlite3.Row, reveal_phone: bool = False) -> dict[str, Any]:
    phone = str(row["contact_phone"])
    return {
        "updated_at": str(row["updated_at"]),
        "channel": str(row["channel"]),
        "chat_kind": str(row["chat_kind"]),
        "contact_phone": phone if reveal_phone else mask_phone(phone),
        "display_name": str(row["display_name"] or ""),
        "topic": str(row["topic"] or ""),
        "stage": str(row["stage"] or ""),
        "summary": str(row["summary"] or ""),
        "next_action": str(row["next_action"] or ""),
        "tags": json.loads(str(row["tags"] or "[]")),
        "last_message_at": str(row["last_message_at"]),
        "interaction_count": int(row["interaction_count"] or 0),
    }


def list_contacts(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    requester_name = validate_director(str(payload.get("requester_phone", "")))
    topic = str(payload.get("topic", "") or "").strip().lower()
    stage = str(payload.get("stage", "") or "").strip().lower()
    limit = max(1, min(int(payload.get("limit", 20) or 20), 100))
    reveal_phone = bool(payload.get("reveal_phone", False))

    clauses: list[str] = []
    params: list[Any] = []
    if topic:
        if topic not in TOPICS:
            raise ValueError("topic is not allowed")
        clauses.append("topic = ?")
        params.append(topic)
    if stage:
        if stage not in STAGES:
            raise ValueError("stage is not allowed")
        clauses.append("stage = ?")
        params.append(stage)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM contacts {where} ORDER BY updated_at DESC, id DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return {
        "ok": True,
        "requested_by": requester_name,
        "count": len(rows),
        "contacts": [row_to_public(row, reveal_phone=reveal_phone) for row in rows],
    }


def send_contact_message(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    requester_name = validate_director(str(payload.get("requester_phone", "")))
    target_phone = normalize_phone(str(payload.get("target_phone", "")))
    message = clean_text(payload.get("message", ""), MAX_MESSAGE)
    media_path = safe_media_path(payload.get("media_path", ""))
    force_document = bool(payload.get("force_document", False))

    if not message and not media_path:
        raise ValueError("message or media_path is required")

    cmd = [
        OPENCLAW,
        "message",
        "send",
        "--channel",
        CHANNEL,
        "--account",
        ACCOUNT_ID,
        "--target",
        target_phone,
        "--json",
    ]
    if message:
        cmd.extend(["--message", message])
    if media_path:
        cmd.extend(["--media", media_path])
        if force_document:
            cmd.append("--force-document")

    completed = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=45,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "message send failed").strip()
        raise RuntimeError(detail[:400])

    summary = clean_text(
        payload.get("summary", f"Director {requester_name} asked Moura to send an outbound coordination message."),
        MAX_SUMMARY,
        required=True,
    )
    record_contact(
        conn,
        {
            "contact_phone": target_phone,
            "channel": CHANNEL,
            "chat_kind": "direct",
            "chat_id": target_phone,
            "display_name": payload.get("display_name", ""),
            "topic": payload.get("topic", "cs"),
            "stage": payload.get("stage", "in_progress"),
            "summary": summary,
            "next_action": payload.get("next_action", ""),
            "tags": payload.get("tags", ["outbound"]),
        },
    )

    response: dict[str, Any]
    try:
        response = json.loads(completed.stdout.strip() or "{}")
    except json.JSONDecodeError:
        response = {"raw": completed.stdout.strip()[:400]}
    return {
        "ok": True,
        "requested_by": requester_name,
        "target_phone_masked": mask_phone(target_phone),
        "has_message": bool(message),
        "has_media": bool(media_path),
        "provider_result": response,
    }


def load_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.payload_b64:
        raw = base64.b64decode(args.payload_b64.encode("utf-8")).decode("utf-8")
        payload = json.loads(raw)
    elif args.payload:
        payload = json.loads(args.payload)
    else:
        raise ValueError("payload is required")
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    return payload


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record-json", help="Record/update one non-sensitive contact")
    record.add_argument("--payload")
    record.add_argument("--payload-b64")

    list_cmd = sub.add_parser("list-json", help="List contacts for verified directors")
    list_cmd.add_argument("--payload")
    list_cmd.add_argument("--payload-b64")

    send_cmd = sub.add_parser("send-json", help="Send one director-authorized WhatsApp message/media")
    send_cmd.add_argument("--payload")
    send_cmd.add_argument("--payload-b64")

    args = parser.parse_args()
    try:
        with connect() as conn:
            init_db(conn)
            payload = load_payload(args)
            if args.command == "record-json":
                result = record_contact(conn, payload)
            elif args.command == "list-json":
                result = list_contacts(conn, payload)
            elif args.command == "send-json":
                result = send_contact_message(conn, payload)
            else:
                raise ValueError("unknown command")
        print(text_result(result))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
