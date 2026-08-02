#!/usr/bin/env python3
"""
yasmin_calendar_reminders.py - send due Yasmin calendar reminders to approved targets.

The internal calendar service owns event/reminder creation and due marking. This
dispatcher only consumes due Yasmin reminders, sends them through Yasmin's
WhatsApp account to Shiffa or Rida as fallback, then updates reminder status
for auditability.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


HOME = Path("/home/olekamole")
DB_PATH = HOME / ".openclaw/internal-calendar/calendar.sqlite"
STATE_DIR = HOME / ".openclaw/yasmin-calendar-reminders"
LOG_FILE = STATE_DIR / "yasmin-calendar-reminders.log"
OPENCLAW = HOME / ".npm-global/bin/openclaw"

AGENT_ID = "yasmin-zahirawedding"
CHANNEL = "whatsapp"
ACCOUNT_ID = "yasmin-zahirawedding"
PRIMARY_AUTHORITY_TARGET = "+6285774835882"
FALLBACK_AUTHORITY_TARGET = "+6285640095210"
ALLOWED_TARGETS = {
    PRIMARY_AUTHORITY_TARGET,
    FALLBACK_AUTHORITY_TARGET,
}
TZ = ZoneInfo("Asia/Jakarta")
MAX_DUE_PER_RUN = 10


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


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(dt: datetime | None = None) -> str:
    value = dt or utc_now()
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    raw = str(value or "").strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def local_time_label(value: str) -> str:
    dt = parse_utc(value).astimezone(TZ)
    return dt.strftime("%A, %d %B %Y %H:%M WIB")


def due_reminders(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            r.*,
            e.title AS event_title,
            e.description AS event_description,
            e.location AS event_location,
            e.start_at AS event_start_at,
            e.end_at AS event_end_at
        FROM reminders r
        JOIN events e ON e.id = r.event_id
        WHERE r.agent_id = ?
          AND r.status = 'due'
        ORDER BY r.remind_at ASC, r.id ASC
        LIMIT ?
        """,
        (AGENT_ID, max(1, min(limit, MAX_DUE_PER_RUN))),
    ).fetchall()


def mark_attempt(conn: sqlite3.Connection, reminder_id: str) -> None:
    conn.execute(
        "UPDATE reminders SET attempts = attempts + 1, updated_at = ? WHERE id = ?",
        (utc_iso(), reminder_id),
    )
    conn.commit()


def mark_sent(conn: sqlite3.Connection, reminder_id: str) -> None:
    now = utc_iso()
    conn.execute(
        """
        UPDATE reminders
        SET status = 'sent', sent_at = ?, updated_at = ?, last_error = ''
        WHERE id = ?
        """,
        (now, now, reminder_id),
    )
    conn.commit()


def mark_failed(conn: sqlite3.Connection, reminder: sqlite3.Row, error: str) -> None:
    attempts = int(reminder["attempts"] or 0) + 1
    next_status = "failed" if attempts >= 3 else "due"
    conn.execute(
        """
        UPDATE reminders
        SET status = ?, last_error = ?, updated_at = ?
        WHERE id = ?
        """,
        (next_status, error[:500], utc_iso(), reminder["id"]),
    )
    conn.commit()


def build_message(reminder: sqlite3.Row) -> str:
    title = str(reminder["event_title"] or "Appointment").strip()
    stored_message = str(reminder["message"] or "").strip()
    location = str(reminder["event_location"] or "").strip()
    start_label = local_time_label(str(reminder["event_start_at"]))
    end_label = local_time_label(str(reminder["event_end_at"]))

    lines = [
        "Reminder Yasmin",
        "",
        stored_message or title,
        f"Jadwal: {title}",
        f"Waktu: {start_label} - {end_label}",
    ]
    if location:
        lines.append(f"Lokasi: {location}")
    return "\n".join(lines)


def send_openclaw(message: str, target: str, dry_run: bool) -> tuple[bool, str]:
    cmd = [
        str(OPENCLAW),
        "message",
        "send",
        "--channel",
        CHANNEL,
        "--account",
        ACCOUNT_ID,
        "--target",
        target,
        "--message",
        message,
        "--json",
    ]
    if dry_run:
        cmd.append("--dry-run")

    completed = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    if completed.returncode == 0:
        return True, (completed.stdout or "").strip()
    detail = (completed.stderr or completed.stdout or "message send failed").strip().replace("\n", " ")
    return False, detail


def dispatch(conn: sqlite3.Connection, dry_run: bool, limit: int) -> dict[str, Any]:
    reminders = due_reminders(conn, limit)
    sent = 0
    failed = 0
    for reminder in reminders:
        reminder_id = str(reminder["id"])
        target = str(reminder["target"] or "").strip()
        if not target:
            target = PRIMARY_AUTHORITY_TARGET
        if target.endswith("@g.us"):
            failed += 1
            mark_failed(conn, reminder, "Yasmin calendar reminders do not send to WhatsApp groups")
            logging.error("blocked group reminder id=%s target=%s", reminder_id, target)
            continue
        if target not in ALLOWED_TARGETS:
            failed += 1
            mark_failed(conn, reminder, "Yasmin calendar reminders may only target approved Zahira recipients")
            logging.error("blocked reminder id=%s unexpected_target=%s", reminder_id, target)
            continue

        message = build_message(reminder)
        mark_attempt(conn, reminder_id)
        ok, detail = send_openclaw(message, target=target, dry_run=dry_run)
        if not ok and target == PRIMARY_AUTHORITY_TARGET:
            logging.warning(
                "primary reminder delivery failed id=%s; trying Rida fallback",
                reminder_id,
            )
            ok, detail = send_openclaw(
                message,
                target=FALLBACK_AUTHORITY_TARGET,
                dry_run=dry_run,
            )
            if ok:
                target = FALLBACK_AUTHORITY_TARGET
        if ok:
            sent += 1
            logging.info("%ssent reminder id=%s target=%s", "DRY-RUN " if dry_run else "", reminder_id, target)
            if not dry_run:
                mark_sent(conn, reminder_id)
        else:
            failed += 1
            logging.error("failed reminder id=%s: %s", reminder_id, detail)
            if not dry_run:
                mark_failed(conn, reminder, detail)

    logging.info("done due=%s sent=%s failed=%s mode=%s", len(reminders), sent, failed, "dry-run" if dry_run else "live")
    return {"ok": failed == 0, "due": len(reminders), "sent": sent, "failed": failed}


def main() -> int:
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", help="Run one dispatch cycle.")
    parser.add_argument("--dry-run", action="store_true", help="Preview sends without changing sent status.")
    parser.add_argument("--live", action="store_true", help="Send live WhatsApp reminders.")
    parser.add_argument("--limit", type=int, default=MAX_DUE_PER_RUN)
    args = parser.parse_args()

    if args.command != "run-due":
        parser.error("command must be run-due")
    if args.live and args.dry_run:
        parser.error("--live and --dry-run are mutually exclusive")
    if not args.live and not args.dry_run:
        parser.error("choose --dry-run or --live")
    if not DB_PATH.exists():
        logging.error("calendar database not found: %s", DB_PATH)
        return 1
    if not OPENCLAW.exists():
        logging.error("OpenClaw CLI not found: %s", OPENCLAW)
        return 1

    try:
        with connect() as conn:
            result = dispatch(conn, dry_run=not args.live, limit=args.limit)
    except Exception as exc:
        logging.exception("dispatcher failed: %s", exc)
        return 1
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
