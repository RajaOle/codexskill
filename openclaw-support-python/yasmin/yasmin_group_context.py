#!/usr/bin/env python3
"""
yasmin_group_context.py - local group-context summarizer for Yasmin ZahiraWedding.

The script reads Yasmin's existing OpenClaw WhatsApp group session files, strips
runtime metadata/tool/thinking records, produces compact operational summaries,
and caches the result in SQLite. It does not send messages and does not expose
arbitrary session history.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


HOME = Path("/home/olekamole")
SESSIONS_INDEX = Path(
    os.environ.get(
        "YASMIN_GROUP_CONTEXT_SESSIONS_INDEX",
        HOME / ".openclaw/agents/yasmin-zahirawedding/sessions/sessions.json",
    )
)
STATE_DIR = Path(os.environ.get("YASMIN_GROUP_CONTEXT_STATE_DIR", HOME / ".openclaw/yasmin-group-context"))
DB_PATH = Path(os.environ.get("YASMIN_GROUP_CONTEXT_DB", STATE_DIR / "group-context.sqlite"))
INTERNAL_TEAM_CONTACTS = HOME / ".openclaw/workspace-yasmin-zahirawedding/knowledge/INTERNAL_TEAM_CONTACTS.md"
ESCALATION_CONTACTS = HOME / ".openclaw/workspace-yasmin-zahirawedding/knowledge/ESCALATION_CONTACTS.md"

TZ = ZoneInfo("Asia/Jakarta")
AGENT_ID = "yasmin-zahirawedding"
GROUP_RE = re.compile(r"^[0-9]+(?:-[0-9]+)?@g\.us$")
PHONE_RE = re.compile(r"\+[1-9][0-9]{7,15}")
INDO_PHONE_RE = re.compile(r"(?<!\d)(?:\+?62|0)8[0-9\-\s]{7,18}(?!\d)")
METADATA_BLOCK_RE = re.compile(
    r"(Conversation info|Sender|Reply target of current user message) \(untrusted[^)]*\):\s*```json\s*(.*?)```",
    re.DOTALL,
)
PRIVATE_ASSISTANT_TEXT_RE = re.compile(
    r"^\s*(NO_REPLY|TOOL_OK|TOOL_FAIL|Menunggu\b|No further instruction\b|Waiting\b|Aku tunggu\b|\[assistant turn failed\b)",
    re.IGNORECASE,
)
INTERNAL_WORD_RE = re.compile(
    r"\b(?:system prompt|developer|tool|watchdog|openclaw|traceback|api key|credential|token|sqlite|database)\b",
    re.IGNORECASE,
)

TOPIC_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("jadwal/crew", re.compile(r"\b(jadwal|kru|crew|rundown|standby|briefing|shift)\b", re.IGNORECASE)),
    ("arrival/location", re.compile(r"\b(otw|sampai|sampe|lokasi|shareloc|gedung|venue|parkir|alamat)\b", re.IGNORECASE)),
    ("package/pricing", re.compile(r"\b(paket|pricelist|harga|juta|budget|dp|invoice|bayar|payment|pelunasan)\b", re.IGNORECASE)),
    ("vendor/venue", re.compile(r"\b(vendor|dekor|decor|venue|hotel|gedung|catering|mua|foto|video)\b", re.IGNORECASE)),
    ("appointment", re.compile(r"\b(meeting|appointment|survey|ketemu|janji|call|zoom|kunjungan)\b", re.IGNORECASE)),
    ("confirmation", re.compile(r"\b(confirm|konfirmasi|fix|acc|approve|oke|ok|setuju|deal)\b", re.IGNORECASE)),
    ("issue/risk", re.compile(r"\b(masalah|urgent|telat|salah|belum|komplain|refund|cancel|batal|kendala)\b", re.IGNORECASE)),
]
REQUEST_RE = re.compile(r"\b(minta|tolong|bantu|cek|carikan|follow\s*up|konfirmasi|jadwal|bisa|apa|gimana|kapan|dimana)\b|\?", re.IGNORECASE)


@dataclass
class CleanMessage:
    event_id: str
    role: str
    timestamp_ms: int
    sender_id: str
    sender_name: str
    text: str


def utc_iso(value: datetime | None = None) -> str:
    dt = value or datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ms_to_iso(ms: int) -> str:
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(TZ).isoformat(timespec="seconds")


def normalize_phone(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+") and digits:
        return f"+{digits}"
    if digits.startswith("0"):
        return f"+62{digits[1:]}"
    if digits.startswith("62"):
        return f"+{digits}"
    return raw


def mask_phone(value: str) -> str:
    phone = normalize_phone(value)
    if not PHONE_RE.fullmatch(phone):
        return value
    return f"{phone[:5]}…{phone[-3:]}"


def mask_text(text: str) -> str:
    text = PHONE_RE.sub(lambda m: mask_phone(m.group(0)), text)
    text = INDO_PHONE_RE.sub(lambda m: mask_phone(m.group(0)), text)
    return text


def stable_hash(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:16]


def load_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def load_internal_contacts() -> dict[str, str]:
    contacts: dict[str, str] = {}
    for path in (INTERNAL_TEAM_CONTACTS, ESCALATION_CONTACTS):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if not line.strip().startswith("|"):
                continue
            parts = [part.strip() for part in line.strip().strip("|").split("|")]
            if len(parts) < 2 or set(parts[0]) <= {"-"}:
                continue
            name = parts[0]
            for part in parts[1:]:
                phone = normalize_phone(part)
                if PHONE_RE.fullmatch(phone):
                    contacts[phone] = name
    return contacts


def authorize(requester_phone: str) -> dict[str, Any]:
    phone = normalize_phone(requester_phone)
    contacts = load_internal_contacts()
    if phone not in contacts:
        raise ValueError("requester_phone is not a verified Zahira internal contact")
    return {"phone": phone, "name": contacts[phone]}


def connect() -> sqlite3.Connection:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS group_summaries (
            group_id TEXT PRIMARY KEY,
            session_key TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            last_message_at TEXT NOT NULL DEFAULT '',
            last_event_id TEXT NOT NULL DEFAULT '',
            summary_json TEXT NOT NULL,
            requester_hash TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_group_summaries_updated ON group_summaries(updated_at)")
    conn.commit()
    return conn


def parse_metadata(text: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for label, raw_json in METADATA_BLOCK_RE.findall(text):
        key = label.lower().replace(" ", "_")
        try:
            parsed[key] = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
    return parsed


def strip_metadata(text: str) -> str:
    text = METADATA_BLOCK_RE.sub("", text)
    text = re.sub(r"\[media attached:[^\]]+\]", "[media attached]", text)
    text = re.sub(r"\[Replying to .*?\].*?\[/Replying\]", "[reply context omitted]", text, flags=re.DOTALL)
    text = re.sub(r"\nDescription:\n.*", "\n[media description omitted]", text, flags=re.DOTALL)
    text = re.sub(r"\nUser text:\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return mask_text(text).strip()


def content_text(event: dict[str, Any]) -> str:
    message = event.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            chunks.append(str(item.get("text") or ""))
    return "\n".join(chunks).strip()


def event_ms(event: dict[str, Any]) -> int:
    message = event.get("message")
    if isinstance(message, dict):
        try:
            timestamp = int(message.get("timestamp") or 0)
            if timestamp > 0:
                return timestamp
        except (TypeError, ValueError):
            pass
    raw = str(event.get("timestamp") or "")
    if raw:
        try:
            return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp() * 1000)
        except ValueError:
            return 0
    return 0


def visible_role(event: dict[str, Any]) -> str:
    message = event.get("message")
    if not isinstance(message, dict):
        return ""
    role = str(message.get("role") or "")
    if role not in {"user", "assistant"}:
        return ""
    return role


def clean_event(event: dict[str, Any]) -> CleanMessage | None:
    role = visible_role(event)
    if not role:
        return None
    raw_text = content_text(event)
    if not raw_text:
        return None
    if role == "assistant" and PRIVATE_ASSISTANT_TEXT_RE.search(raw_text):
        return None
    text = strip_metadata(raw_text)
    if not text or INTERNAL_WORD_RE.search(text):
        return None
    metadata = parse_metadata(raw_text)
    conversation = metadata.get("conversation_info", {})
    sender = metadata.get("sender", {})
    sender_id = ""
    sender_name = ""
    if isinstance(conversation, dict):
        sender_id = normalize_phone(str(conversation.get("sender_id") or ""))
        sender_name = str(conversation.get("sender") or "")
    if isinstance(sender, dict):
        sender_id = normalize_phone(str(sender.get("e164") or sender.get("id") or sender_id))
        sender_name = str(sender.get("name") or sender_name)
    if role == "assistant":
        sender_name = "Yasmin"
    return CleanMessage(
        event_id=str(event.get("id") or ""),
        role=role,
        timestamp_ms=event_ms(event),
        sender_id=sender_id,
        sender_name=sender_name.strip() or ("Sender" if role == "user" else "Yasmin"),
        text=text,
    )


def read_messages(path: Path, max_lines: int) -> list[CleanMessage]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    messages: list[CleanMessage] = []
    for line in lines[-max(20, max_lines):]:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "message":
            continue
        clean = clean_event(event)
        if clean:
            messages.append(clean)
    return messages


def group_id_from_key(session_key: str, data: dict[str, Any]) -> str:
    for key in ("groupId", "lastTo"):
        value = str(data.get(key) or "")
        if GROUP_RE.fullmatch(value):
            return value
    for path_key in (("origin", "to"), ("route", "target", "to"), ("deliveryContext", "to")):
        value: Any = data
        for part in path_key:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(part)
        if isinstance(value, str) and GROUP_RE.fullmatch(value):
            return value
    match = re.search(r"group:([^:]+@g\.us)", session_key)
    return match.group(1) if match else ""


def load_group_entries(query: str = "", include_empty: bool = False) -> list[dict[str, Any]]:
    index = load_json(SESSIONS_INDEX, {})
    if not isinstance(index, dict):
        return []
    rows: list[dict[str, Any]] = []
    query_l = query.lower().strip()
    seen: set[tuple[str, str]] = set()
    for session_key, data in index.items():
        if not isinstance(data, dict):
            continue
        if not session_key.startswith(f"agent:{AGENT_ID}:whatsapp:group:"):
            continue
        group_id = group_id_from_key(session_key, data)
        if not group_id:
            continue
        session_file_raw = str(data.get("sessionFile") or "")
        session_file = Path(session_file_raw) if session_file_raw else None
        has_file = bool(session_file and session_file.exists())
        if not has_file and not include_empty:
            continue
        display_name = str(data.get("displayName") or data.get("subject") or group_id)
        haystack = f"{group_id} {display_name} {session_key}".lower()
        if query_l and query_l not in haystack:
            continue
        key = (group_id, session_file_raw or session_key)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "group_id": group_id,
                "display_name": display_name,
                "session_key": session_key,
                "session_file": session_file_raw,
                "has_session_file": has_file,
                "updated_at": str(data.get("updatedAt") or data.get("lastInteractionAt") or ""),
            }
        )
    rows.sort(key=lambda row: row["updated_at"], reverse=True)
    return rows


def compact_text(text: str, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].strip() + "…"


def summarize_messages(group: dict[str, Any], messages: list[CleanMessage], include_snippets: bool) -> dict[str, Any]:
    user_messages = [msg for msg in messages if msg.role == "user"]
    assistant_messages = [msg for msg in messages if msg.role == "assistant"]
    participants = Counter()
    participant_phones: dict[str, str] = {}
    topic_counts: Counter[str] = Counter()
    requests: list[dict[str, str]] = []
    action_candidates: list[dict[str, str]] = []
    media_count = 0

    for msg in user_messages:
        label = msg.sender_name or mask_phone(msg.sender_id) or "Sender"
        participants[label] += 1
        if msg.sender_id:
            participant_phones[label] = mask_phone(msg.sender_id)
        if "[media attached]" in msg.text or "[media description omitted]" in msg.text:
            media_count += 1
        for topic, pattern in TOPIC_RULES:
            if pattern.search(msg.text):
                topic_counts[topic] += 1
        if REQUEST_RE.search(msg.text):
            item = {
                "at": ms_to_iso(msg.timestamp_ms),
                "from": label,
                "brief": compact_text(msg.text, 180),
            }
            requests.append(item)
            if len(action_candidates) < 8:
                action_candidates.append(item)

    latest = messages[-1] if messages else None
    first = messages[0] if messages else None
    top_topics = [topic for topic, _count in topic_counts.most_common(6)]
    if not top_topics:
        top_topics = ["general coordination"] if user_messages else []

    summary_lines: list[str] = []
    if top_topics:
        summary_lines.append(f"Topik utama: {', '.join(top_topics)}.")
    if action_candidates:
        summary_lines.append(f"Ada {len(action_candidates)} permintaan/aksi terdeteksi dalam konteks terakhir.")
    if media_count:
        summary_lines.append(f"Ada {media_count} pesan media/attachment dalam konteks yang dibaca.")
    if latest:
        summary_lines.append(f"Pesan terakhir berasal dari {latest.sender_name} pada {ms_to_iso(latest.timestamp_ms)}.")
    if not summary_lines:
        summary_lines.append("Belum ada konteks grup yang cukup untuk diringkas.")

    result: dict[str, Any] = {
        "ok": True,
        "group_id": group["group_id"],
        "display_name": group["display_name"],
        "session_key": group["session_key"],
        "timeframe": {
            "first_message_at": ms_to_iso(first.timestamp_ms) if first else "",
            "last_message_at": ms_to_iso(latest.timestamp_ms) if latest else "",
        },
        "counts": {
            "messages_used": len(messages),
            "user_messages": len(user_messages),
            "yasmin_messages": len(assistant_messages),
            "media_messages": media_count,
        },
        "participants": [
            {
                "name": name,
                "phone_masked": participant_phones.get(name, ""),
                "messages": count,
            }
            for name, count in participants.most_common(12)
        ],
        "topics": [{"topic": topic, "signals": count} for topic, count in topic_counts.most_common(8)],
        "summary": " ".join(summary_lines),
        "open_requests": requests[-8:],
        "suggested_next_actions": action_candidates[:8],
        "last_event_id": latest.event_id if latest else "",
        "last_message_at": ms_to_iso(latest.timestamp_ms) if latest else "",
    }
    if include_snippets:
        result["brief_snippets"] = [
            {
                "at": ms_to_iso(msg.timestamp_ms),
                "from": msg.sender_name,
                "role": msg.role,
                "brief": compact_text(msg.text, 160),
            }
            for msg in messages[-10:]
        ]
    return result


def save_summary(conn: sqlite3.Connection, summary: dict[str, Any], requester_phone: str) -> None:
    now = utc_iso()
    existing = conn.execute("SELECT created_at FROM group_summaries WHERE group_id = ?", (summary["group_id"],)).fetchone()
    conn.execute(
        """
        INSERT INTO group_summaries (
            group_id, session_key, display_name, last_message_at, last_event_id,
            summary_json, requester_hash, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(group_id) DO UPDATE SET
            session_key = excluded.session_key,
            display_name = excluded.display_name,
            last_message_at = excluded.last_message_at,
            last_event_id = excluded.last_event_id,
            summary_json = excluded.summary_json,
            requester_hash = excluded.requester_hash,
            updated_at = excluded.updated_at
        """,
        (
            summary["group_id"],
            summary["session_key"],
            summary["display_name"],
            summary["last_message_at"],
            summary["last_event_id"],
            json.dumps(summary, ensure_ascii=False, separators=(",", ":")),
            stable_hash(requester_phone),
            existing["created_at"] if existing else now,
            now,
        ),
    )
    conn.commit()


def list_groups(payload: dict[str, Any]) -> dict[str, Any]:
    auth = authorize(str(payload.get("requester_phone") or ""))
    query = str(payload.get("query") or "")
    limit = max(1, min(int(payload.get("limit") or 25), 100))
    include_empty = bool(payload.get("include_empty"))
    rows = load_group_entries(query=query, include_empty=include_empty)[:limit]
    return {
        "ok": True,
        "requester": auth["name"],
        "count": len(rows),
        "groups": [
            {
                "group_id": row["group_id"],
                "display_name": row["display_name"],
                "has_session_file": row["has_session_file"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ],
    }


def summarize_group(payload: dict[str, Any]) -> dict[str, Any]:
    auth = authorize(str(payload.get("requester_phone") or ""))
    group_id = str(payload.get("group_id") or "").strip()
    query = str(payload.get("query") or "").strip()
    include_snippets = bool(payload.get("include_snippets"))
    max_messages = max(20, min(int(payload.get("max_messages") or 120), 400))
    groups = load_group_entries(query=group_id or query, include_empty=False)
    if group_id:
        groups = [row for row in groups if row["group_id"] == group_id]
    if not groups:
        raise ValueError("matching Yasmin group session was not found")
    if len({row["group_id"] for row in groups}) > 1 and not group_id:
        return {
            "ok": False,
            "error": "query matched multiple groups; provide group_id",
            "matches": [
                {
                    "group_id": row["group_id"],
                    "display_name": row["display_name"],
                    "updated_at": row["updated_at"],
                }
                for row in groups[:10]
            ],
        }
    group = groups[0]
    session_file = Path(group["session_file"])
    messages = read_messages(session_file, max_lines=max_messages)
    summary = summarize_messages(group, messages, include_snippets=include_snippets)
    summary["requester"] = auth["name"]
    with connect() as conn:
        save_summary(conn, summary, auth["phone"])
    return summary


def cached_summaries(payload: dict[str, Any]) -> dict[str, Any]:
    auth = authorize(str(payload.get("requester_phone") or ""))
    query = str(payload.get("query") or "").lower().strip()
    limit = max(1, min(int(payload.get("limit") or 25), 100))
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT group_id, display_name, last_message_at, last_event_id, summary_json, updated_at
            FROM group_summaries
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit * 3,),
        ).fetchall()
    summaries: list[dict[str, Any]] = []
    for row in rows:
        try:
            summary = json.loads(row["summary_json"])
        except json.JSONDecodeError:
            continue
        haystack = f"{row['group_id']} {row['display_name']} {summary.get('summary', '')}".lower()
        if query and query not in haystack:
            continue
        summaries.append(
            {
                "group_id": row["group_id"],
                "display_name": row["display_name"],
                "last_message_at": row["last_message_at"],
                "last_event_id": row["last_event_id"],
                "summary": summary.get("summary", ""),
                "topics": summary.get("topics", []),
                "updated_at": row["updated_at"],
            }
        )
        if len(summaries) >= limit:
            break
    return {"ok": True, "requester": auth["name"], "count": len(summaries), "summaries": summaries}


def decode_payload(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    decoded = base64.b64decode(raw).decode("utf-8")
    parsed = json.loads(decoded)
    if not isinstance(parsed, dict):
        raise ValueError("payload must be a JSON object")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["list-groups-json", "summarize-json", "cached-json"])
    parser.add_argument("--payload-b64", default="")
    args = parser.parse_args()
    try:
        payload = decode_payload(args.payload_b64)
        if args.command == "list-groups-json":
            result = list_groups(payload)
        elif args.command == "summarize-json":
            result = summarize_group(payload)
        elif args.command == "cached-json":
            result = cached_summaries(payload)
        else:
            raise ValueError(f"unknown command: {args.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
