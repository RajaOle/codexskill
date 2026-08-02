#!/usr/bin/env python3
"""
openclaw_agent_load_test.py - dry-run OpenClaw agent concurrency test.

This script invokes local OpenClaw agent turns without --deliver, so it does not
send replies to WhatsApp, Instagram, or any other live channel.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path


OPENCLAW = "/home/olekamole/.npm-global/bin/openclaw"


@dataclass
class SystemSample:
    ts: str
    mem_available_kib: int
    swap_free_kib: int
    load1: float
    gateway_rss_kib: int


@dataclass
class TurnResult:
    index: int
    session_id: str
    ok: bool
    elapsed_s: float
    returncode: int
    stdout_tail: str
    stderr_tail: str


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def read_meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    with open("/proc/meminfo", "r", encoding="utf-8") as handle:
        for line in handle:
            key, raw_value = line.split(":", 1)
            parts = raw_value.strip().split()
            if parts and parts[0].isdigit():
                values[key] = int(parts[0])
    return values


def gateway_rss_kib() -> int:
    try:
        completed = subprocess.run(
            ["pgrep", "-f", "openclaw/dist/index.js gateway"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.SubprocessError:
        return 0
    rss_total = 0
    for pid in completed.stdout.split():
        status_path = Path("/proc") / pid / "status"
        try:
            with open(status_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        if len(parts) >= 2 and parts[1].isdigit():
                            rss_total += int(parts[1])
                        break
        except OSError:
            continue
    return rss_total


def sample_system() -> SystemSample:
    meminfo = read_meminfo()
    load1, _, _ = os.getloadavg()
    return SystemSample(
        ts=now(),
        mem_available_kib=meminfo.get("MemAvailable", 0),
        swap_free_kib=meminfo.get("SwapFree", 0),
        load1=load1,
        gateway_rss_kib=gateway_rss_kib(),
    )


def tail_text(value: str, limit: int = 700) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[-limit:]


def run_turn(agent: str, run_id: str, index: int, timeout: int, thinking: str) -> TurnResult:
    session_id = f"loadtest-{run_id}-{agent}-{index:03d}"
    message = (
        "OpenClaw dry-run capacity test. Do not use tools. Do not send messages. "
        "Reply with exactly: OK"
    )
    cmd = [
        OPENCLAW,
        "agent",
        "--agent",
        agent,
        "--session-id",
        session_id,
        "--message",
        message,
        "--thinking",
        thinking,
        "--timeout",
        str(timeout),
        "--json",
    ]
    started = time.monotonic()
    completed = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout + 15,
    )
    elapsed = time.monotonic() - started
    return TurnResult(
        index=index,
        session_id=session_id,
        ok=completed.returncode == 0,
        elapsed_s=round(elapsed, 3),
        returncode=completed.returncode,
        stdout_tail=tail_text(completed.stdout),
        stderr_tail=tail_text(completed.stderr),
    )


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1)))
    return round(ordered[idx], 3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", default="yasmin-zahirawedding")
    parser.add_argument(
        "--agents",
        default="",
        help="Comma-separated agent ids. If set, turns are distributed round-robin.",
    )
    parser.add_argument("--concurrency", default="1,2,4,6,8")
    parser.add_argument("--thinking", default="off")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output", default="/home/olekamole/logs/openclaw_agent_load_test.json")
    args = parser.parse_args()

    run_id = time.strftime("%Y%m%d-%H%M%S")
    agents = [part.strip() for part in args.agents.split(",") if part.strip()] or [args.agent]
    levels = [int(part.strip()) for part in args.concurrency.split(",") if part.strip()]
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report: dict[str, object] = {
        "run_id": run_id,
        "started_at": now(),
        "agents": agents,
        "delivery": "disabled (--deliver omitted)",
        "thinking": args.thinking,
        "levels": [],
    }

    print(f"[{now()}] starting dry-run load test agents={agents} levels={levels}")
    for level in levels:
        before = sample_system()
        batch_started = time.monotonic()
        print(f"[{now()}] level={level} starting")
        with concurrent.futures.ThreadPoolExecutor(max_workers=level) as executor:
            futures = [
                executor.submit(
                    run_turn,
                    agents[i % len(agents)],
                    run_id,
                    (level * 1000) + i,
                    args.timeout,
                    args.thinking,
                )
                for i in range(level)
            ]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        elapsed = round(time.monotonic() - batch_started, 3)
        after = sample_system()
        latencies = [result.elapsed_s for result in results]
        ok_count = sum(1 for result in results if result.ok)
        level_report = {
            "concurrency": level,
            "ok": ok_count,
            "failed": len(results) - ok_count,
            "elapsed_s": elapsed,
            "latency_min_s": min(latencies) if latencies else 0,
            "latency_p50_s": percentile(latencies, 50),
            "latency_p95_s": percentile(latencies, 95),
            "latency_max_s": max(latencies) if latencies else 0,
            "before": asdict(before),
            "after": asdict(after),
            "results": [asdict(result) for result in sorted(results, key=lambda item: item.index)],
        }
        report["levels"].append(level_report)
        print(
            f"[{now()}] level={level} ok={ok_count}/{len(results)} "
            f"elapsed={elapsed}s p95={level_report['latency_p95_s']}s "
            f"mem_avail_after={after.mem_available_kib // 1024}MiB "
            f"gateway_rss_after={after.gateway_rss_kib // 1024}MiB"
        )

    report["finished_at"] = now()
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[{now()}] wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
