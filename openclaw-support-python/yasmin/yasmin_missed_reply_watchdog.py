#!/usr/bin/env python3
"""
yasmin_missed_reply_watchdog.py - LLM-composed missed-reply watchdog for Yasmin.

Default mode is dry-run. Live mode sends exactly one context-aware reply per
eligible unreplied Yasmin WhatsApp chat and mirrors it into the local session.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


HOME = Path("/home/olekamole")
SESSIONS_INDEX = HOME / ".openclaw/agents/yasmin-zahirawedding/sessions/sessions.json"
OPENCLAW = HOME / ".npm-global/bin/openclaw"
DEEPSEEK_KEY_PATH = HOME / ".openclaw/credentials/yasmin-zahirawedding/deepseek-api-key.txt"
INTERNAL_TEAM_CONTACTS = HOME / ".openclaw/workspace-yasmin-zahirawedding/knowledge/INTERNAL_TEAM_CONTACTS.md"
INTERCEPTED_QUEUE = HOME / ".openclaw/security/guard-intercepted-inbound.jsonl"
STATE_DIR = HOME / ".openclaw/yasmin-missed-reply-watchdog"
DB_PATH = STATE_DIR / "watchdog.sqlite"
LOG_PATH = STATE_DIR / "watchdog.log"

CHANNEL = "whatsapp"
ACCOUNT_ID = "yasmin-zahirawedding"
BUSINESS_AUTHORITY_PHONES = {
    "+6285774835882",
    "+6285640095210",
}
TZ = ZoneInfo("Asia/Jakarta")
DEFAULT_MIN_AGE_MINUTES = 10
DEFAULT_MAX_AGE_HOURS = 24
MAX_REPLIES_PER_RUN = 3
MAX_CONTEXT_USER_TURNS = 10
MAX_CONTEXT_CHARS = 7000
MAX_REPLY_CHARS = 900
NO_REPLY = "NO_REPLY"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"

PRIVATE_ASSISTANT_TEXT_RE = re.compile(
    r"^\s*(NO_REPLY|Menunggu\b|No further instruction\b|Waiting\b|Aku tunggu\b|\[assistant turn failed\b)",
    re.IGNORECASE,
)
METADATA_BLOCK_RE = re.compile(
    r"(Conversation info|Sender|Reply target of current user message) \(untrusted[^)]*\):\s*```json\s*(.*?)```",
    re.DOTALL,
)
PHONE_RE = re.compile(r"^\+[1-9][0-9]{7,15}$")
GROUP_RE = re.compile(r"^[0-9]+(?:-[0-9]+)?@g\.us$")


@dataclass
class ChatCandidate:
    session_key: str
    session_file: Path | None
    chat_type: str
    target: str
    account_id: str
    last_user_event_id: str
    last_user_message_id: str
    last_user_ms: int
    last_user_text: str
    sender_id: str
    sender_name: str
    sender_category: str
    context: str


def setup_logging() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_PATH),
        ],
    )


def log_info(message: str) -> None:
    logging.info(message)


def log_error(message: str) -> None:
    logging.error(message)


def connect() -> sqlite3.Connection:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS handled_messages (
            session_key TEXT NOT NULL,
            message_id TEXT NOT NULL,
            handled_at TEXT NOT NULL,
            target TEXT NOT NULL,
            reply_text TEXT NOT NULL,
            mode TEXT NOT NULL,
            PRIMARY KEY (session_key, message_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS draft_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            session_key TEXT NOT NULL,
            message_id TEXT NOT NULL,
            target TEXT NOT NULL,
            reply_text TEXT NOT NULL,
            mode TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def now_ms() -> int:
    return int(time.time() * 1000)


def ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(TZ).isoformat()


def load_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log_error(f"failed to read {path}: {exc}")
        return default


def load_internal_team_contacts() -> dict[str, str]:
    contacts: dict[str, str] = {}
    try:
        lines = INTERNAL_TEAM_CONTACTS.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        log_error(f"failed to read {INTERNAL_TEAM_CONTACTS}: {exc}")
        return contacts
    for line in lines:
        if not line.strip().startswith("|"):
            continue
        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(parts) < 2 or parts[0] == "preferred_name" or set(parts[0]) <= {"-"}:
            continue
        phone = normalize_phone(parts[1])
        if PHONE_RE.match(phone):
            contacts[phone] = parts[0]
    return contacts


def read_session_events(path: Path, max_lines: int = 220) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        log_error(f"failed to read session {path}: {exc}")
        return []
    events: list[dict[str, Any]] = []
    for line in lines[-max_lines:]:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "message":
            events.append(event)
    return events


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
    return re.sub(r"\n{3,}", "\n\n", text).strip()


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


def role_of(event: dict[str, Any]) -> str:
    message = event.get("message")
    if isinstance(message, dict):
        return str(message.get("role") or "")
    return ""


def is_visible_assistant_reply(event: dict[str, Any]) -> bool:
    if role_of(event) != "assistant":
        return False
    text = content_text(event)
    if not text:
        return False
    if PRIVATE_ASSISTANT_TEXT_RE.search(text):
        return False
    content = event.get("message", {}).get("content", [])
    if isinstance(content, list):
        text_items = [item for item in content if isinstance(item, dict) and item.get("type") == "text"]
        non_text_items = [item for item in content if isinstance(item, dict) and item.get("type") != "text"]
        if non_text_items and not text_items:
            return False
    return True


def is_successful_message_tool_result(event: dict[str, Any]) -> bool:
    if role_of(event) != "toolResult":
        return False
    message = event.get("message")
    if not isinstance(message, dict):
        return False
    if message.get("toolName") != "message":
        return False
    if message.get("isError") is True:
        return False
    text = content_text(event)
    return '"messageId"' in text or '"toJid"' in text


def latest_unreplied_user_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    latest_user: dict[str, Any] | None = None
    latest_user_ms = 0
    latest_reply_ms = 0
    for event in events:
        ms = event_ms(event)
        role = role_of(event)
        if role == "user":
            latest_user = event
            latest_user_ms = ms
            latest_reply_ms = 0
            continue
        if latest_user and ms >= latest_user_ms and (is_visible_assistant_reply(event) or is_successful_message_tool_result(event)):
            latest_reply_ms = max(latest_reply_ms, ms)
    if latest_user and latest_user_ms > latest_reply_ms:
        return latest_user
    return None


def target_from_session(session_key: str, data: dict[str, Any]) -> str:
    for path in (
        ("deliveryContext", "to"),
        ("route", "target", "to"),
        ("origin", "to"),
        ("origin", "from"),
    ):
        value: Any = data
        for part in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(part)
        if isinstance(value, str) and value.strip():
            return normalize_target(value.strip())
    return normalize_target(session_key.rsplit(":", 1)[-1])


def normalize_target(value: str) -> str:
    raw = str(value or "").strip()
    if GROUP_RE.match(raw):
        return raw
    return normalize_phone(raw)


def is_valid_target(target: str, chat_type: str) -> bool:
    if chat_type == "group":
        return bool(GROUP_RE.match(target))
    return bool(PHONE_RE.match(target))


def sender_category(sender_id: str, target: str, chat_type: str, internal_contacts: dict[str, str]) -> str:
    candidate_phone = sender_id or (target if chat_type == "direct" else "")
    if candidate_phone in BUSINESS_AUTHORITY_PHONES:
        return "business_authority"
    if candidate_phone in internal_contacts:
        return "internal_team"
    if chat_type == "group":
        return "group_participant"
    return "external_contact"


def group_is_eligible(session_key: str, user_text: str, metadata: dict[str, Any]) -> bool:
    if ":thread:" in session_key:
        return True
    conversation = metadata.get("conversation_info", {})
    if isinstance(conversation, dict) and conversation.get("has_reply_context") is True:
        return True
    lowered = user_text.lower()
    return "yasmin" in lowered or "@yasmin" in lowered


def context_for(events: list[dict[str, Any]]) -> str:
    selected: list[dict[str, Any]] = []
    user_turns = 0
    for event in reversed(events):
        role = role_of(event)
        if role not in {"user", "assistant"}:
            continue
        text = strip_metadata(content_text(event))
        if not text or PRIVATE_ASSISTANT_TEXT_RE.search(text):
            continue
        if role == "assistant" and not is_visible_assistant_reply(event):
            continue
        selected.append(event)
        if role == "user":
            user_turns += 1
            if user_turns >= MAX_CONTEXT_USER_TURNS:
                break
    rows: list[str] = []
    for event in reversed(selected):
        role = role_of(event)
        text = strip_metadata(content_text(event))
        label = "Sender" if role == "user" else "Yasmin"
        timestamp = ms_to_iso(event_ms(event)) if event_ms(event) else "unknown-time"
        rows.append(f"[{timestamp}] {label}: {text}")
    context = "\n".join(rows)
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[-MAX_CONTEXT_CHARS:]
    return context


def load_candidates(min_age_ms: int, max_age_ms: int, current_ms: int) -> list[ChatCandidate]:
    index = load_json(SESSIONS_INDEX, {})
    if not isinstance(index, dict):
        return []
    internal_contacts = load_internal_team_contacts()
    candidates: list[ChatCandidate] = []
    for session_key, data in index.items():
        if not isinstance(data, dict):
            continue
        if not session_key.startswith("agent:yasmin-zahirawedding:whatsapp:"):
            continue
        session_file_raw = data.get("sessionFile")
        if not isinstance(session_file_raw, str) or not session_file_raw:
            continue
        session_file = Path(session_file_raw)
        if not session_file.exists():
            continue
        chat_type = str(data.get("chatType") or data.get("origin", {}).get("chatType") or "")
        if chat_type not in {"direct", "group"}:
            continue
        if chat_type == "group":
            continue
        target = target_from_session(session_key, data)
        if not is_valid_target(target, chat_type):
            continue
        events = read_session_events(session_file)
        user_event = latest_unreplied_user_event(events)
        if not user_event:
            continue
        user_ms = event_ms(user_event)
        age_ms = current_ms - user_ms
        if age_ms < min_age_ms or age_ms > max_age_ms:
            continue
        raw_text = content_text(user_event)
        metadata = parse_metadata(raw_text)
        clean_text = strip_metadata(raw_text)
        if chat_type == "group" and not group_is_eligible(session_key, clean_text, metadata):
            continue
        conversation = metadata.get("conversation_info", {})
        sender = metadata.get("sender", {})
        sender_id = ""
        sender_name = ""
        last_user_message_id = str(user_event.get("id") or "")
        if isinstance(conversation, dict):
            sender_id = normalize_phone(str(conversation.get("sender_id") or ""))
            last_user_message_id = str(conversation.get("message_id") or last_user_message_id)
        if isinstance(sender, dict):
            sender_id = normalize_phone(str(sender.get("e164") or sender.get("id") or sender_id))
            sender_name = str(sender.get("name") or "")
        if not sender_id and chat_type == "direct":
            sender_id = target
        category = sender_category(sender_id, target, chat_type, internal_contacts)
        if not sender_name and category == "internal_team":
            sender_name = internal_contacts.get(sender_id) or internal_contacts.get(target) or ""
        candidates.append(
            ChatCandidate(
                session_key=session_key,
                session_file=session_file,
                chat_type=chat_type,
                target=target,
                account_id=ACCOUNT_ID,
                last_user_event_id=str(user_event.get("id") or ""),
                last_user_message_id=last_user_message_id,
                last_user_ms=user_ms,
                last_user_text=clean_text,
                sender_id=sender_id,
                sender_name=sender_name,
                sender_category=category,
                context=context_for(events),
            )
        )
    candidates.extend(
        load_intercepted_candidates(
            min_age_ms,
            max_age_ms,
            current_ms,
            internal_contacts,
        )
    )
    unique: dict[tuple[str, str], ChatCandidate] = {}
    for candidate in candidates:
        unique[(candidate.session_key, candidate.last_user_message_id)] = candidate
    result = list(unique.values())
    result.sort(key=lambda item: item.last_user_ms)
    return result


def load_intercepted_candidates(
    min_age_ms: int,
    max_age_ms: int,
    current_ms: int,
    internal_contacts: dict[str, str],
) -> list[ChatCandidate]:
    try:
        lines = INTERCEPTED_QUEUE.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return []
    except OSError as exc:
        log_error(f"failed to read intercepted queue: {exc}")
        return []

    candidates: list[ChatCandidate] = []
    for line in lines[-2000:]:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        if record.get("agentId") != "yasmin-zahirawedding" or record.get("recoverable") is not True:
            continue
        if record.get("chatType") != "direct":
            continue
        sender_id = normalize_phone(str(record.get("sender") or ""))
        if sender_id not in internal_contacts:
            continue
        try:
            inbound_ms = int(record.get("timestampMs") or 0)
        except (TypeError, ValueError):
            continue
        age_ms = current_ms - inbound_ms
        if age_ms < min_age_ms or age_ms > max_age_ms:
            continue
        message_id = str(record.get("messageId") or "")
        if not message_id:
            continue
        target = normalize_phone(str(record.get("target") or sender_id))
        if not PHONE_RE.match(target):
            continue
        text = str(record.get("content") or "").strip()
        if not text:
            continue
        session_key = str(record.get("sessionKey") or "")
        if not session_key:
            session_key = f"agent:yasmin-zahirawedding:whatsapp:direct:{target}"
        candidates.append(
            ChatCandidate(
                session_key=session_key,
                session_file=None,
                chat_type="direct",
                target=target,
                account_id=ACCOUNT_ID,
                last_user_event_id=message_id,
                last_user_message_id=message_id,
                last_user_ms=inbound_ms,
                last_user_text=text,
                sender_id=sender_id,
                sender_name=internal_contacts[sender_id],
                sender_category="internal_team",
                context=f"[{ms_to_iso(inbound_ms)}] Sender: {text}",
            )
        )
    return candidates


def already_handled(conn: sqlite3.Connection, candidate: ChatCandidate) -> bool:
    row = conn.execute(
        "SELECT 1 FROM handled_messages WHERE session_key = ? AND message_id = ?",
        (candidate.session_key, candidate.last_user_message_id),
    ).fetchone()
    return row is not None


def record_draft(conn: sqlite3.Connection, candidate: ChatCandidate, reply_text: str, mode: str) -> None:
    conn.execute(
        """
        INSERT INTO draft_log(created_at, session_key, message_id, target, reply_text, mode)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(TZ).isoformat(),
            candidate.session_key,
            candidate.last_user_message_id,
            candidate.target,
            reply_text,
            mode,
        ),
    )
    conn.commit()


