#!/usr/bin/env python3
"""
moura_reengagement.py - conservative WhatsApp re-engagement for Moura Alexandra.

Default mode is dry-run. Use --live only from the systemd service after review.

Live sends use OpenClaw's WhatsApp channel sender and then mirror the same text
into the exact Moura agent session. If Gateway `chat.inject` is unavailable,
the script appends a normal assistant transcript row and restarts Gateway once
after the batch so the next inbound WhatsApp reply has the check-in in context.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import secrets
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
SESSIONS_INDEX = HOME / ".openclaw/agents/moura-alexandra/sessions/sessions.json"
STATE_DIR = HOME / ".openclaw/moura-reengagement"
STATE_FILE = STATE_DIR / "state.json"
CONTACTS_FILE = STATE_DIR / "contacts.json"
LOG_FILE = STATE_DIR / "moura-reengagement.log"
OPENCLAW = HOME / ".npm-global/bin/openclaw"
DEEPSEEK_KEY_PATH = HOME / ".openclaw/credentials/moura-alexandra/deepseek-api-key.txt"
OPENCLAW_SECRETS_ENV = HOME / ".openclaw/secrets.env"

ACCOUNT_ID = "moura-alexandra"
CHANNEL = "whatsapp"
TZ = ZoneInfo("Asia/Jakarta")

MIN_FOLLOWUP_HOURS = 36
FOLLOWUP_COOLDOWN_DAYS = 21
CHECKIN_COOLDOWN_DAYS_SMALL_LIST = 14
CHECKIN_COOLDOWN_DAYS_MEDIUM_LIST = 21
CHECKIN_COOLDOWN_DAYS_LARGE_LIST = 30
MIN_BATCH_INTERVAL_DAYS = 14
UNANSWERED_REENGAGEMENT_EXCLUDE_AFTER_DAYS = 14
MAX_SENDS_PER_RUN = 1
MAX_SENDS_PER_14_DAYS = 1
QUIET_HOUR_START = 21
QUIET_HOUR_END = 8
MAX_CONTEXT_USER_TURNS = 5
MAX_CONTEXT_CHARS = 7000
MAX_REPLY_CHARS = 700
NO_SEND = "NO_SEND"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"

OPT_OUT_RE = re.compile(
    r"\b("
    r"stop|unsubscribe|unsub|berhenti|spam|jangan\s+spam|jangan\s+ganggu|jangan\s+chat|jangan\s+wa|"
    r"jangan\s+hubungi|ga\s+usah\s+chat|gak\s+usah\s+chat|ga\s+usah\s+wa|gak\s+usah\s+wa|"
    r"tidak\s+mau\s+dihubungi|dont\s+spam|don't\s+spam|dont\s+bother|don't\s+bother|"
    r"stop\s+bothering\s+me"
    r")\b",
    re.IGNORECASE,
)
MENTAL_RE = re.compile(
    r"\b(stress|stres|cemas|anxiety|panic|panik|capek|burnout|sedih|takut|overthinking|sendiri|kesepian|gerd|lambung|asam)\b",
    re.IGNORECASE,
)
PRODUCT_RE = re.compile(
    r"\b(mouru|hotto|produk|minuman|meal replacement|bpom|harga|beli|order|ingredient|bahan|formula)\b",
    re.IGNORECASE,
)
PRIVATE_ASSISTANT_TEXT_RE = re.compile(
    r"^\s*(NO_REPLY|NO_SEND|Menunggu\b|No further instruction\b|Waiting\b|Aku tunggu\b|\[assistant turn failed\b)",
    re.IGNORECASE,
)


@dataclass
class Contact:
    phone: str
    session_key: str
    session_file: Path
    last_interaction_ms: int
    sender_name: str = ""
    gender: str = "unknown"
    opted_out: bool = False
    last_role: str = ""
    last_user_text: str = ""
    last_assistant_text: str = ""
    last_user_ms: int = 0
    last_assistant_ms: int = 0
    recent_context: str = ""


def log(message: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S %z")
    line = f"[{ts}] {message}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        log(f"WARN failed to read {path}: {exc}")
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def now_ms() -> int:
    return int(time.time() * 1000)


def ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(TZ)


def days_since(ms: int, current_ms: int) -> float:
    return (current_ms - ms) / 86_400_000


def hours_since(ms: int, current_ms: int) -> float:
    return (current_ms - ms) / 3_600_000


def in_quiet_hours(dt: datetime) -> bool:
    return dt.hour >= QUIET_HOUR_START or dt.hour < QUIET_HOUR_END


def strip_metadata(text: str) -> str:
    text = re.sub(r"Conversation info \(untrusted metadata\):\s*```json.*?```\s*", "", text, flags=re.S)
    text = re.sub(r"Sender \(untrusted metadata\):\s*```json.*?```\s*", "", text, flags=re.S)
    return re.sub(r"\s+", " ", text).strip()


def extract_sender_name(text: str) -> str:
    match = re.search(r'"sender"\s*:\s*"([^"]+)"', text)
    if match:
        return match.group(1).strip()
    match = re.search(r'"name"\s*:\s*"([^"]+)"', text)
    if match:
        return match.group(1).strip()
    return ""


def message_text(event: dict[str, Any]) -> str:
    content = event.get("message", {}).get("content", [])
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            chunks.append(str(item.get("text", "")))
    return "\n".join(chunks)


def event_message_ms(event: dict[str, Any]) -> int:
    message = event.get("message", {})
    if isinstance(message, dict):
        try:
            timestamp = int(message.get("timestamp", 0) or 0)
            if timestamp > 0:
                return timestamp
        except (TypeError, ValueError):
            pass
    raw_timestamp = event.get("timestamp")
    if isinstance(raw_timestamp, str):
        try:
            return int(datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00")).timestamp() * 1000)
        except ValueError:
            return 0
    return 0


def load_session_tail(path: Path, max_events: int = 80) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        log(f"WARN failed to read session {path}: {exc}")
        return []
    events: list[dict[str, Any]] = []
    for line in lines[-max_events:]:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "message":
            events.append(event)
    return events


def role_of(event: dict[str, Any]) -> str:
    message = event.get("message", {})
    if isinstance(message, dict):
        return str(message.get("role") or "")
    return ""


def is_visible_assistant_reply(event: dict[str, Any]) -> bool:
    if role_of(event) != "assistant":
        return False
    text = strip_metadata(message_text(event))
    if not text or PRIVATE_ASSISTANT_TEXT_RE.search(text):
        return False
    content = event.get("message", {}).get("content", [])
    if isinstance(content, list):
        text_items = [item for item in content if isinstance(item, dict) and item.get("type") == "text"]
        non_text_items = [item for item in content if isinstance(item, dict) and item.get("type") != "text"]
        if non_text_items and not text_items:
            return False
    return True


def context_for(events: list[dict[str, Any]]) -> str:
    selected: list[dict[str, Any]] = []
    user_turns = 0
    for event in reversed(events):
        role = role_of(event)
        if role not in {"user", "assistant"}:
            continue
        text = strip_metadata(message_text(event))
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
        text = strip_metadata(message_text(event))
        label = "User" if role == "user" else "Moura"
        event_ms = event_message_ms(event)
        timestamp = ms_to_dt(event_ms).isoformat() if event_ms else "unknown-time"
        rows.append(f"[{timestamp}] {label}: {text}")

    context = "\n".join(rows)
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[-MAX_CONTEXT_CHARS:]
    return context


def infer_gender(name: str, override: str) -> str:
    if override in {"female", "male", "neutral"}:
        return override
    normalized = name.strip().casefold()
    if normalized in {"ibnu", "ole", "raja", "bimo", "dimas", "reza", "adi", "indra", "agus", "andi"}:
        return "male"
    if normalized in {"alexandra", "sarah", "putri", "dewi", "rani", "nanda", "nadia", "maya", "sinta"}:
        return "female"
    return "unknown"


def load_contacts() -> list[Contact]:
    index = load_json(SESSIONS_INDEX, {})
    overrides = load_json(CONTACTS_FILE, {"contacts": {}}).get("contacts", {})
    contacts: list[Contact] = []

    for session_key, data in index.items():
        if "agent:moura-alexandra:whatsapp:direct:" not in session_key:
            continue
        route = data.get("route", {})
        target = route.get("target", {}) if isinstance(route, dict) else {}
        phone = target.get("to") or data.get("lastTo") or session_key.rsplit(":", 1)[-1]
        if not isinstance(phone, str) or not phone.startswith("+"):
            continue
        session_file = Path(str(data.get("sessionFile", "")))
        last_interaction_ms = int(data.get("lastInteractionAt") or data.get("updatedAt") or 0)
        contact = Contact(
            phone=phone,
            session_key=session_key,
            session_file=session_file,
            last_interaction_ms=last_interaction_ms,
        )

        events = load_session_tail(session_file)
        for event in events:
            role = event.get("message", {}).get("role", "")
            raw = message_text(event)
            clean = strip_metadata(raw)
            event_ms = event_message_ms(event)
            if role == "user":
                contact.sender_name = extract_sender_name(raw) or contact.sender_name
                contact.last_user_text = clean or contact.last_user_text
                contact.last_user_ms = max(contact.last_user_ms, event_ms)
                if OPT_OUT_RE.search(clean):
                    contact.opted_out = True
            elif role == "assistant":
                contact.last_assistant_text = clean or contact.last_assistant_text
                contact.last_assistant_ms = max(contact.last_assistant_ms, event_ms)
            if role in {"user", "assistant"}:
                contact.last_role = role

        override = overrides.get(phone, {}) if isinstance(overrides, dict) else {}
        if isinstance(override, dict):
            if override.get("name"):
                contact.sender_name = str(override["name"])
            if override.get("opted_out") is True:
                contact.opted_out = True
            contact.gender = infer_gender(contact.sender_name, str(override.get("gender", "unknown")))
        else:
            contact.gender = infer_gender(contact.sender_name, "unknown")
        contact.recent_context = context_for(events)
        contacts.append(contact)

    return contacts


def salutation(contact: Contact) -> str:
    if contact.gender == "male":
        return "mas"
    if contact.gender == "female":
        return "say"
    return ""


def weekly_checkin_text(contact: Contact) -> str:
    honorific = salutation(contact)
    if honorific == "male":
        variants = [
            "gmn kabar kamu hari ini mas?",
            "mas, hari ini gimana kabarnya?",
            "lagi aman-aman aja mas hari ini?",
        ]
    elif honorific == "female":
        variants = [
            "say, gmn kabar km hr ini?",
            "say, hari ini gimana kabarnya?",
            "lagi aman-aman aja say hari ini?",
        ]
    else:
        variants = [
            "hei, gmn kabar kamu hari ini?",
            "hari ini gimana kabarnya?",
            "lagi aman-aman aja hari ini?",
        ]
    return random.choice(variants)


def followup_text(contact: Contact) -> str:
    honorific = salutation(contact)
    suffix = f" {honorific}" if honorific else ""
    last_user = contact.last_user_text
    last_assistant = contact.last_assistant_text

    if MENTAL_RE.search(last_user) or MENTAL_RE.search(last_assistant):
        variants = [
            f"aku kepikiran obrolan kita kemarin{suffix}. sekarang rasanya gimana?",
            f"kemarin kamu sempet cerita lagi berat{suffix}. hari ini agak mendingan ga?",
            f"aku cuma mau cek pelan-pelan{suffix}, kabarmu sekarang gimana?",
        ]
    elif PRODUCT_RE.search(last_user) or PRODUCT_RE.search(last_assistant):
        variants = [
            f"kemarin kamu sempet nanya soal Mouru{suffix}. ada yang masih bikin penasaran?",
            f"aku follow up dikit ya{suffix}, soal Mouru kemarin masih ada yang mau kamu tanyain?",
        ]
    else:
        variants = [
            f"aku follow up obrolan kita kemarin ya{suffix}. gimana kabarmu sekarang?",
            f"kemarin obrolannya sempet berhenti{suffix}. mau lanjut cerita atau tanya sesuatu?",
        ]
    return random.choice(variants).strip()


def recent_send_count(state: dict[str, Any], current_ms: int, window_days: int) -> int:
    sends = state.get("send_log", [])
    if not isinstance(sends, list):
        return 0
    cutoff = current_ms - window_days * 86_400_000
    return sum(1 for item in sends if int(item.get("sent_at_ms", 0)) >= cutoff)


def last_batch_age_days(state: dict[str, Any], current_ms: int) -> float | None:
    sends = state.get("send_log", [])
    if not isinstance(sends, list):
        return None
    sent_times = [int(item.get("sent_at_ms", 0) or 0) for item in sends]
    sent_times = [sent_at for sent_at in sent_times if sent_at > 0]
    if not sent_times:
        return None
    return days_since(max(sent_times), current_ms)


def sync_contact_exclusions(state: dict[str, Any], contacts: list[Contact], current_dt: datetime, current_ms: int) -> bool:
    changed = False
    for contact in contacts:
        cstate = state.setdefault("contacts", {}).setdefault(contact.phone, {})
        if contact.opted_out and cstate.get("opted_out") is not True:
            cstate["opted_out"] = True
            cstate["excluded"] = True
            cstate["excluded_reason"] = "opt_out_reply"
            cstate["excluded_at"] = current_dt.isoformat()
            changed = True
            log(f"EXCLUDE {contact.phone}: opt-out reply detected")
            continue

        if cstate.get("excluded") is True or cstate.get("opted_out") is True:
            continue

        last_sent_ms = int(cstate.get("last_sent_ms", 0) or 0)
        last_kind = str(cstate.get("last_kind", ""))
        if not last_sent_ms or last_kind not in {"followup", "checkin"}:
            continue
        if contact.last_user_ms > last_sent_ms:
            continue
        if days_since(last_sent_ms, current_ms) < UNANSWERED_REENGAGEMENT_EXCLUDE_AFTER_DAYS:
            continue

        cstate["excluded"] = True
        cstate["excluded_reason"] = "unanswered_reengagement"
        cstate["excluded_at"] = current_dt.isoformat()
        changed = True
        log(f"EXCLUDE {contact.phone}: no reply after last re-engagement")
    return changed


def checkin_cooldown_days(total_contacts: int) -> int:
    if total_contacts <= 20:
        return CHECKIN_COOLDOWN_DAYS_SMALL_LIST
    if total_contacts <= 100:
        return CHECKIN_COOLDOWN_DAYS_MEDIUM_LIST
    return CHECKIN_COOLDOWN_DAYS_LARGE_LIST


def eligible_reason(contact: Contact, state: dict[str, Any], total_contacts: int, current_ms: int) -> tuple[str, str] | None:
    if contact.opted_out:
        return None
    cstate = state.setdefault("contacts", {}).setdefault(contact.phone, {})
    if cstate.get("excluded") is True:
        return None
    if cstate.get("opted_out") is True:
        return None

    last_sent_ms = int(cstate.get("last_sent_ms", 0) or 0)
    last_followup_ms = int(cstate.get("last_followup_ms", 0) or 0)
    last_checkin_ms = int(cstate.get("last_checkin_ms", 0) or 0)

    if last_sent_ms and days_since(last_sent_ms, current_ms) < 7:
        return None

    if contact.last_role == "assistant" and hours_since(contact.last_interaction_ms, current_ms) >= MIN_FOLLOWUP_HOURS:
        if not last_followup_ms or days_since(last_followup_ms, current_ms) >= FOLLOWUP_COOLDOWN_DAYS:
            return ("followup", "Moura was the last visible sender and the chat has been quiet long enough for one careful follow-up.")

    inactive_days = days_since(contact.last_interaction_ms, current_ms)
    cooldown = checkin_cooldown_days(total_contacts)
    if inactive_days >= cooldown and (not last_checkin_ms or days_since(last_checkin_ms, current_ms) >= cooldown):
        return ("checkin", "The contact has been inactive long enough for one light check-in.")

    return None


def read_deepseek_key() -> str:
    env_key = os.environ.get("MOURA_DEEPSEEK_API_KEY", "").strip()
    if env_key:
        return env_key
    env_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if env_key:
        return env_key
    try:
        file_key = DEEPSEEK_KEY_PATH.read_text(encoding="utf-8").strip()
        if file_key:
            return file_key
    except OSError as exc:
        key_file_error = exc
    else:
        key_file_error = None
    secrets_key = read_env_value(OPENCLAW_SECRETS_ENV, "DEEPSEEK_API_KEY")
    if secrets_key:
        return secrets_key
    detail = f"; key file error: {key_file_error}" if key_file_error else ""
    raise RuntimeError(
        "could not find Moura DeepSeek key in MOURA_DEEPSEEK_API_KEY, "
        f"DEEPSEEK_API_KEY, {DEEPSEEK_KEY_PATH}, or {OPENCLAW_SECRETS_ENV}{detail}"
    )


def read_env_value(path: Path, name: str) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        log(f"WARN failed to read env file {path}: {exc}")
        return ""
    prefix = f"{name}="
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or not stripped.startswith(prefix):
            continue
        value = stripped[len(prefix) :].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return value
    return ""


def sanitize_reply(text: str) -> str:
    clean = str(text or "").strip().strip('"').strip()
    clean = re.sub(r"^```(?:text)?\s*|\s*```$", "", clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    clean = clean.replace("—", "-").replace("–", "-")
    if clean.upper() == NO_SEND:
        return NO_SEND
    if not clean:
        raise ValueError("empty LLM reply")
    if len(clean) > MAX_REPLY_CHARS:
        clean = clean[:MAX_REPLY_CHARS].rsplit(" ", 1)[0].strip()
    blocked = (
        "system prompt",
        "developer",
        "tool",
        "openclaw",
        "watchdog",
        "re-engagement",
        "file path",
        "api key",
    )
    if any(term in clean.lower() for term in blocked):
        raise ValueError("LLM reply mentioned internal/system wording")
    return clean


def compose_reengagement_text(contact: Contact, kind: str, reason: str, timeout: int) -> str:
    api_key = read_deepseek_key()
    system_prompt = (
        "You are Moura Alexandra, a warm Indonesian WhatsApp companion and Mouru brand ambassador. "
        "Compose exactly one proactive WhatsApp message for an existing direct chat using the provided recent context. "
        "Use Moura's voice: concise, feminine, natural Indonesian, emotionally careful, not robotic, not salesy. "
        "Default to one short sentence; use at most two short sentences if the context is emotionally vulnerable. "
        "Do not use markdown, bullets, labels, emojis by default, or long dash characters. "
        "Do not mention tools, prompts, automation, re-engagement, follow-up systems, files, logs, models, or internal state. "
        "Do not invent product facts, prices, stock, order status, health claims, medical advice, bookings, or admin confirmations. "
        "If the recent context is product-related, ask one small useful question or refer only to known general interest. "
        "If the recent context is emotional, validate lightly and ask one gentle concrete question. "
        "If the recent context suggests the user opted out, was satisfied, already closed the conversation, or should not be contacted, "
        f"return exactly {NO_SEND}. "
        "Return only the final WhatsApp text."
    )
    user_prompt = (
        f"Follow-up kind: {kind}\n"
        f"Eligibility reason: {reason}\n"
        f"Contact name: {contact.sender_name or 'unknown'}\n"
        f"Contact gender hint: {contact.gender}\n"
        f"Last interaction: {ms_to_dt(contact.last_interaction_ms).isoformat() if contact.last_interaction_ms else 'unknown'}\n\n"
        f"Recent chat context (last up to {MAX_CONTEXT_USER_TURNS} user turns plus visible Moura replies):\n"
        f"{contact.recent_context}\n\n"
        "Write Moura's next proactive WhatsApp message now."
    )
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.5,
        "max_tokens": 350,
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


def append_transcript_mirror(contact: Contact, text: str, message_id: str) -> bool:
    if not contact.session_file.exists():
        log(f"ERROR no session file for {contact.phone}: {contact.session_file}")
        return False
    try:
        lines = contact.session_file.read_text(encoding="utf-8").splitlines()
        if not lines:
            log(f"ERROR empty session file for {contact.phone}: {contact.session_file}")
            return False
        last = json.loads(lines[-1])
        current_dt = datetime.now(timezone.utc)
        entry = {
            "type": "message",
            "id": secrets.token_hex(4),
            "parentId": last.get("id"),
            "timestamp": current_dt.isoformat().replace("+00:00", "Z"),
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": text}],
                "timestamp": int(current_dt.timestamp() * 1000),
                "source": "moura-reengagement",
                "delivery": {
                    "channel": CHANNEL,
                    "accountId": ACCOUNT_ID,
                    "to": contact.phone,
                    "messageId": message_id,
                },
            },
        }
        with contact.session_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
        log(f"MIRRORED file {contact.phone}: {entry['id']}")
        return True
    except (OSError, json.JSONDecodeError) as exc:
        log(f"ERROR transcript mirror failed for {contact.phone}: {exc}")
        return False


def inject_transcript_mirror(contact: Contact, text: str) -> bool:
    params = {
        "sessionKey": contact.session_key,
        "message": text,
        "label": "Moura re-engagement",
    }
    cmd = [
        str(OPENCLAW),
        "gateway",
        "call",
        "chat.inject",
        "--params",
        json.dumps(params, ensure_ascii=False, separators=(",", ":")),
        "--json",
        "--timeout",
        "10000",
    ]
    try:
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log(f"WARN chat.inject failed for {contact.phone}: {exc}")
        return False
    if result.returncode != 0:
        stderr = result.stderr.strip().replace("\n", " ")
        log(f"WARN chat.inject returned {result.returncode} for {contact.phone}: {stderr}")
        return False
    log(f"MIRRORED gateway {contact.phone}: {text}")
    return True


def restart_gateway_after_file_mirror() -> None:
    cmd = [str(OPENCLAW), "gateway", "restart"]
    try:
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log(f"ERROR gateway restart after mirror failed: {exc}")
        return
    if result.returncode != 0:
        stderr = result.stderr.strip().replace("\n", " ")
        log(f"ERROR gateway restart after mirror returned {result.returncode}: {stderr}")
        return
    log("gateway restarted after transcript file mirror")


def send_message(contact: Contact, text: str, dry_run: bool) -> tuple[bool, bool]:
    cmd = [
        str(OPENCLAW),
        "message",
        "send",
        "--channel",
        CHANNEL,
        "--account",
        ACCOUNT_ID,
        "--target",
        contact.phone,
        "--message",
        text,
        "--json",
    ]
    if dry_run:
        log(f"DRY-RUN {contact.phone}: {text}")
        return True, False

    try:
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log(f"ERROR send failed for {contact.phone}: {exc}")
        return False, False

    if result.returncode != 0:
        stderr = result.stderr.strip().replace("\n", " ")
        log(f"ERROR send returned {result.returncode} for {contact.phone}: {stderr}")
        return False, False

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {}
    message_id = str(payload.get("messageId") or payload.get("payload", {}).get("result", {}).get("messageId") or "")
    log(f"SENT {contact.phone}: {text}")

    if inject_transcript_mirror(contact, text):
        return True, False
    if append_transcript_mirror(contact, text, message_id):
        return True, True
    return True, False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Actually send WhatsApp messages.")
    parser.add_argument("--ignore-quiet-hours", action="store_true", help="Allow sending outside 08:00-21:00 WIB.")
    parser.add_argument("--max-sends", type=int, default=MAX_SENDS_PER_RUN)
    parser.add_argument("--compose-timeout", type=int, default=45)
    args = parser.parse_args()

    random.seed(datetime.now(TZ).strftime("%Y-%m-%d"))
    current_dt = datetime.now(TZ)
    current_ms = now_ms()
    dry_run = not args.live

    state = load_json(STATE_FILE, {"version": 1, "contacts": {}, "send_log": []})
    contacts = load_contacts()
    total_contacts = len(contacts)
    if sync_contact_exclusions(state, contacts, current_dt, current_ms):
        save_json(STATE_FILE, state)

    if not args.ignore_quiet_hours and in_quiet_hours(current_dt):
        log(f"SKIP quiet hours at {current_dt.strftime('%H:%M')} WIB")
        return 0

    batch_age_days = last_batch_age_days(state, current_ms)
    if batch_age_days is not None and batch_age_days < MIN_BATCH_INTERVAL_DAYS:
        log(f"SKIP batch cooldown active ({batch_age_days:.1f}/{MIN_BATCH_INTERVAL_DAYS} days)")
        return 0

    if recent_send_count(state, current_ms, MIN_BATCH_INTERVAL_DAYS) >= MAX_SENDS_PER_14_DAYS:
        log(f"SKIP 14-day cap reached ({MAX_SENDS_PER_14_DAYS})")
        return 0

    candidates: list[tuple[Contact, str, str]] = []
    for contact in contacts:
        result = eligible_reason(contact, state, total_contacts, current_ms)
        if result:
            kind, reason = result
            candidates.append((contact, kind, reason))

    random.shuffle(candidates)
    followups = [item for item in candidates if item[1] == "followup"]
    checkins = [item for item in candidates if item[1] == "checkin"]
    selected = (followups + checkins)[: max(0, args.max_sends)]

    log(
        f"scan contacts={total_contacts} candidates={len(candidates)} selected={len(selected)} "
        f"mode={'live' if args.live else 'dry-run'}"
    )

    sent_count = 0
    restart_needed = False
    for contact, kind, reason in selected:
        try:
            text = compose_reengagement_text(contact, kind, reason, timeout=max(5, args.compose_timeout))
        except (RuntimeError, ValueError) as exc:
            log(f"ERROR compose skipped for {contact.phone}: {exc}")
            continue
        if text == NO_SEND:
            log(f"NO_SEND {contact.phone}: context did not need proactive message")
            continue
        ok, needs_restart = send_message(contact, text, dry_run=dry_run)
        if not ok:
            continue
        sent_count += 1
        restart_needed = restart_needed or needs_restart
        if not dry_run:
            cstate = state.setdefault("contacts", {}).setdefault(contact.phone, {})
            cstate["last_sent_ms"] = current_ms
            cstate["last_sent_at"] = current_dt.isoformat()
            cstate["last_kind"] = kind
            if kind == "followup":
                cstate["last_followup_ms"] = current_ms
            else:
                cstate["last_checkin_ms"] = current_ms
            state.setdefault("send_log", []).append(
                {
                    "phone": contact.phone,
                    "kind": kind,
                    "sent_at_ms": current_ms,
                    "sent_at": current_dt.isoformat(),
                    "last_interaction_at": ms_to_dt(contact.last_interaction_ms).isoformat(),
                }
            )

    if not dry_run:
        state["send_log"] = state.get("send_log", [])[-200:]
        save_json(STATE_FILE, state)
        if restart_needed:
            restart_gateway_after_file_mirror()

    log(f"done sent={sent_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
