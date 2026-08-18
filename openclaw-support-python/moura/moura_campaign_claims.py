#!/usr/bin/env python3
"""
moura_campaign_claims.py - secure Mouru campaign winner claim intake.

This is a narrow handoff service for Moura Alexandra. It validates the current
campaign Google Doc, stores sensitive payout details locally, and notifies Mouru
business directors with a non-sensitive claim reference.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HOME = Path("/home/olekamole")
STATE_DIR = HOME / ".openclaw/moura-campaign-claims"
DB_PATH = STATE_DIR / "claims.sqlite"
LOG_FILE = STATE_DIR / "moura-campaign-claims.log"
CAMPAIGN_DOC_ID = "1vm9pfgcKN8oX3q0-YFFwq0fl0fXc1q8x8sMk7yr34NU"
CAMPAIGN_DOC_URL = f"https://docs.google.com/document/d/{CAMPAIGN_DOC_ID}/edit?tab=t.0"
GDRIVE_CREDENTIALS_PATH = HOME / ".openclaw/gdrive-credentials.json"
GDRIVE_TOKEN_PATH = HOME / ".openclaw/gdrive-token.json"
OPENCLAW = HOME / ".npm-global/bin/openclaw"

CHANNEL = "whatsapp"
ACCOUNT_ID = "moura-alexandra"
MAX_TEXT = 160

DIRECTOR_NOTIFY_TARGETS = {
    "Ibnu": ["+62REDACTED"],
    "Apin": ["+62REDACTED", "+62REDACTED"],
}
AUTHORIZED_DIRECTORS = {
    "+62REDACTED": "Ibnu",
    "+62REDACTED": "Ibnu",
    "+62REDACTED": "Apin",
    "+62REDACTED": "Apin",
}
CONTACT_STAGES = {
    "claimed_winner",
    "verified_story",
    "payout_requested",
    "claim_submitted",
    "voucher_delivered",
    "admin_verify_needed",
}

PHONE_RE = re.compile(r"^\+[1-9][0-9]{7,15}$")
ACCOUNT_RE = re.compile(r"^[0-9][0-9 \-]{4,33}$")


@dataclass
class Winner:
    rank: int
    status: str
    instagram_username: str
    whatsapp_phone: str
    prize_cash: int
    voucher_value: int
    voucher_code: str
    voucher_product_link: str
    claim_status: str


@dataclass
class Campaign:
    campaign_id: str
    status: str
    winner_claim_status: str
    payout_handoff_status: str
    voucher_handoff_status: str
    winners: dict[int, Winner]
    file_sha256: str
    source_url: str


def setup_logging() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(STATE_DIR, 0o700)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_FILE),
        ],
    )
    try:
        os.chmod(LOG_FILE, 0o600)
    except FileNotFoundError:
        pass


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
        raise ValueError("invalid requester_phone format")
    return phone


def validate_director(phone: str) -> str:
    normalized = normalize_phone(phone)
    name = AUTHORIZED_DIRECTORS.get(normalized)
    if not name:
        raise PermissionError("requester is not an authorized Mouru business director")
    return name


def normalize_optional_phone(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return normalize_phone(raw)


def clean_text(value: Any, field: str, max_len: int = MAX_TEXT) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        raise ValueError(f"{field} is required")
    if len(text) > max_len:
        raise ValueError(f"{field} exceeds {max_len} characters")
    return text


def normalize_account_number(value: str) -> str:
    raw = str(value or "").strip()
    if not ACCOUNT_RE.match(raw):
        raise ValueError("invalid account_number format")
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 5 or len(digits) > 34:
        raise ValueError("invalid account_number length")
    return digits


def mask_phone(phone: str) -> str:
    if len(phone) <= 6:
        return "***"
    return f"{phone[:4]}***{phone[-3:]}"


def mask_account(account_number: str) -> str:
    return f"***{account_number[-4:]}" if len(account_number) >= 4 else "***"


def parse_money(value: str) -> int:
    digits = re.sub(r"\D", "", value or "")
    return int(digits) if digits else 0


def parse_backtick_value(line: str) -> str:
    match = re.search(r"`([^`]+)`", line)
    if match:
        return match.group(1).strip()
    return line.split(":", 1)[1].strip() if ":" in line else ""


def read_json_file(path: Path, label: str) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"{label} is missing") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON") from exc


def http_json(url: str, data: dict[str, str] | None = None, token: str = "") -> dict[str, Any]:
    encoded = None
    headers = {"Accept": "application/json"}
    if data is not None:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=encoded, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")[:240]
        raise RuntimeError(f"Google API HTTP {exc.code}: {message}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Google API connection failed: {exc.reason}") from exc


def refresh_gdrive_token(credentials: dict[str, Any], token: dict[str, Any]) -> dict[str, Any]:
    oauth_config = credentials.get("installed") or credentials.get("web") or {}
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise PermissionError("Google Drive OAuth refresh token is missing")
    response = http_json(
        "https://oauth2.googleapis.com/token",
        {
            "client_id": str(oauth_config.get("client_id", "")),
            "client_secret": str(oauth_config.get("client_secret", "")),
            "refresh_token": str(refresh_token),
            "grant_type": "refresh_token",
        },
    )
    next_token = dict(token)
    next_token["access_token"] = response.get("access_token", "")
    next_token["token_type"] = response.get("token_type", "Bearer")
    next_token["expiry_date"] = int(time.time() * 1000) + int(response.get("expires_in", 3600)) * 1000
    GDRIVE_TOKEN_PATH.write_text(json.dumps(next_token, indent=2), encoding="utf-8")
    os.chmod(GDRIVE_TOKEN_PATH, 0o600)
    return next_token


def get_gdrive_access_token() -> str:
    credentials = read_json_file(GDRIVE_CREDENTIALS_PATH, "Google Drive OAuth credentials")
    token = read_json_file(GDRIVE_TOKEN_PATH, "Google Drive OAuth token")
    access_token = str(token.get("access_token") or "")
    expiry_date = int(token.get("expiry_date") or 0)
    if not access_token or expiry_date <= int(time.time() * 1000) + 60000:
        token = refresh_gdrive_token(credentials, token)
        access_token = str(token.get("access_token") or "")
    if not access_token:
        raise PermissionError("Google Drive OAuth access token is missing")
    return access_token


def fetch_campaign_text() -> str:
    query = urllib.parse.urlencode({"mimeType": "text/plain"})
    url = f"https://www.googleapis.com/drive/v3/files/{CAMPAIGN_DOC_ID}/export?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {get_gdrive_access_token()}",
            "Accept": "text/plain",
            "User-Agent": "moura-campaign-claims/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")[:240]
        raise RuntimeError(f"Google Drive export HTTP {exc.code}: {message}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Google Drive export failed: {exc.reason}") from exc


def get_campaign_field(stripped: str, field: str) -> str:
    normalized = stripped.removeprefix("- ").strip()
    if normalized.lower().startswith(f"{field.lower()}:"):
        return parse_backtick_value(normalized)
    return ""


def parse_campaign(content: str | None = None) -> Campaign:
    content = fetch_campaign_text() if content is None else content
    file_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    lines = content.splitlines()

    campaign_id = ""
    status = ""
    winner_claim_status = ""
    payout_handoff_status = ""
    voucher_handoff_status = ""
    winners: dict[int, dict[str, str]] = {}
    current_rank: int | None = None

    for line in lines:
        stripped = line.strip()
        if current_rank is None:
            campaign_id = get_campaign_field(stripped, "Campaign id") or campaign_id
            status = (get_campaign_field(stripped, "Status") or status).lower()
            winner_claim_status = (get_campaign_field(stripped, "Winner claim status") or winner_claim_status).lower()
            payout_handoff_status = (
                get_campaign_field(stripped, "Payout handoff status")
                or get_campaign_field(stripped, "Payout handoff")
                or payout_handoff_status
            ).lower()
            voucher_handoff_status = (
                get_campaign_field(stripped, "Voucher handoff status")
                or get_campaign_field(stripped, "Voucher handoff")
                or voucher_handoff_status
            ).lower()

        winner_match = re.match(r"^Winner\s+([1-9][0-9]*):$", stripped)
        numbered_winner_match = re.match(r"^([1-9][0-9]*)\.\s+(@?[A-Za-z0-9._]+)\s*$", stripped)
        if winner_match:
            current_rank = int(winner_match.group(1))
            winners[current_rank] = {}
            continue
        if numbered_winner_match:
            current_rank = int(numbered_winner_match.group(1))
            winners[current_rank] = {
                "instagram username": numbered_winner_match.group(2),
                "status": "announced",
            }
            continue

        if current_rank is not None and stripped.startswith("- ") and ":" in stripped:
            key, value = stripped[2:].split(":", 1)
            normalized_key = key.strip().lower()
            if normalized_key == "cash":
                normalized_key = "prize cash"
            elif normalized_key == "voucher":
                normalized_key = "voucher value"
            elif normalized_key == "code":
                normalized_key = "voucher code"
            winners[current_rank][normalized_key] = parse_backtick_value(stripped)
            continue

        if current_rank is not None and stripped.startswith("http"):
            for winner_data in winners.values():
                winner_data.setdefault("voucher product link", stripped)

    parsed_winners: dict[int, Winner] = {}
    for rank, data in winners.items():
        parsed_winners[rank] = Winner(
            rank=rank,
            status=data.get("status", "").strip().lower(),
            instagram_username=data.get("instagram username", "").strip(),
            whatsapp_phone=normalize_optional_phone(data.get("whatsapp phone", "")),
            prize_cash=parse_money(data.get("prize cash", "")),
            voucher_value=parse_money(data.get("voucher value", "")),
            voucher_code=data.get("voucher code", "").strip(),
            voucher_product_link=data.get("voucher product link", "").strip(),
            claim_status=data.get("claim status", "").strip().lower(),
        )

    if not campaign_id:
        raise ValueError("campaign id is missing in current campaign Google Doc")
    return Campaign(
        campaign_id=campaign_id,
        status=status,
        winner_claim_status=winner_claim_status,
        payout_handoff_status=payout_handoff_status,
        voucher_handoff_status=voucher_handoff_status,
        winners=parsed_winners,
        file_sha256=file_sha,
        source_url=CAMPAIGN_DOC_URL,
    )


def current_campaign() -> dict[str, Any]:
    content = fetch_campaign_text()
    campaign = parse_campaign(content)
    return {
        "ok": True,
        "source": "google_doc",
        "source_url": campaign.source_url,
        "document_id": CAMPAIGN_DOC_ID,
        "sha256": campaign.file_sha256,
        "campaign_id": campaign.campaign_id,
        "campaign_status": campaign.status,
        "winner_claim_status": campaign.winner_claim_status,
        "payout_handoff_status": campaign.payout_handoff_status,
        "voucher_handoff_status": campaign.voucher_handoff_status,
        "winners_count": len(campaign.winners),
        "campaign_text": content,
    }


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
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            campaign_file_sha256 TEXT NOT NULL,
            winner_rank INTEGER NOT NULL,
            winner_instagram_username TEXT NOT NULL,
            requester_phone TEXT NOT NULL,
            source_chat_id TEXT NOT NULL,
            bank_name TEXT NOT NULL,
            account_holder_name TEXT NOT NULL,
            account_number TEXT NOT NULL,
            account_number_last4 TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'submitted',
            notification_status TEXT NOT NULL DEFAULT '',
            notified_targets TEXT NOT NULL DEFAULT '',
            local_note TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_claims_unique_active
        ON claims(campaign_id, winner_rank, requester_phone)
        WHERE status IN ('submitted', 'reviewing', 'paid')
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            winner_rank INTEGER NOT NULL DEFAULT 0,
            instagram_username TEXT NOT NULL DEFAULT '',
            requester_phone TEXT NOT NULL,
            source_chat_id TEXT NOT NULL,
            chat_kind TEXT NOT NULL,
            stage TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            claim_id INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_unique
        ON contacts(campaign_id, requester_phone, instagram_username)
        """
    )
    conn.commit()


