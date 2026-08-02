#!/usr/bin/env python3
"""
openclaw_agent_dry_run.py - behavior dry-run helper for any OpenClaw agent.

Runs a local embedded OpenClaw agent turn without --deliver, channel, target,
reply-channel, or reply target. The prompt forbids tools and message sends, so
the result is a draft only and cannot trigger live channel delivery.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


OPENCLAW = Path("/home/olekamole/.npm-global/bin/openclaw")
SECRETS_ENV = Path("/home/olekamole/.openclaw/secrets.env")
DEFAULT_OUTPUT_DIR = Path("/home/olekamole/logs/openclaw-agent-dry-runs")


def now_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def read_text(path: Path, max_chars: int) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SystemExit(f"ERROR: cannot read facts file {path}: {exc}") from exc
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[TRUNCATED BY DRY RUN HELPER]\n"


def build_facts(args: argparse.Namespace) -> str:
    chunks: list[str] = []
    remaining = max(0, args.max_facts_chars)
    for raw_path in args.facts_file:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        chunk = read_text(path, remaining if remaining else 0)
        chunks.append(f"## Facts file: {path}\n{chunk}")
        remaining = max(0, remaining - len(chunk))
        if remaining == 0:
            break
    for fact in args.facts:
        chunks.append(f"## Inline fact\n{fact}")
    return "\n\n".join(chunks).strip()


def build_prompt(args: argparse.Namespace, facts: str) -> str:
    customers = "\n".join(f"- {item}" for item in args.customer)
    output_contract = (
        "Return only compact JSON. Use an array when there are multiple scenarios. "
        "Each item must have keys: scenario, draft. The draft is customer-facing text only."
    )
    if args.plain:
        output_contract = "Return only the draft customer-facing text. No commentary."

    prompt = f"""OpenClaw behavior dry run only.
Do not use tools.
Do not call the message tool.
Do not send messages.
Do not use WhatsApp, Telegram, Instagram, or any live channel.
This is a local evaluator run, not a production turn.
Apply the agent's current workspace instructions and style.
{output_contract}
"""
    if facts:
        prompt += f"\nVerified facts for this dry run:\n{facts}\n"
    prompt += f"\nCustomer scenario(s):\n{customers}\n"
    return prompt


def command_for(args: argparse.Namespace, prompt: str, session_id: str) -> list[str]:
    return [
        str(OPENCLAW),
        "agent",
        "--local",
        "--agent",
        args.agent,
        "--session-id",
        session_id,
        "--message",
        prompt,
        "--thinking",
        args.thinking,
        "--timeout",
        str(args.timeout),
        "--json",
    ]


def run_openclaw(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    quoted = " ".join(shlex.quote(part) for part in cmd)
    if SECRETS_ENV.exists():
        shell_cmd = f"set -a; source {shlex.quote(str(SECRETS_ENV))}; set +a; {quoted}"
    else:
        shell_cmd = quoted
    return subprocess.run(
        ["/bin/bash", "-lc", shell_cmd],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout + 30,
    )


def extract_json(stdout: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(stdout):
        if char != "{":
            continue
        try:
            payload, end = decoder.raw_decode(stdout[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "payloads" in payload and stdout[index + end :].strip().startswith("[agent]"):
            return payload
        if isinstance(payload, dict) and "payloads" in payload:
            return payload
    return None


def collect_text(payload: dict[str, Any] | None, stdout: str) -> str:
    if not payload:
        return stdout.strip()
    payloads = payload.get("payloads", [])
    texts = []
    for item in payloads:
        if isinstance(item, dict) and item.get("text"):
            texts.append(str(item["text"]))
    return "\n".join(texts).strip()


def has_delivery_risk(payload: dict[str, Any] | None, stdout: str) -> bool:
    haystack = stdout
    if payload:
        meta = payload.get("meta", {})
        tool_summary = meta.get("toolSummary", {})
        tools = tool_summary.get("tools", [])
        if "message" in tools:
            return True
    risk_markers = [
        "--deliver",
        "message send",
        '"toolName":"message"',
        '"name":"message"',
        "channel\":\"whatsapp",
        "reply-channel whatsapp",
    ]
    return any(marker in haystack for marker in risk_markers)


def write_report(args: argparse.Namespace, session_id: str, cmd: list[str], completed: subprocess.CompletedProcess[str], payload: dict[str, Any] | None, draft: str) -> Path:
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{session_id}.json"
    report = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "agent": args.agent,
        "session_id": session_id,
        "delivery": "disabled",
        "command": [part if part != cmd[cmd.index('--message') + 1] else "[PROMPT]" for part in cmd] if "--message" in cmd else cmd,
        "returncode": completed.returncode,
        "draft": draft,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", required=True, help="OpenClaw agent id, e.g. yasmin-zahirawedding")
    parser.add_argument("--customer", action="append", required=True, help="Customer scenario. Repeat for multiple scenarios.")
    parser.add_argument("--facts", action="append", default=[], help="Inline verified fact to inject.")
    parser.add_argument("--facts-file", action="append", default=[], help="Knowledge file to inject as verified facts.")
    parser.add_argument("--max-facts-chars", type=int, default=12000)
    parser.add_argument("--session-id", default="", help="Explicit session id. Default is generated.")
    parser.add_argument("--thinking", default="off")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--plain", action="store_true", help="Ask for plain draft text instead of JSON.")
    args = parser.parse_args()

    session_id = args.session_id or f"dryrun-{args.agent}-{now_stamp()}"
    facts = build_facts(args)
    prompt = build_prompt(args, facts)
    cmd = command_for(args, prompt, session_id)

    completed = run_openclaw(cmd, args.timeout)
    payload = extract_json(completed.stdout)
    draft = collect_text(payload, completed.stdout)
    report_path = write_report(args, session_id, cmd, completed, payload, draft)

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] agent={args.agent} session={session_id} returncode={completed.returncode}")
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] delivery=disabled command_has_deliver=no command_has_channel=no command_has_target=no")
    if has_delivery_risk(payload, completed.stdout):
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR: delivery-risk marker found in dry-run output", file=sys.stderr)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] report={report_path}")
        return 2
    if completed.returncode != 0:
        print(completed.stderr.strip() or completed.stdout.strip(), file=sys.stderr)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] report={report_path}")
        return completed.returncode
    print("[draft]")
    print(draft)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