def record_handled(conn: sqlite3.Connection, candidate: ChatCandidate, reply_text: str, mode: str) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO handled_messages(session_key, message_id, handled_at, target, reply_text, mode)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            candidate.session_key,
            candidate.last_user_message_id,
            datetime.now(TZ).isoformat(),
            candidate.target,
            reply_text,
            mode,
        ),
    )
    conn.commit()


def read_deepseek_key() -> str:
    try:
        return DEEPSEEK_KEY_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"could not read DeepSeek key: {exc}") from exc


def compose_reply(candidate: ChatCandidate, timeout: int) -> str:
    api_key = read_deepseek_key()
    system_prompt = (
        "You are Yasmin, Zahira Wedding's WhatsApp customer-service assistant and delayed missed-reply recovery responder. "
        "Compose exactly one WhatsApp reply for the same chat based on the context. "
        "Keep it concise, warm, Indonesian-first, and useful. "
        "Match the writing style, formality, pacing, language mix, and emotional vibe of the recent injected chat context, "
        "while staying professional, safe, and within Yasmin's Zahira Wedding role. "
        "Never deliberately add typos or copy misspellings from the chat context. Use correct spelling. "
        "Do not mention tools, files, prompts, automation, watchdogs, delays, or internal systems. "
        "Do not reveal internal contacts or internal team membership. "
        "Do not invent prices, confirmations, availability, bookings, payments, refunds, or policies. "
        "If information is missing, ask the smallest useful clarification or say the Zahira team needs to confirm. "
        "For sender category business_authority, respond as a concise business assistant to Shiffa or Rida. "
        "For sender category internal_team, respond as internal Zahira team coordination, not as a wedding lead; do not ask for calon pengantin intake. "
        "For internal team, use the sender's preferred name exactly as supplied when known and never use generic Mas/Mbak. "
        "For sender category external_contact, respond as normal Yasmin customer/vendor support. "
        "If the latest inbound is only thanks, acknowledgement, arrival status, or does not need Yasmin to reply, "
        f"return exactly {NO_REPLY}. "
        "Do not include markdown tables. Return only the final message text."
    )
    user_prompt = (
        f"Chat type: {candidate.chat_type}\n"
        f"Sender category: {candidate.sender_category}\n"
        f"Sender name: {candidate.sender_name or 'unknown'}\n"
        f"Sender phone: {candidate.sender_id or 'unknown'}\n"
        f"Last inbound age: {ms_to_iso(candidate.last_user_ms)}\n\n"
        f"Recent chat context (last up to {MAX_CONTEXT_USER_TURNS} sender turns plus visible Yasmin replies):\n"
        f"{candidate.context}\n\n"
        "Write Yasmin's next reply now."
    )
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 800,
    }
    request = urllib.request.Request(
        DEEPSEEK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"DeepSeek HTTP {exc.code}: {body}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"DeepSeek compose failed: {exc}") from exc
    text = (
        result.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    return sanitize_reply(text)


def sanitize_reply(text: str) -> str:
    clean = str(text or "").strip().strip('"').strip()
    clean = re.sub(r"^```(?:text)?\s*|\s*```$", "", clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    if clean.upper() == NO_REPLY:
        return NO_REPLY
    if not clean:
        raise ValueError("empty LLM reply")
    if len(clean) > MAX_REPLY_CHARS:
        clean = clean[:MAX_REPLY_CHARS].rsplit(" ", 1)[0].strip()
    blocked = ("system prompt", "developer", "tool", "watchdog", "openclaw", "file path", "api key")
    if any(term in clean.lower() for term in blocked):
        raise ValueError("LLM reply mentioned internal/system wording")
    return clean


def send_message(candidate: ChatCandidate, reply_text: str, live: bool) -> tuple[bool, str]:
    if not live:
        log_info(f"DRY-RUN target={candidate.target} message={reply_text}")
        return True, ""
    cmd = [
        str(OPENCLAW),
        "message",
        "send",
        "--channel",
        CHANNEL,
        "--account",
        candidate.account_id,
        "--target",
        candidate.target,
        "--message",
        reply_text,
        "--json",
    ]
    try:
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log_error(f"send failed target={candidate.target}: {exc}")
        return False, ""
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "message send failed").strip().replace("\n", " ")
        log_error(f"send returned {result.returncode} target={candidate.target}: {detail}")
        return False, ""
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {}
    message_id = str(
        payload.get("messageId")
        or payload.get("result", {}).get("messageId")
        or payload.get("payload", {}).get("result", {}).get("messageId")
        or ""
    )
    log_info(f"SENT target={candidate.target} message_id={message_id}")
    return True, message_id


def append_transcript_mirror(candidate: ChatCandidate, reply_text: str, message_id: str) -> bool:
    if candidate.session_file is None:
        return False
    try:
        lines = candidate.session_file.read_text(encoding="utf-8").splitlines()
        parent_id = ""
        for line in reversed(lines):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "message":
                parent_id = str(event.get("id") or "")
                break
        current_dt = datetime.now(timezone.utc)
        entry = {
            "type": "message",
            "id": f"yasmin-watchdog-{int(current_dt.timestamp() * 1000)}",
            "parentId": parent_id or None,
            "timestamp": current_dt.isoformat().replace("+00:00", "Z"),
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": reply_text}],
                "timestamp": int(current_dt.timestamp() * 1000),
                "source": "yasmin-missed-reply-watchdog",
                "delivery": {
                    "channel": CHANNEL,
                    "accountId": candidate.account_id,
                    "to": candidate.target,
                    "messageId": message_id,
                },
            },
        }
        with candidate.session_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
        return True
    except OSError as exc:
        log_error(f"transcript mirror failed target={candidate.target}: {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Actually send WhatsApp replies.")
    parser.add_argument("--min-age-minutes", type=int, default=DEFAULT_MIN_AGE_MINUTES)
    parser.add_argument("--max-age-hours", type=int, default=DEFAULT_MAX_AGE_HOURS)
    parser.add_argument("--max-replies", type=int, default=MAX_REPLIES_PER_RUN)
    parser.add_argument("--compose-timeout", type=int, default=45)
    parser.add_argument("--mark-dry-run-handled", action="store_true", help="Mark dry-run candidates handled after composing.")
    args = parser.parse_args()

    setup_logging()
    conn = connect()
    current_ms = now_ms()
    min_age_ms = max(1, args.min_age_minutes) * 60_000
    max_age_ms = max(1, args.max_age_hours) * 3_600_000
    candidates = [
        candidate
        for candidate in load_candidates(min_age_ms, max_age_ms, current_ms)
        if not already_handled(conn, candidate)
    ]
    selected = candidates[: max(0, args.max_replies)]
    log_info(
        f"scan candidates={len(candidates)} selected={len(selected)} "
        f"mode={'live' if args.live else 'dry-run'} min_age={args.min_age_minutes}m"
    )
    sent = 0
    for candidate in selected:
        try:
            reply_text = compose_reply(candidate, timeout=max(5, args.compose_timeout))
        except (RuntimeError, ValueError) as exc:
            log_error(f"compose skipped target={candidate.target} message={candidate.last_user_message_id}: {exc}")
            continue
        if reply_text == NO_REPLY:
            log_info(f"NO_REPLY target={candidate.target} message={candidate.last_user_message_id}")
            if args.live or args.mark_dry_run_handled:
                record_handled(conn, candidate, NO_REPLY, "no-reply")
            continue
        record_draft(conn, candidate, reply_text, "live" if args.live else "dry-run")
        ok, message_id = send_message(candidate, reply_text, live=args.live)
        if not ok:
            continue
        sent += 1
        if args.live:
            append_transcript_mirror(candidate, reply_text, message_id)
            record_handled(conn, candidate, reply_text, "live")
        elif args.mark_dry_run_handled:
            record_handled(conn, candidate, reply_text, "dry-run")
    log_info(f"done sent_or_drafted={sent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
