#!/usr/bin/env python3
"""
minipc_critical_alert.py - send OpenClaw alerts when the MiniPC is under stress.

The script is intended to run from a systemd user timer. It samples thermal
zones more than once to avoid acting on one stale ACPI reading, then sends
alerts through OpenClaw's configured channel accounts.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


HOME = Path("/home/olekamole")
STATE_DIR = HOME / ".openclaw/minipc-critical-alert"
STATE_FILE = STATE_DIR / "state.json"
LOG_FILE = STATE_DIR / "minipc-critical-alert.log"
OPENCLAW = HOME / ".npm-global/bin/openclaw"

BOSS_TELEGRAM_TARGET = "103586290"

TEMP_SAMPLE_COUNT = 5
TEMP_SAMPLE_DELAY_SEC = 1.0
ALERT_COOLDOWN_SEC = 30 * 60
RECOVERY_COOLDOWN_SEC = 30 * 60

CPU_TEMP_WARN_C = 85.0
CPU_TEMP_CRITICAL_C = 90.0
CPU_TEMP_EMERGENCY_C = 97.0
RAM_CRITICAL_PCT = 92.0
SWAP_CRITICAL_PCT = 80.0
DISK_CRITICAL_PCT = 88.0
DISK_MIN_FREE_GB = 8.0
MEMORY_PRESSURE_FULL_AVG60 = 10.0
IO_PRESSURE_FULL_AVG60 = 20.0
LOAD_PER_CPU_CRITICAL = 2.0


@dataclass
class MetricIssue:
    key: str
    severity: str
    message: str


def ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S %z")


def log(message: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{ts()}] {message}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state() -> dict[str, Any]:
    try:
        if STATE_FILE.exists():
            with STATE_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError) as exc:
        log(f"WARN failed to read state: {exc}")
    return {}


def save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(STATE_FILE)
    os.chmod(STATE_FILE, 0o600)


def read_float(path: Path, divisor: float = 1.0) -> float | None:
    try:
        return float(path.read_text(encoding="utf-8").strip()) / divisor
    except (OSError, ValueError):
        return None


def read_thermal_sample() -> dict[str, float]:
    sample: dict[str, float] = {}
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        try:
            zone_type = (zone / "type").read_text(encoding="utf-8").strip()
        except OSError:
            zone_type = zone.name
        temp_c = read_float(zone / "temp", divisor=1000.0)
        if temp_c is None:
            continue
        sample[zone_type] = temp_c
    return sample


def sample_cpu_temperature() -> dict[str, Any]:
    samples: list[dict[str, float]] = []
    for index in range(TEMP_SAMPLE_COUNT):
        samples.append(read_thermal_sample())
        if index < TEMP_SAMPLE_COUNT - 1:
            time.sleep(TEMP_SAMPLE_DELAY_SEC)

    cpu_values: list[float] = []
    cpu_names = ("x86_pkg_temp", "TCPU", "TCPU_PCI", "Package id")
    for sample in samples:
        for name, value in sample.items():
            if any(token in name for token in cpu_names):
                cpu_values.append(value)

    max_temp = max(cpu_values) if cpu_values else None
    sustained_temp = sorted(cpu_values)[len(cpu_values) // 2] if cpu_values else None
    latest = samples[-1] if samples else {}
    return {
        "max_c": max_temp,
        "median_c": sustained_temp,
        "latest": latest,
        "samples": samples,
    }


def parse_meminfo() -> dict[str, int]:
    data: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2:
                data[parts[0].rstrip(":")] = int(parts[1])
    except (OSError, ValueError):
        pass
    return data


def memory_metrics() -> dict[str, float]:
    info = parse_meminfo()
    mem_total = float(info.get("MemTotal", 0))
    mem_available = float(info.get("MemAvailable", 0))
    swap_total = float(info.get("SwapTotal", 0))
    swap_free = float(info.get("SwapFree", 0))
    ram_pct = ((mem_total - mem_available) / mem_total * 100.0) if mem_total else 0.0
    swap_pct = ((swap_total - swap_free) / swap_total * 100.0) if swap_total else 0.0
    return {
        "ram_pct": ram_pct,
        "ram_available_gb": mem_available / 1024.0 / 1024.0,
        "swap_pct": swap_pct,
    }


def disk_metrics() -> dict[str, float]:
    usage = shutil.disk_usage("/")
    used_pct = (usage.used / usage.total) * 100.0
    free_gb = usage.free / 1024.0 / 1024.0 / 1024.0
    return {"disk_pct": used_pct, "disk_free_gb": free_gb}


def pressure_metric(path: Path) -> dict[str, float]:
    result = {"some_avg60": 0.0, "full_avg60": 0.0}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return result
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        prefix = parts[0]
        for part in parts[1:]:
            if part.startswith("avg60="):
                try:
                    result[f"{prefix}_avg60"] = float(part.split("=", 1)[1])
                except ValueError:
                    pass
    return result


def load_metrics() -> dict[str, float]:
    load1, load5, load15 = os.getloadavg()
    cpu_count = os.cpu_count() or 1
    return {
        "load1": load1,
        "load5": load5,
        "load15": load15,
        "cpu_count": float(cpu_count),
        "load_per_cpu": load5 / cpu_count,
    }


def collect_metrics() -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    metrics["temperature"] = sample_cpu_temperature()
    metrics.update(memory_metrics())
    metrics.update(disk_metrics())
    metrics.update(load_metrics())
    metrics["memory_pressure"] = pressure_metric(Path("/proc/pressure/memory"))
    metrics["io_pressure"] = pressure_metric(Path("/proc/pressure/io"))
    return metrics


def evaluate(metrics: dict[str, Any]) -> list[MetricIssue]:
    issues: list[MetricIssue] = []

    temp = metrics["temperature"]
    max_temp = temp.get("max_c")
    median_temp = temp.get("median_c")
    if isinstance(max_temp, (int, float)) and isinstance(median_temp, (int, float)):
        if max_temp >= CPU_TEMP_EMERGENCY_C or median_temp >= CPU_TEMP_CRITICAL_C:
            issues.append(
                MetricIssue(
                    "cpu_temp",
                    "critical",
                    f"CPU package temperature high: max {max_temp:.1f}C, median {median_temp:.1f}C",
                )
            )
        elif max_temp >= CPU_TEMP_CRITICAL_C and median_temp >= CPU_TEMP_WARN_C:
            issues.append(
                MetricIssue(
                    "cpu_temp",
                    "warning",
                    f"CPU temperature spike: max {max_temp:.1f}C, median {median_temp:.1f}C",
                )
            )

    if metrics["ram_pct"] >= RAM_CRITICAL_PCT:
        issues.append(
            MetricIssue(
                "ram",
                "critical",
                f"RAM pressure high: {metrics['ram_pct']:.1f}% used, {metrics['ram_available_gb']:.1f}GiB available",
            )
        )
    if metrics["swap_pct"] >= SWAP_CRITICAL_PCT:
        issues.append(MetricIssue("swap", "critical", f"Swap usage high: {metrics['swap_pct']:.1f}% used"))
    if metrics["disk_pct"] >= DISK_CRITICAL_PCT or metrics["disk_free_gb"] <= DISK_MIN_FREE_GB:
        issues.append(
            MetricIssue(
                "disk",
                "critical",
                f"Root disk low: {metrics['disk_pct']:.1f}% used, {metrics['disk_free_gb']:.1f}GiB free",
            )
        )
    if metrics["memory_pressure"]["full_avg60"] >= MEMORY_PRESSURE_FULL_AVG60:
        issues.append(
            MetricIssue(
                "memory_pressure",
                "critical",
                f"Memory stalls high: full avg60 {metrics['memory_pressure']['full_avg60']:.1f}%",
            )
        )
    if metrics["io_pressure"]["full_avg60"] >= IO_PRESSURE_FULL_AVG60:
        issues.append(
            MetricIssue(
                "io_pressure",
                "critical",
                f"I/O stalls high: full avg60 {metrics['io_pressure']['full_avg60']:.1f}%",
            )
        )
    if metrics["load_per_cpu"] >= LOAD_PER_CPU_CRITICAL:
        issues.append(
            MetricIssue(
                "load",
                "critical",
                f"Load average high: load5 {metrics['load5']:.2f} across {int(metrics['cpu_count'])} CPUs",
            )
        )
    return issues


def format_metrics(metrics: dict[str, Any]) -> str:
    temp = metrics["temperature"]
    max_temp = temp.get("max_c")
    median_temp = temp.get("median_c")
    temp_text = "unavailable"
    if isinstance(max_temp, (int, float)) and isinstance(median_temp, (int, float)):
        temp_text = f"max {max_temp:.1f}C, median {median_temp:.1f}C"

    return (
        f"Temp: {temp_text}\n"
        f"RAM: {metrics['ram_pct']:.1f}% used, {metrics['ram_available_gb']:.1f}GiB available\n"
        f"Swap: {metrics['swap_pct']:.1f}% used\n"
        f"Disk: {metrics['disk_pct']:.1f}% used, {metrics['disk_free_gb']:.1f}GiB free\n"
        f"Load5: {metrics['load5']:.2f} ({metrics['load_per_cpu']:.2f} per CPU)\n"
        f"Memory stalls avg60: {metrics['memory_pressure']['full_avg60']:.1f}%\n"
        f"I/O stalls avg60: {metrics['io_pressure']['full_avg60']:.1f}%"
    )


def build_alert_message(issues: list[MetricIssue], metrics: dict[str, Any]) -> str:
    issue_lines = "\n".join(f"- {issue.message}" for issue in issues)
    return (
        "CRITICAL MiniPC health alert\n"
        f"Time: {ts()}\n"
        "Host: debianminipc\n\n"
        f"{issue_lines}\n\n"
        f"{format_metrics(metrics)}\n\n"
        "Action: check ventilation, active workloads, and storage. If temp remains high, stop heavy services."
    )


def build_recovery_message(metrics: dict[str, Any]) -> str:
    return (
        "RECOVERY MiniPC health back to normal\n"
        f"Time: {ts()}\n"
        "Host: debianminipc\n\n"
        f"{format_metrics(metrics)}"
    )


def send_openclaw(channel: str, account: str, target: str, message: str, dry_run: bool) -> tuple[bool, str]:
    cmd = [
        str(OPENCLAW),
        "message",
        "send",
        "--channel",
        channel,
        "--account",
        account,
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


def notify_boss(message: str, dry_run: bool) -> bool:
    deliveries = [
        ("telegram", "default", BOSS_TELEGRAM_TARGET),
    ]
    ok = True
    for channel, account, target in deliveries:
        sent, detail = send_openclaw(channel, account, target, message, dry_run=dry_run)
        if sent:
            log(f"{'DRY-RUN ' if dry_run else ''}sent {channel} alert to {target}")
        else:
            ok = False
            log(f"ERROR failed to send {channel} alert to {target}: {detail}")
    return ok


def issue_key(issues: list[MetricIssue]) -> str:
    return ",".join(sorted(issue.key for issue in issues))


def should_send_alert(state: dict[str, Any], issues: list[MetricIssue], now: float) -> bool:
    last_key = str(state.get("last_issue_key", ""))
    last_alert_at = float(state.get("last_alert_at", 0) or 0)
    current_key = issue_key(issues)
    if current_key != last_key:
        return True
    return now - last_alert_at >= ALERT_COOLDOWN_SEC


def should_send_recovery(state: dict[str, Any], now: float) -> bool:
    if not state.get("currently_alerting"):
        return False
    last_recovery_at = float(state.get("last_recovery_at", 0) or 0)
    return now - last_recovery_at >= RECOVERY_COOLDOWN_SEC


def inject_simulated_critical(metrics: dict[str, Any]) -> None:
    metrics["temperature"]["max_c"] = 99.0
    metrics["temperature"]["median_c"] = 95.0
    metrics["temperature"]["latest"]["x86_pkg_temp"] = 99.0


def run_once(dry_run: bool, simulate_critical: bool) -> int:
    state = {} if dry_run else load_state()
    metrics = collect_metrics()
    if simulate_critical:
        inject_simulated_critical(metrics)
    issues = evaluate(metrics)
    now = time.time()

    if issues:
        message = build_alert_message(issues, metrics)
        if should_send_alert(state, issues, now):
            ok = notify_boss(message, dry_run=dry_run)
            state["last_alert_at"] = now
            state["last_issue_key"] = issue_key(issues)
            state["currently_alerting"] = True
            state["last_send_ok"] = ok
        else:
            log(f"critical condition persists but cooldown is active: {issue_key(issues)}")
        state["last_status"] = "alert"
        state["last_issues"] = [issue.__dict__ for issue in issues]
        state["last_metrics"] = metrics
        if dry_run:
            log("DRY-RUN state not saved")
        else:
            save_state(state)
        return 0

    if should_send_recovery(state, now):
        message = build_recovery_message(metrics)
        ok = notify_boss(message, dry_run=dry_run)
        state["last_recovery_at"] = now
        state["last_send_ok"] = ok
        log("health recovered")
    else:
        log("health OK")

    state["currently_alerting"] = False
    state["last_status"] = "ok"
    state["last_issues"] = []
    state["last_metrics"] = metrics
    if dry_run:
        log("DRY-RUN state not saved")
    else:
        save_state(state)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Evaluate and print OpenClaw payloads without sending.")
    parser.add_argument(
        "--simulate-critical",
        action="store_true",
        help="Inject a synthetic critical temperature reading. Use with --dry-run for notification validation.",
    )
    args = parser.parse_args()

    if not OPENCLAW.exists():
        log(f"ERROR OpenClaw CLI not found at {OPENCLAW}")
        return 1

    try:
        return run_once(dry_run=args.dry_run, simulate_critical=args.simulate_critical)
    except subprocess.TimeoutExpired as exc:
        log(f"ERROR OpenClaw send timed out: {exc}")
        return 1
    except Exception as exc:
        log(f"ERROR monitor failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