def validate_against_campaign(payload: dict[str, Any], campaign: Campaign) -> tuple[int, Winner]:
    campaign_id = clean_text(payload.get("campaign_id"), "campaign_id", 120)
    if campaign_id != campaign.campaign_id:
        raise ValueError("campaign_id does not match current campaign")
    if campaign.status != "ended":
        raise PermissionError("campaign status is not ended")
    if campaign.winner_claim_status != "open":
        raise PermissionError("winner claim status is not open")
    if campaign.payout_handoff_status != "enabled":
        raise PermissionError("payout handoff status is not enabled")

    chat_kind = clean_text(payload.get("chat_kind"), "chat_kind", 20).lower()
    if chat_kind != "direct":
        raise PermissionError("campaign claim submission is DM-only")

    rank = int(payload.get("winner_rank", 0))
    winner = campaign.winners.get(rank)
    if not winner:
        raise ValueError("winner_rank is not listed in current campaign")
    if winner.status != "announced":
        raise PermissionError("winner is not announced")
    if winner.claim_status != "open":
        raise PermissionError("winner claim status is not open")
    if winner.prize_cash <= 0:
        raise PermissionError("this winner has no cash payout to submit")
    if not winner.whatsapp_phone:
        raise PermissionError("winner WhatsApp phone is not configured")

    requester_phone = normalize_phone(str(payload.get("requester_phone", "")))
    if requester_phone != winner.whatsapp_phone:
        raise PermissionError("requester phone does not match listed winner")

    supplied_ig = re.sub(r"^@", "", str(payload.get("instagram_username", "") or "").strip()).lower()
    listed_ig = re.sub(r"^@", "", winner.instagram_username.strip()).lower()
    if listed_ig and supplied_ig and supplied_ig != listed_ig:
        raise PermissionError("instagram_username does not match listed winner")
    return rank, winner


