#!/usr/bin/env python3
"""
yasmin_recovery_dashboard.py - local read-only recovery transcript dashboard.

This dashboard intentionally has no send, retry, delete, or mark-handled action.
It reads the existing guard intercepted-inbound queue and missed-reply watchdog
state so Shiffa, Rida, or the internal team can inspect recovery status without adding a new
production WhatsApp delivery path.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sqlite3
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


HOME = Path("/home/olekamole")
SCRIPTS_DIR = HOME / "scripts"
WATCHDOG_STATE_DIR = HOME / ".openclaw/yasmin-missed-reply-watchdog"
WATCHDOG_DB = WATCHDOG_STATE_DIR / "watchdog.sqlite"
WATCHDOG_LOG = WATCHDOG_STATE_DIR / "watchdog.log"
INTERCEPTED_QUEUE = HOME / ".openclaw/security/guard-intercepted-inbound.jsonl"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8791
DEFAULT_LIMIT = 80
MAX_LIMIT = 500


sys.path.insert(0, str(SCRIPTS_DIR))

try:
    import yasmin_missed_reply_watchdog as watchdog
except Exception as exc:  # pragma: no cover - surfaced in /healthz and /api/state
    watchdog = None  # type: ignore[assignment]
    WATCHDOG_IMPORT_ERROR = str(exc)
else:
    WATCHDOG_IMPORT_ERROR = ""


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def clamp_limit(value: str | None) -> int:
    if not value:
        return DEFAULT_LIMIT
    try:
        parsed = int(value)
    except ValueError:
        return DEFAULT_LIMIT
    return max(1, min(MAX_LIMIT, parsed))


def read_jsonl(path: Path, limit: int) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return []
    except OSError as exc:
        return [{"error": f"failed to read {path}: {exc}"}]
    records: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            records.append({"error": "invalid jsonl row", "raw": line[:500]})
            continue
        if isinstance(record, dict):
            records.append(record)
    records.reverse()
    return records


def db_rows(query: str, params: tuple[Any, ...], limit: int) -> list[dict[str, Any]]:
    if not WATCHDOG_DB.exists():
        return []
    try:
        conn = sqlite3.connect(WATCHDOG_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, (*params, limit)).fetchall()
        conn.close()
    except sqlite3.Error as exc:
        return [{"error": f"sqlite error: {exc}"}]
    return [dict(row) for row in rows]


def read_log_tail(limit: int) -> list[str]:
    try:
        lines = WATCHDOG_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return []
    except OSError as exc:
        return [f"failed to read watchdog log: {exc}"]
    return lines[-limit:]


def load_candidates(max_age_hours: int, include_handled: bool) -> list[dict[str, Any]]:
    if watchdog is None:
        return [{"error": f"watchdog import failed: {WATCHDOG_IMPORT_ERROR}"}]
    try:
        conn = watchdog.connect()
        current_ms = watchdog.now_ms()
        candidates = watchdog.load_candidates(
            min_age_ms=0,
            max_age_ms=max(1, max_age_hours) * 3_600_000,
            current_ms=current_ms,
        )
        rows: list[dict[str, Any]] = []
        for candidate in candidates:
            handled = watchdog.already_handled(conn, candidate)
            if handled and not include_handled:
                continue
            item = asdict(candidate)
            item["session_file"] = str(candidate.session_file) if candidate.session_file else ""
            item["handled"] = handled
            item["age_minutes"] = max(0, int((current_ms - candidate.last_user_ms) / 60_000))
            item["last_user_iso"] = watchdog.ms_to_iso(candidate.last_user_ms)
            rows.append(item)
        conn.close()
        rows.sort(key=lambda row: (row.get("handled", False), -int(row.get("last_user_ms") or 0)))
        return rows
    except Exception as exc:
        return [{"error": f"candidate scan failed: {exc}"}]


def queue_summary(records: list[dict[str, Any]]) -> dict[str, int]:
    recoverable = 0
    yasmin = 0
    direct = 0
    for record in records:
        if record.get("recoverable") is True:
            recoverable += 1
        if record.get("agentId") == "yasmin-zahirawedding":
            yasmin += 1
        if record.get("chatType") == "direct":
            direct += 1
    return {
        "total_loaded": len(records),
        "recoverable": recoverable,
        "yasmin": yasmin,
        "direct": direct,
    }


def build_state(limit: int, max_age_hours: int, include_handled: bool) -> dict[str, Any]:
    intercepted = read_jsonl(INTERCEPTED_QUEUE, limit)
    candidates = load_candidates(max_age_hours=max_age_hours, include_handled=include_handled)
    drafts = db_rows(
        """
        SELECT id, created_at, session_key, message_id, target, reply_text, mode
        FROM draft_log
        ORDER BY id DESC
        LIMIT ?
        """,
        (),
        limit,
    )
    handled = db_rows(
        """
        SELECT session_key, message_id, handled_at, target, reply_text, mode
        FROM handled_messages
        ORDER BY handled_at DESC
        LIMIT ?
        """,
        (),
        limit,
    )
    return {
        "ok": True,
        "generated_at": iso_now(),
        "paths": {
            "intercepted_queue": str(INTERCEPTED_QUEUE),
            "watchdog_db": str(WATCHDOG_DB),
            "watchdog_log": str(WATCHDOG_LOG),
        },
        "watchdog_import_error": WATCHDOG_IMPORT_ERROR,
        "queue_summary": queue_summary(intercepted),
        "counts": {
            "candidates": len(candidates),
            "drafts": len(drafts),
            "handled": len(handled),
            "intercepted_loaded": len(intercepted),
        },
        "candidates": candidates[:limit],
        "drafts": drafts,
        "handled": handled,
        "intercepted": intercepted,
        "log_tail": read_log_tail(min(limit, 120)),
    }


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def short_text(value: Any, length: int = 260) -> str:
    text = "" if value is None else str(value)
    text = text.strip()
    if len(text) <= length:
        return text
    return text[:length].rsplit(" ", 1)[0].strip() + "…"


def render_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return '<p class="muted">No rows.</p>'
    header = "".join(f"<th>{esc(label)}</th>" for key, label in columns)
    body_rows: list[str] = []
    for row in rows:
        cells: list[str] = []
        for key, _label in columns:
            value = row.get(key, "")
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            cells.append(f"<td>{esc(short_text(value))}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def render_html(state: dict[str, Any], limit: int, max_age_hours: int, include_handled: bool) -> bytes:
    candidates = render_table(
        state["candidates"],
        [
            ("last_user_iso", "Last inbound"),
            ("age_minutes", "Age min"),
            ("sender_category", "Sender type"),
            ("sender_name", "Sender"),
            ("target", "Target"),
            ("chat_type", "Chat"),
            ("handled", "Handled"),
            ("last_user_text", "Last message"),
        ],
    )
    drafts = render_table(
        state["drafts"],
        [
            ("created_at", "Created"),
            ("mode", "Mode"),
            ("target", "Target"),
            ("message_id", "Message ID"),
            ("reply_text", "Draft/reply"),
        ],
    )
    handled = render_table(
        state["handled"],
        [
            ("handled_at", "Handled"),
            ("mode", "Mode"),
            ("target", "Target"),
            ("message_id", "Message ID"),
            ("reply_text", "Reply"),
        ],
    )
    intercepted = render_table(
        state["intercepted"],
        [
            ("createdAt", "Created"),
            ("agentId", "Agent"),
            ("action", "Action"),
            ("recoverable", "Recoverable"),
            ("chatType", "Chat"),
            ("sender", "Sender"),
            ("target", "Target"),
            ("content", "Content"),
            ("reasons", "Reasons"),
        ],
    )
    log_tail = "\n".join(esc(line) for line in state["log_tail"])
    summary = state["queue_summary"]
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Yasmin Recovery Dashboard</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, -apple-system, Segoe UI, sans-serif; }}
    body {{ margin: 24px; line-height: 1.35; }}
    h1 {{ margin-bottom: 4px; }}
    h2 {{ margin-top: 28px; }}
    .muted {{ color: #777; }}
    .cards {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 18px 0; }}
    .card {{ border: 1px solid #9995; border-radius: 12px; padding: 12px 14px; min-width: 140px; }}
    .num {{ font-size: 1.7rem; font-weight: 700; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 0.92rem; }}
    th, td {{ border-bottom: 1px solid #9994; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ position: sticky; top: 0; background: Canvas; }}
    pre {{ border: 1px solid #9995; border-radius: 10px; padding: 12px; overflow: auto; max-height: 360px; }}
    form {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: end; margin: 16px 0; }}
    input {{ padding: 6px 8px; }}
    a {{ color: LinkText; }}
  </style>
</head>
<body>
  <h1>Yasmin Recovery Dashboard</h1>
  <div class="muted">Read-only local viewer. No WhatsApp send, retry, delete, or mark-handled action is exposed here.</div>
  <div class="muted">Generated: {esc(state["generated_at"])}</div>
  <form method="get">
    <label>Limit<br><input name="limit" type="number" min="1" max="{MAX_LIMIT}" value="{limit}"></label>
    <label>Max age hours<br><input name="max_age_hours" type="number" min="1" max="720" value="{max_age_hours}"></label>
    <label><input name="include_handled" type="checkbox" value="1" {"checked" if include_handled else ""}> Include handled candidates</label>
    <button type="submit">Refresh</button>
    <a href="/api/state?limit={limit}&max_age_hours={max_age_hours}&include_handled={1 if include_handled else 0}">JSON</a>
  </form>
  <div class="cards">
    <div class="card"><div class="num">{state["counts"]["candidates"]}</div><div>Candidates</div></div>
    <div class="card"><div class="num">{state["counts"]["drafts"]}</div><div>Drafts</div></div>
    <div class="card"><div class="num">{state["counts"]["handled"]}</div><div>Handled</div></div>
    <div class="card"><div class="num">{summary["intercepted_loaded"] if "intercepted_loaded" in summary else state["counts"]["intercepted_loaded"]}</div><div>Intercepted loaded</div></div>
    <div class="card"><div class="num">{summary["recoverable"]}</div><div>Recoverable intercepted</div></div>
  </div>
  <h2>Current recovery candidates</h2>
  {candidates}
  <h2>Watchdog drafts</h2>
  {drafts}
  <h2>Handled messages</h2>
  {handled}
  <h2>Intercepted inbound queue</h2>
  <p class="muted">{esc(state["paths"]["intercepted_queue"])}</p>
  {intercepted}
  <h2>Watchdog log tail</h2>
  <pre>{log_tail}</pre>
</body>
</html>
"""
    return html_doc.encode("utf-8")


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "YasminRecoveryDashboard/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {self.address_string()} {fmt % args}\n")

    def is_authorized(self, query: dict[str, list[str]]) -> bool:
        token = os.environ.get("YASMIN_RECOVERY_DASHBOARD_TOKEN", "").strip()
        if not token:
            return True
        provided = self.headers.get("X-Dashboard-Token", "").strip()
        if not provided:
            provided = query.get("token", [""])[0].strip()
        return provided == token

    def send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, status: HTTPStatus, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if not self.is_authorized(query):
            self.send_json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "invalid dashboard token"})
            return
        limit = clamp_limit(query.get("limit", [""])[0])
        try:
            max_age_hours = int(query.get("max_age_hours", ["168"])[0])
        except ValueError:
            max_age_hours = 168
        max_age_hours = max(1, min(720, max_age_hours))
        include_handled = query.get("include_handled", ["0"])[0] in {"1", "true", "yes", "on"}

        if parsed.path == "/healthz":
            self.send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "generated_at": iso_now(),
                    "watchdog_import_ok": watchdog is not None,
                    "watchdog_import_error": WATCHDOG_IMPORT_ERROR,
                },
            )
            return
        if parsed.path == "/api/state":
            self.send_json(HTTPStatus.OK, build_state(limit, max_age_hours, include_handled))
            return
        if parsed.path in {"/", "/index.html"}:
            state = build_state(limit, max_age_hours, include_handled)
            self.send_html(HTTPStatus.OK, render_html(state, limit, max_age_hours, include_handled))
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--once-json", action="store_true", help="Print one dashboard state JSON and exit.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--max-age-hours", type=int, default=168)
    parser.add_argument("--include-handled", action="store_true")
    args = parser.parse_args()

    if args.once_json:
        state = build_state(
            limit=max(1, min(MAX_LIMIT, args.limit)),
            max_age_hours=max(1, min(720, args.max_age_hours)),
            include_handled=args.include_handled,
        )
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"{iso_now()} Yasmin recovery dashboard listening on http://{args.host}:{args.port}")
    if not os.environ.get("YASMIN_RECOVERY_DASHBOARD_TOKEN", "").strip():
        print("Token auth disabled. Keep this bound to 127.0.0.1 or set YASMIN_RECOVERY_DASHBOARD_TOKEN.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
