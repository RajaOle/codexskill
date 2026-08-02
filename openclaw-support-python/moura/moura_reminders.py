#!/usr/bin/env python3
"""
moura_reminders.py - narrow WhatsApp reminder scheduler for Moura Alexandra.

This is intentionally not a cron/shell bridge. It stores audited reminders in a
local SQLite database and sends due reminders through OpenClaw's message CLI.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import random
import re
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


HOME = Path("/home/olekamole")
STATE_DIR = HOME / ".openclaw/moura-reminders"
DB_PATH = STATE_DIR / "reminders.sqlite"
LOG_FILE = STATE_DIR / "moura-reminders.log"
OPENCLAW = HOME / ".npm-global/bin/openclaw"
OPENCLAW_CONFIG = HOME / ".openclaw/openclaw.json"

CHANNEL = "whatsapp"
ACCOUNT_ID = "moura-alexandra"
TZ = ZoneInfo("Asia/Jakarta")
MAX_MESSAGE_CHARS = 900
MAX_LABEL_CHARS = 120
MAX_DUE_PER_RUN = 10
MAX_DAILY_TIMES = 12
EDITABLE_STATUSES = {"pending", "failed", "canceled"}
DAILY_WINDOW_PRESETS = {
    "morning": ("08:00", "10:30"),
    "noon": ("12:00", "14:00"),
    "afternoon": ("16:00", "18:00"),
}
DAILY_WINDOW_ALIASES = {
    "pagi": "morning",
    "morning": "morning",
    "siang": "noon",
    "noon": "noon",
    "midday": "noon",
    "sore": "afternoon",
    "afternoon": "afternoon",
}

AUTHORIZED_DIRECTORS = {
    "+685643497070": "Ibnu",
    "+6285643497070": "Ibnu",
    "+6281231152992": "Apin",
    "+62895379652424": "Apin",
}

PHONE_RE = re.compile(r"^\+[1-9][0-9]{7,15}$")
WHATSAPP_GROUP_RE = re.compile(r"^[0-9]{10,32}@g\.us$")
TIME_OF_DAY_RE = re.compile(r"^([01]?[0-9]|2[0-3]):([0-5][0-9])(?::([0-5][0-9]))?$")


@dataclass
class Reminder:
    id: int
    created_at: str
    created_by_phone: str
    created_by_name: str
    target: str
    due_at: str
    timezone_name: str
    message: str
    label: str
    source: str
    status: str
    attempts: int
    recurrence: str
    recurrence_times: str
    recurrence_windows: str
    recurrence_until: str
    sent_count: int


def setup_logging() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_FILE),
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
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            created_by_phone TEXT NOT NULL,
            created_by_name TEXT NOT NULL,
            target TEXT NOT NULL,
            due_at TEXT NOT NULL,
            timezone_name TEXT NOT NULL,
            message TEXT NOT NULL,
            label TEXT NOT NULL,
            source TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            recurrence TEXT NOT NULL DEFAULT 'once',
            recurrence_times TEXT NOT NULL DEFAULT '',
            recurrence_windows TEXT NOT NULL DEFAULT '',
            recurrence_until TEXT NOT NULL DEFAULT '',
            sent_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '',
            sent_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    ensure_column(conn, "reminders", "recurrence", "TEXT NOT NULL DEFAULT 'once'")
    ensure_column(conn, "reminders", "recurrence_times", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "reminders", "recurrence_windows", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "reminders", "recurrence_until", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "reminders", "sent_count", "INTEGER NOT NULL DEFAULT 0")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(status, due_at)"
    )
    conn.commit()


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def normalize_phone(value: str) -> str:
    phone = str(value or "").strip()
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if not phone.startswith("+") and phone.isdigit():
        phone = "+" + phone
    if not PHONE_RE.match(phone):
        raise ValueError("invalid phone format")
    return phone


def configured_moura_groups() -> set[str]:
    try:
        data = json.loads(OPENCLAW_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("could not load Moura WhatsApp group allowlist") from exc

    groups = (
        data.get("channels", {})
        .get(CHANNEL, {})
        .get("accounts", {})
        .get(ACCOUNT_ID, {})
        .get("groups", {})
    )
    if not isinstance(groups, dict):
        return set()
    return {str(group_id).strip() for group_id in groups if WHATSAPP_GROUP_RE.match(str(group_id).strip())}


def normalize_target(value: str) -> str:
    target = str(value or "").strip()
    if WHATSAPP_GROUP_RE.match(target):
        if target not in configured_moura_groups():
            raise ValueError("group target is not configured for Moura Alexandra")
        return target
    return normalize_phone(target)


def parse_due_at(value: str, timezone_name: str) -> datetime:
    if not value:
        raise ValueError("due_at is required")
    tz = ZoneInfo(timezone_name or "Asia/Jakarta")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("due_at must be ISO-8601, for example 2026-07-18T09:00:00+07:00") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(timezone.utc)


def parse_optional_until(value: str, timezone_name: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return utc_iso(parse_due_at(raw, timezone_name))


def normalize_recurrence(value: str) -> str:
    recurrence = str(value or "once").strip().lower()
    if recurrence in {"none", "one_shot", "one-shot"}:
        recurrence = "once"
    if recurrence in {"daily-random", "daily random", "random_daily"}:
        recurrence = "daily_random"
    if recurrence not in {"once", "daily", "daily_random"}:
        raise ValueError("recurrence must be once, daily, or daily_random")
    return recurrence


def parse_time_of_day(value: str) -> dt_time:
    match = TIME_OF_DAY_RE.match(value)
    if not match:
        raise ValueError("time values must use HH:MM or HH:MM:SS")
    return dt_time(int(match.group(1)), int(match.group(2)), int(match.group(3) or "0"))


def parse_daily_times(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        raw_items = [str(item).strip() for item in value]
    else:
        raw_items = []

    times: list[dt_time] = []
    seen: set[str] = set()
    for raw in raw_items:
        if not raw:
            continue
        parsed = parse_time_of_day(raw)
        normalized = parsed.strftime("%H:%M:%S" if parsed.second else "%H:%M")
        if normalized in seen:
            continue
        seen.add(normalized)
        times.append(parsed)

    if not times:
        raise ValueError("daily recurrence requires at least one daily time")
    if len(times) > MAX_DAILY_TIMES:
        raise ValueError(f"daily recurrence supports at most {MAX_DAILY_TIMES} times per day")
    return [t.strftime("%H:%M:%S" if t.second else "%H:%M") for t in sorted(times)]


def parse_daily_windows(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        raw_items = [str(item).strip() for item in value]
    else:
        raw_items = []

    windows: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        key = DAILY_WINDOW_ALIASES.get(raw.lower())
        if not key:
            raise ValueError("daily_windows must use morning, noon, and/or afternoon")
        if key in seen:
            continue
        seen.add(key)
        windows.append(key)

    if not windows:
        raise ValueError("daily_random recurrence requires at least one daily window")
    return sorted(windows, key=lambda item: parse_time_of_day(DAILY_WINDOW_PRESETS[item][0]))


def next_daily_due(daily_times: list[str], timezone_name: str, after_dt: datetime) -> datetime:
    tz = ZoneInfo(timezone_name or "Asia/Jakarta")
    local_after = after_dt.astimezone(tz)
    parsed_times = parse_daily_times(daily_times)

    for raw_time in parsed_times:
        hour, minute, *rest = [int(part) for part in raw_time.split(":")]
        second = rest[0] if rest else 0
        candidate = datetime.combine(local_after.date(), dt_time(hour, minute, second), tzinfo=tz)
        if candidate > local_after:
            return candidate.astimezone(timezone.utc)

    hour, minute, *rest = [int(part) for part in parsed_times[0].split(":")]
    second = rest[0] if rest else 0
    candidate = datetime.combine(local_after.date() + timedelta(days=1), dt_time(hour, minute, second), tzinfo=tz)
    return candidate.astimezone(timezone.utc)


def random_datetime_between(start_dt: datetime, end_dt: datetime) -> datetime:
    total_seconds = int((end_dt - start_dt).total_seconds())
    if total_seconds <= 0:
        raise ValueError("daily random window has no remaining time")
    return start_dt + timedelta(seconds=random.randint(0, total_seconds))


def next_daily_window_due(
    daily_windows: list[str],
    timezone_name: str,
    after_dt: datetime,
    allow_active_window: bool = True,
) -> datetime:
    tz = ZoneInfo(timezone_name or "Asia/Jakarta")
    local_after = after_dt.astimezone(tz)
    parsed_windows = parse_daily_windows(daily_windows)
    min_delay = timedelta(minutes=1)

    for day_offset in range(2):
        target_date = local_after.date() + timedelta(days=day_offset)
        for window in parsed_windows:
            start_raw, end_raw = DAILY_WINDOW_PRESETS[window]
            start_dt = datetime.combine(target_date, parse_time_of_day(start_raw), tzinfo=tz)
            end_dt = datetime.combine(target_date, parse_time_of_day(end_raw), tzinfo=tz)
            lower_bound = start_dt
            if day_offset == 0 and local_after >= start_dt:
                if not allow_active_window:
                    continue
                lower_bound = local_after + min_delay
            if lower_bound < end_dt:
                return random_datetime_between(lower_bound, end_dt).astimezone(timezone.utc)

    first_window = parsed_windows[0]
    start_raw, end_raw = DAILY_WINDOW_PRESETS[first_window]
    target_date = local_after.date() + timedelta(days=2)
    start_dt = datetime.combine(target_date, parse_time_of_day(start_raw), tzinfo=tz)
    end_dt = datetime.combine(target_date, parse_time_of_day(end_raw), tzinfo=tz)
    return random_datetime_between(start_dt, end_dt).astimezone(timezone.utc)


def next_recurring_due(reminder: Reminder, after_dt: datetime) -> datetime | None:
    if reminder.recurrence == "daily":
        try:
            daily_times = json.loads(reminder.recurrence_times)
        except json.JSONDecodeError as exc:
            raise RuntimeError("stored daily recurrence times are invalid") from exc
        next_due = next_daily_due(daily_times, reminder.timezone_name, after_dt)
    elif reminder.recurrence == "daily_random":
        try:
            daily_windows = json.loads(reminder.recurrence_windows)
        except json.JSONDecodeError as exc:
            raise RuntimeError("stored daily recurrence windows are invalid") from exc
        next_due = next_daily_window_due(
            daily_windows,
            reminder.timezone_name,
            after_dt,
            allow_active_window=False,
        )
    else:
        return None

    if reminder.recurrence_until:
        until_dt = parse_due_at(reminder.recurrence_until, reminder.timezone_name)
        if next_due > until_dt:
            return None
    return next_due


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def text_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def validate_authorized_director(phone: str) -> str:
    normalized = normalize_phone(phone)
    name = AUTHORIZED_DIRECTORS.get(normalized)
    if not name:
        raise PermissionError("requester is not an authorized Mouru business director")
    return name


def create_reminder(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    requester_phone = normalize_phone(str(payload.get("created_by_phone", "")))
    requester_name = validate_authorized_director(requester_phone)
    target = normalize_target(str(payload.get("target", "")))
    timezone_name = str(payload.get("timezone", "Asia/Jakarta") or "Asia/Jakarta")
    now = utc_now()
    recurrence = normalize_recurrence(str(payload.get("recurrence", "once") or "once"))
    recurrence_times = ""
    recurrence_windows = ""
    recurrence_until = parse_optional_until(str(payload.get("recurrence_until", "") or ""), timezone_name)

    if recurrence == "daily" and not payload.get("daily_times") and payload.get("daily_windows"):
        recurrence = "daily_random"

    if recurrence == "daily":
        daily_times = parse_daily_times(payload.get("daily_times", payload.get("times", [])))
        recurrence_times = json.dumps(daily_times, ensure_ascii=False)
        due_dt = next_daily_due(daily_times, timezone_name, now)
        if recurrence_until and due_dt > parse_due_at(recurrence_until, timezone_name):
            raise ValueError("recurrence_until must be after the next scheduled daily reminder")
    elif recurrence == "daily_random":
        daily_windows = parse_daily_windows(payload.get("daily_windows", payload.get("windows", [])))
        recurrence_windows = json.dumps(daily_windows, ensure_ascii=False)
        due_dt = next_daily_window_due(daily_windows, timezone_name, now)
        if recurrence_until and due_dt > parse_due_at(recurrence_until, timezone_name):
            raise ValueError("recurrence_until must be after the next scheduled random daily reminder")
    else:
        due_dt = parse_due_at(str(payload.get("due_at", "")), timezone_name)

    if due_dt <= now:
        raise ValueError("due_at must be in the future")

    message = re.sub(r"\s+", " ", str(payload.get("message", "") or "")).strip()
    if not message:
        raise ValueError("message is required")
    if len(message) > MAX_MESSAGE_CHARS:
        raise ValueError(f"message exceeds {MAX_MESSAGE_CHARS} characters")

    label = re.sub(r"\s+", " ", str(payload.get("label", "") or "")).strip()
    if len(label) > MAX_LABEL_CHARS:
        raise ValueError(f"label exceeds {MAX_LABEL_CHARS} characters")

    source = re.sub(r"\s+", " ", str(payload.get("source", "moura_reminder_create") or "")).strip()
    if not source:
        source = "moura_reminder_create"

    cursor = conn.execute(
        """
        INSERT INTO reminders (
            created_at, created_by_phone, created_by_name, target, due_at,
            timezone_name, message, label, source, status, recurrence,
            recurrence_times, recurrence_windows, recurrence_until
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
        """,
        (
            utc_iso(now),
            requester_phone,
            requester_name,
            target,
            utc_iso(due_dt),
            timezone_name,
            message,
            label,
            source,
            recurrence,
            recurrence_times,
            recurrence_windows,
            recurrence_until,
        ),
    )
    conn.commit()
    reminder_id = int(cursor.lastrowid)
    log_info(
        f"created reminder id={reminder_id} requester={requester_phone} target={target} due_at={utc_iso(due_dt)}"
    )
    return {
        "ok": True,
        "id": reminder_id,
        "target": target,
        "due_at": utc_iso(due_dt),
        "timezone": timezone_name,
        "recurrence": recurrence,
        "daily_times": json.loads(recurrence_times) if recurrence_times else [],
        "daily_windows": json.loads(recurrence_windows) if recurrence_windows else [],
        "recurrence_until": recurrence_until,
        "created_by": requester_name,
    }


def validate_payload_requester(payload: dict[str, Any]) -> tuple[str, str]:
    requester_phone = normalize_phone(str(payload.get("created_by_phone", "")))
    requester_name = validate_authorized_director(requester_phone)
    return requester_phone, requester_name


def normalize_limit(value: Any, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    for key in ("message", "last_error"):
        if key in item and isinstance(item[key], str) and len(item[key]) > 220:
            item[key] = item[key][:217] + "..."
    return item


def row_to_reminder(row: sqlite3.Row) -> Reminder:
    return Reminder(
        id=int(row["id"]),
        created_at=str(row["created_at"]),
        created_by_phone=str(row["created_by_phone"]),
        created_by_name=str(row["created_by_name"]),
        target=str(row["target"]),
        due_at=str(row["due_at"]),
        timezone_name=str(row["timezone_name"]),
        message=str(row["message"]),
        label=str(row["label"]),
        source=str(row["source"]),
        status=str(row["status"]),
        attempts=int(row["attempts"]),
        recurrence=str(row["recurrence"] or "once"),
        recurrence_times=str(row["recurrence_times"] or ""),
        recurrence_windows=str(row["recurrence_windows"] or ""),
        recurrence_until=str(row["recurrence_until"] or ""),
        sent_count=int(row["sent_count"] or 0),
    )


def due_reminders(conn: sqlite3.Connection, limit: int) -> list[Reminder]:
    rows = conn.execute(
        """
        SELECT * FROM reminders
        WHERE status = 'pending' AND due_at <= ?
        ORDER BY due_at ASC, id ASC
        LIMIT ?
        """,
        (utc_iso(utc_now()), limit),
    ).fetchall()
    return [row_to_reminder(row) for row in rows]


def mark_attempt(conn: sqlite3.Connection, reminder: Reminder) -> None:
    conn.execute(
        "UPDATE reminders SET attempts = attempts + 1 WHERE id = ?",
        (reminder.id,),
    )
    conn.commit()


def mark_sent(conn: sqlite3.Connection, reminder: Reminder) -> None:
    now = utc_now()
    sent_at = utc_iso(now)
    if reminder.recurrence in {"daily", "daily_random"}:
        next_due = next_recurring_due(reminder, now)
        if next_due:
            conn.execute(
                """
                UPDATE reminders
                SET status = 'pending', due_at = ?, attempts = 0, sent_count = sent_count + 1,
                    sent_at = ?, last_error = ''
                WHERE id = ?
                """,
                (utc_iso(next_due), sent_at, reminder.id),
            )
        else:
            conn.execute(
                """
                UPDATE reminders
                SET status = 'sent', attempts = 0, sent_count = sent_count + 1,
                    sent_at = ?, last_error = ''
                WHERE id = ?
                """,
                (sent_at, reminder.id),
            )
    else:
        conn.execute(
            """
            UPDATE reminders
            SET status = 'sent', sent_count = sent_count + 1, sent_at = ?, last_error = ''
            WHERE id = ?
            """,
            (sent_at, reminder.id),
        )
    conn.commit()


def mark_failed(conn: sqlite3.Connection, reminder: Reminder, error: str) -> None:
    next_status = "failed" if reminder.attempts + 1 >= 3 else "pending"
    conn.execute(
        "UPDATE reminders SET status = ?, last_error = ? WHERE id = ?",
        (next_status, error[:500], reminder.id),
    )
    conn.commit()


def send_reminder(reminder: Reminder, dry_run: bool) -> bool:
    text = reminder.message
    if reminder.label:
        text = f"{reminder.label}\n\n{text}"
    if dry_run:
        log_info(f"DRY-RUN send id={reminder.id} target={reminder.target}: {text}")
        return True

    cmd = [
        str(OPENCLAW),
        "message",
        "send",
        "--channel",
        CHANNEL,
        "--account",
        ACCOUNT_ID,
        "--target",
        reminder.target,
        "--message",
        text,
        "--json",
    ]
    try:
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"send failed: {exc}") from exc
    if result.returncode != 0:
        stderr = result.stderr.strip().replace("\n", " ")
        raise RuntimeError(f"send returned {result.returncode}: {stderr}")
    log_info(f"SENT id={reminder.id} target={reminder.target}")
    return True


def run_due(conn: sqlite3.Connection, dry_run: bool, limit: int) -> dict[str, Any]:
    reminders = due_reminders(conn, limit=limit)
    sent = 0
    failed = 0
    for reminder in reminders:
        mark_attempt(conn, reminder)
        try:
            if send_reminder(reminder, dry_run=dry_run):
                sent += 1
                if not dry_run:
                    mark_sent(conn, reminder)
        except RuntimeError as exc:
            failed += 1
            log_error(f"ERROR id={reminder.id}: {exc}")
            if not dry_run:
                mark_failed(conn, reminder, str(exc))
    log_info(f"done due={len(reminders)} sent={sent} failed={failed} mode={'dry-run' if dry_run else 'live'}")
    return {"ok": failed == 0, "due": len(reminders), "sent": sent, "failed": failed}


def list_reminders(conn: sqlite3.Connection, status: str, limit: int) -> dict[str, Any]:
    if status == "all":
        rows = conn.execute(
            "SELECT * FROM reminders ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM reminders WHERE status = ? ORDER BY due_at ASC, id ASC LIMIT ?",
            (status, limit),
        ).fetchall()
    items = [dict(row) for row in rows]
    return {"ok": True, "count": len(items), "reminders": items}


def list_reminders_for_payload(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    validate_payload_requester(payload)
    status = str(payload.get("status", "pending") or "pending").strip().lower()
    if status not in {"pending", "sent", "failed", "canceled", "all"}:
        raise ValueError("status must be pending, sent, failed, canceled, or all")
    limit = normalize_limit(payload.get("limit"), 20, 50)
    target = str(payload.get("target", "") or "").strip()

    clauses: list[str] = []
    params: list[Any] = []
    if status != "all":
        clauses.append("status = ?")
        params.append(status)
    if target:
        clauses.append("target = ?")
        params.append(normalize_target(target))

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM reminders {where} ORDER BY id DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return {"ok": True, "count": len(rows), "reminders": [row_to_dict(row) for row in rows]}


def parse_reminder_id(value: Any) -> int:
    try:
        reminder_id = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("id must be a reminder id number") from exc
    if reminder_id <= 0:
        raise ValueError("id must be a positive reminder id")
    return reminder_id


def cancel_reminders(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    requester_phone, requester_name = validate_payload_requester(payload)
    reason = re.sub(r"\s+", " ", str(payload.get("reason", "") or "")).strip()
    if len(reason) > 180:
        reason = reason[:180]
    if not reason:
        reason = "Canceled from authorized WhatsApp request"
    audit = f"{reason} by {requester_name} ({requester_phone}) at {utc_iso(utc_now())}"

    if payload.get("id") not in (None, ""):
        reminder_id = parse_reminder_id(payload.get("id"))
        cursor = conn.execute(
            """
            UPDATE reminders
            SET status = 'canceled', last_error = ?
            WHERE id = ? AND status IN ('pending', 'failed')
            """,
            (audit, reminder_id),
        )
        conn.commit()
        return {"ok": True, "canceled": cursor.rowcount, "ids": [reminder_id] if cursor.rowcount else []}

    target = str(payload.get("target", "") or "").strip()
    if not target:
        raise ValueError("cancel requires either id or target")
    normalized_target = normalize_target(target)
    cursor = conn.execute(
        """
        UPDATE reminders
        SET status = 'canceled', last_error = ?
        WHERE target = ? AND status IN ('pending', 'failed')
        """,
        (audit, normalized_target),
    )
    conn.commit()
    return {"ok": True, "canceled": cursor.rowcount, "target": normalized_target}


def normalized_message(value: Any) -> str:
    message = re.sub(r"\s+", " ", str(value or "")).strip()
    if not message:
        raise ValueError("message is required")
    if len(message) > MAX_MESSAGE_CHARS:
        raise ValueError(f"message exceeds {MAX_MESSAGE_CHARS} characters")
    return message


def normalized_label(value: Any) -> str:
    label = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(label) > MAX_LABEL_CHARS:
        raise ValueError(f"label exceeds {MAX_LABEL_CHARS} characters")
    return label


def update_reminder(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    validate_payload_requester(payload)
    reminder_id = parse_reminder_id(payload.get("id"))
    row = conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
    if row is None:
        raise ValueError("reminder id not found")
    if str(row["status"]) not in EDITABLE_STATUSES:
        raise ValueError("only pending, failed, or canceled reminders can be updated")

    timezone_name = str(payload.get("timezone", row["timezone_name"]) or "Asia/Jakarta")
    target = normalize_target(str(payload.get("target", row["target"])))
    message = normalized_message(payload.get("message", row["message"]))
    label = normalized_label(payload.get("label", row["label"]))

    now = utc_now()
    recurrence = normalize_recurrence(str(payload.get("recurrence", row["recurrence"] or "once") or "once"))
    recurrence_times = str(row["recurrence_times"] or "")
    recurrence_windows = str(row["recurrence_windows"] or "")
    recurrence_until = parse_optional_until(
        str(payload.get("recurrence_until", row["recurrence_until"] or "") or ""),
        timezone_name,
    )

    schedule_changed = any(
        key in payload
        for key in (
            "due_at",
            "timezone",
            "recurrence",
            "daily_times",
            "times",
            "daily_windows",
            "windows",
            "recurrence_until",
        )
    )

    if recurrence == "daily" and not payload.get("daily_times") and payload.get("daily_windows"):
        recurrence = "daily_random"

    if recurrence == "daily":
        times_source = payload.get("daily_times", payload.get("times"))
        if times_source is None:
            if not recurrence_times:
                raise ValueError("daily recurrence requires daily_times")
            times_source = json.loads(recurrence_times)
        daily_times = parse_daily_times(times_source)
        recurrence_times = json.dumps(daily_times, ensure_ascii=False)
        recurrence_windows = ""
        due_dt = next_daily_due(daily_times, timezone_name, now)
        if recurrence_until and due_dt > parse_due_at(recurrence_until, timezone_name):
            raise ValueError("recurrence_until must be after the next scheduled daily reminder")
    elif recurrence == "daily_random":
        windows_source = payload.get("daily_windows", payload.get("windows"))
        if windows_source is None:
            if not recurrence_windows:
                raise ValueError("daily_random recurrence requires daily_windows")
            windows_source = json.loads(recurrence_windows)
        daily_windows = parse_daily_windows(windows_source)
        recurrence_times = ""
        recurrence_windows = json.dumps(daily_windows, ensure_ascii=False)
        due_dt = next_daily_window_due(daily_windows, timezone_name, now)
        if recurrence_until and due_dt > parse_due_at(recurrence_until, timezone_name):
            raise ValueError("recurrence_until must be after the next scheduled random daily reminder")
    else:
        recurrence_times = ""
        recurrence_windows = ""
        due_source = str(payload.get("due_at", row["due_at"]) or "")
        due_dt = parse_due_at(due_source, timezone_name)
        if due_dt <= now:
            raise ValueError("due_at must be in the future")

    activate = parse_bool(
        payload.get("activate"),
        default=(schedule_changed or str(row["status"]) != "canceled"),
    )
    if str(row["status"]) == "canceled" and not activate and schedule_changed:
        next_status = "canceled"
    elif str(row["status"]) == "canceled" and not activate:
        raise ValueError("canceled reminders require activate=true or a new schedule to resume")
    else:
        next_status = "pending"

    conn.execute(
        """
        UPDATE reminders
        SET target = ?, due_at = ?, timezone_name = ?, message = ?, label = ?,
            status = ?, attempts = 0, recurrence = ?, recurrence_times = ?,
            recurrence_windows = ?, recurrence_until = ?, last_error = ''
        WHERE id = ?
        """,
        (
            target,
            utc_iso(due_dt),
            timezone_name,
            message,
            label,
            next_status,
            recurrence,
            recurrence_times,
            recurrence_windows,
            recurrence_until,
            reminder_id,
        ),
    )
    conn.commit()
    return {
        "ok": True,
        "id": reminder_id,
        "target": target,
        "due_at": utc_iso(due_dt),
        "timezone": timezone_name,
        "status": next_status,
        "recurrence": recurrence,
        "daily_times": json.loads(recurrence_times) if recurrence_times else [],
        "daily_windows": json.loads(recurrence_windows) if recurrence_windows else [],
        "recurrence_until": recurrence_until,
    }


def decode_payload(encoded: str) -> dict[str, Any]:
    try:
        raw = base64.b64decode(encoded.encode("ascii"), validate=True).decode("utf-8")
        payload = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("payload must be base64-encoded JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("payload must decode to a JSON object")
    return payload


def main() -> int:
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add-json", help="Create a reminder from base64 JSON payload.")
    add.add_argument("--payload-b64", required=True)

    list_json = sub.add_parser("list-json", help="List reminders from base64 JSON payload.")
    list_json.add_argument("--payload-b64", required=True)

    cancel_json = sub.add_parser("cancel-json", help="Cancel reminders from base64 JSON payload.")
    cancel_json.add_argument("--payload-b64", required=True)

    update_json = sub.add_parser("update-json", help="Update a reminder from base64 JSON payload.")
    update_json.add_argument("--payload-b64", required=True)

    run = sub.add_parser("run-due", help="Send due reminders.")
    run.add_argument("--live", action="store_true")
    run.add_argument("--limit", type=int, default=MAX_DUE_PER_RUN)

    ls = sub.add_parser("list", help="List reminders.")
    ls.add_argument("--status", choices=["pending", "sent", "failed", "canceled", "all"], default="pending")
    ls.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()
    try:
        with connect() as conn:
            init_db(conn)
            if args.command == "add-json":
                result = create_reminder(conn, decode_payload(args.payload_b64))
            elif args.command == "list-json":
                result = list_reminders_for_payload(conn, decode_payload(args.payload_b64))
            elif args.command == "cancel-json":
                result = cancel_reminders(conn, decode_payload(args.payload_b64))
            elif args.command == "update-json":
                result = update_reminder(conn, decode_payload(args.payload_b64))
            elif args.command == "run-due":
                result = run_due(conn, dry_run=not args.live, limit=max(1, min(args.limit, MAX_DUE_PER_RUN)))
            elif args.command == "list":
                result = list_reminders(conn, status=args.status, limit=max(1, min(args.limit, 200)))
            else:
                raise ValueError("unsupported command")
    except Exception as exc:
        log_error(str(exc))
        print(text_result({"ok": False, "error": str(exc)}))
        return 1

    print(text_result(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