def notify_directors(claim_id: int, campaign: Campaign, winner: Winner, requester_phone: str, bank_name: str, account_number: str) -> dict[str, Any]:
    message = (
        "Moura campaign claim received.\n"
        f"Claim ID: {claim_id}\n"
        f"Campaign: {campaign.campaign_id}\n"
        f"Winner: #{winner.rank}\n"
        f"Winner phone: {mask_phone(requester_phone)}\n"
        f"Bank: {bank_name}\n"
        f"Account: {mask_account(account_number)}\n"
        "Full payout details are stored locally in the secure Moura claim store."
    )
    results = []
    for director, targets in DIRECTOR_NOTIFY_TARGETS.items():
        for target in targets:
            started = time.time()
            try:
                completed = subprocess.run(
                    [
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
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                results.append(
                    {
                        "director": director,
                        "target": target,
                        "ok": completed.returncode == 0,
                        "duration_ms": int((time.time() - started) * 1000),
                        "error": "" if completed.returncode == 0 else (completed.stderr.strip() or completed.stdout.strip())[:240],
                    }
                )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    {
                        "director": director,
                        "target": target,
                        "ok": False,
                        "duration_ms": int((time.time() - started) * 1000),
                        "error": str(exc)[:240],
                    }
                )
    return {
        "ok": any(item["ok"] for item in results),
        "results": results,
    }


def submit_claim(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    campaign = parse_campaign()
    rank, winner = validate_against_campaign(payload, campaign)
    requester_phone = normalize_phone(str(payload.get("requester_phone", "")))
    source_chat_id = clean_text(payload.get("source_chat_id", requester_phone), "source_chat_id", 120)
    bank_name = clean_text(payload.get("bank_name"), "bank_name", 80)
    account_holder_name = clean_text(payload.get("account_holder_name"), "account_holder_name", 120)
    account_number = normalize_account_number(str(payload.get("account_number", "")))
    winner_ig = winner.instagram_username or clean_text(payload.get("instagram_username", ""), "instagram_username", 120)

    now = utc_iso(utc_now())
    try:
        cursor = conn.execute(
            """
            INSERT INTO claims (
                created_at, campaign_id, campaign_file_sha256, winner_rank,
                winner_instagram_username, requester_phone, source_chat_id,
                bank_name, account_holder_name, account_number,
                account_number_last4, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'submitted')
            """,
            (
                now,
                campaign.campaign_id,
                campaign.file_sha256,
                rank,
                winner_ig,
                requester_phone,
                source_chat_id,
                bank_name,
                account_holder_name,
                account_number,
                account_number[-4:],
            ),
        )
        conn.commit()
        claim_id = int(cursor.lastrowid)
        duplicate = False
    except sqlite3.IntegrityError:
        row = conn.execute(
            """
            SELECT id FROM claims
            WHERE campaign_id = ? AND winner_rank = ? AND requester_phone = ?
              AND status IN ('submitted', 'reviewing', 'paid')
            ORDER BY id DESC
            LIMIT 1
            """,
            (campaign.campaign_id, rank, requester_phone),
        ).fetchone()
        if not row:
            raise
        claim_id = int(row["id"])
        duplicate = True

    notify_result = {"ok": False, "results": []}
    if not duplicate:
        notify_result = notify_directors(claim_id, campaign, winner, requester_phone, bank_name, account_number)
        conn.execute(
            """
            UPDATE claims
            SET notification_status = ?, notified_targets = ?
            WHERE id = ?
            """,
            (
                "sent" if notify_result["ok"] else "failed",
                json.dumps(notify_result["results"], ensure_ascii=False),
                claim_id,
            ),
        )
        conn.commit()
    record_contact(
        conn,
        {
            "campaign_id": campaign.campaign_id,
            "requester_phone": requester_phone,
            "source_chat_id": source_chat_id,
            "chat_kind": "direct",
            "winner_rank": rank,
            "instagram_username": winner_ig,
            "stage": "claim_submitted",
            "note": "Cash-prize claim submitted",
            "claim_id": claim_id,
        },
        validate_requester=False,
    )

    logging.info(
        "claim submitted id=%s campaign=%s winner_rank=%s requester=%s duplicate=%s notified=%s",
        claim_id,
        campaign.campaign_id,
        rank,
        mask_phone(requester_phone),
        duplicate,
        notify_result["ok"],
    )
    return {
        "ok": True,
        "claim_id": claim_id,
        "duplicate": duplicate,
        "campaign_id": campaign.campaign_id,
        "winner_rank": rank,
        "requester_phone_masked": mask_phone(requester_phone),
        "account_number_masked": mask_account(account_number),
        "notified_directors": bool(notify_result["ok"]) or duplicate,
    }


def normalize_instagram_username(value: Any) -> str:
    username = re.sub(r"^@", "", str(value or "").strip()).lower()
    username = re.sub(r"[^a-z0-9._]", "", username)
    if len(username) > 80:
        username = username[:80]
    return username


def normalize_contact_stage(value: Any) -> str:
    stage = str(value or "claimed_winner").strip().lower()
    if stage not in CONTACT_STAGES:
        raise ValueError("stage is not allowed")
    return stage


def record_contact(conn: sqlite3.Connection, payload: dict[str, Any], validate_requester: bool = True) -> dict[str, Any]:
    campaign = parse_campaign()
    if validate_requester:
        requester_phone = normalize_phone(str(payload.get("requester_phone", "")))
    else:
        requester_phone = normalize_phone(str(payload.get("requester_phone", "")))
    campaign_id = clean_text(payload.get("campaign_id", campaign.campaign_id), "campaign_id", 120)
    if campaign_id != campaign.campaign_id:
        raise ValueError("campaign_id does not match current campaign")
    chat_kind = clean_text(payload.get("chat_kind", "direct"), "chat_kind", 20).lower()
    if chat_kind not in {"direct", "group"}:
        raise ValueError("chat_kind must be direct or group")
    source_chat_id = clean_text(payload.get("source_chat_id", requester_phone), "source_chat_id", 120)
    stage = normalize_contact_stage(payload.get("stage"))
    note = re.sub(r"\s+", " ", str(payload.get("note", "") or "")).strip()
    if len(note) > 220:
        note = note[:220]
    instagram_username = normalize_instagram_username(payload.get("instagram_username"))
    try:
        winner_rank = int(payload.get("winner_rank", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("winner_rank must be a number") from exc
    if winner_rank and winner_rank not in campaign.winners:
        raise ValueError("winner_rank is not listed in current campaign")
    claim_id = int(payload.get("claim_id", 0) or 0)
    now = utc_iso(utc_now())

    cursor = conn.execute(
        """
        INSERT INTO contacts (
            created_at, updated_at, campaign_id, winner_rank, instagram_username,
            requester_phone, source_chat_id, chat_kind, stage, note, claim_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(campaign_id, requester_phone, instagram_username)
        DO UPDATE SET
            updated_at = excluded.updated_at,
            winner_rank = CASE WHEN excluded.winner_rank != 0 THEN excluded.winner_rank ELSE contacts.winner_rank END,
            source_chat_id = excluded.source_chat_id,
            chat_kind = excluded.chat_kind,
            stage = excluded.stage,
            note = excluded.note,
            claim_id = CASE WHEN excluded.claim_id != 0 THEN excluded.claim_id ELSE contacts.claim_id END
        """,
        (
            now,
            now,
            campaign_id,
            winner_rank,
            instagram_username,
            requester_phone,
            source_chat_id,
            chat_kind,
            stage,
            note,
            claim_id,
        ),
    )
    conn.commit()
    return {
        "ok": True,
        "contact_id": int(cursor.lastrowid or 0),
        "campaign_id": campaign_id,
        "winner_rank": winner_rank,
        "instagram_username": instagram_username,
        "requester_phone_masked": mask_phone(requester_phone),
        "stage": stage,
    }


def contact_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "updated_at": str(row["updated_at"]),
        "campaign_id": str(row["campaign_id"]),
        "winner_rank": int(row["winner_rank"] or 0),
        "instagram_username": str(row["instagram_username"] or ""),
        "requester_phone_masked": mask_phone(str(row["requester_phone"] or "")),
        "chat_kind": str(row["chat_kind"] or ""),
        "stage": str(row["stage"] or ""),
        "note": str(row["note"] or ""),
        "claim_id": int(row["claim_id"] or 0),
    }


def claim_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "created_at": str(row["created_at"]),
        "claim_id": int(row["id"]),
        "campaign_id": str(row["campaign_id"]),
        "winner_rank": int(row["winner_rank"]),
        "instagram_username": str(row["winner_instagram_username"]),
        "requester_phone_masked": mask_phone(str(row["requester_phone"])),
        "bank_name": str(row["bank_name"]),
        "account_holder_name": str(row["account_holder_name"]),
        "account_number_masked": mask_account(str(row["account_number"])),
        "status": str(row["status"]),
        "notification_status": str(row["notification_status"]),
    }


def claim_status(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    requester_name = validate_director(str(payload.get("requester_phone", "")))
    campaign = parse_campaign()
    campaign_id = clean_text(payload.get("campaign_id", campaign.campaign_id), "campaign_id", 120)
    if campaign_id != campaign.campaign_id:
        raise ValueError("campaign_id does not match current campaign")
    contacts = conn.execute(
        """
        SELECT * FROM contacts
        WHERE campaign_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 50
        """,
        (campaign_id,),
    ).fetchall()
    claims = conn.execute(
        """
        SELECT * FROM claims
        WHERE campaign_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 50
        """,
        (campaign_id,),
    ).fetchall()
    winner_summary = [
        {
            "winner_rank": winner.rank,
            "instagram_username": winner.instagram_username,
            "claim_status": winner.claim_status,
            "prize_cash": winner.prize_cash,
            "voucher_value": winner.voucher_value,
        }
        for winner in campaign.winners.values()
    ]
    return {
        "ok": True,
        "requested_by": requester_name,
        "campaign_id": campaign_id,
        "campaign_status": campaign.status,
        "winner_claim_status": campaign.winner_claim_status,
        "contacts_count": len(contacts),
        "claims_count": len(claims),
        "contacts": [contact_row(row) for row in contacts],
        "claims": [claim_row(row) for row in claims],
        "winners": winner_summary,
    }


def load_payload_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.payload_b64:
        decoded = base64.b64decode(args.payload_b64.encode("utf-8")).decode("utf-8")
        return json.loads(decoded)
    if args.payload:
        return json.loads(args.payload)
    raise ValueError("payload is required")


def main() -> int:
    os.umask(0o077)
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    submit = sub.add_parser("submit-json", help="Submit a campaign claim from JSON")
    submit.add_argument("--payload", help="JSON payload")
    submit.add_argument("--payload-b64", help="Base64-encoded JSON payload")

    contact = sub.add_parser("contact-json", help="Record a non-sensitive campaign winner contact")
    contact.add_argument("--payload", help="JSON payload")
    contact.add_argument("--payload-b64", help="Base64-encoded JSON payload")

    status = sub.add_parser("status-json", help="Return campaign contact and claim status for directors")
    status.add_argument("--payload", help="JSON payload")
    status.add_argument("--payload-b64", help="Base64-encoded JSON payload")

    current = sub.add_parser("current-json", help="Return current campaign source text from Google Docs")
    current.add_argument("--payload", help="Ignored JSON payload")
    current.add_argument("--payload-b64", help="Ignored Base64-encoded JSON payload")

    args = parser.parse_args()
    try:
        conn = connect()
        init_db(conn)
        if args.command == "submit-json":
            payload = load_payload_from_args(args)
            print(text_result(submit_claim(conn, payload)))
            return 0
        if args.command == "contact-json":
            payload = load_payload_from_args(args)
            print(text_result(record_contact(conn, payload)))
            return 0
        if args.command == "status-json":
            payload = load_payload_from_args(args)
            print(text_result(claim_status(conn, payload)))
            return 0
        if args.command == "current-json":
            print(text_result(current_campaign()))
            return 0
        raise ValueError("unknown command")
    except Exception as exc:  # noqa: BLE001
        logging.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
