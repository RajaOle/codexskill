#!/usr/bin/env python3
"""
Safely reclaim MiniPC disk space on a monthly systemd schedule.

The worker cleans:
  - downloaded APT package archives;
  - systemd journals beyond 300 MiB or older than 14 days;
  - Docker build cache older than 30 days;
  - Chrome and Firefox cache files older than 30 days.

Running containers, Docker images, browser profiles, cookies, passwords, and
application data are not removed.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path


HOME_DIR = Path("/home/olekamole")
APT_CACHE_DIR = Path("/var/cache/apt/archives")
BROWSER_CACHE_DIRS = (
    HOME_DIR / ".cache/google-chrome",
    HOME_DIR / ".cache/mozilla/firefox",
)
BROWSER_CACHE_MIN_AGE_DAYS = 30
DOCKER_CACHE_MIN_AGE_HOURS = 30 * 24
JOURNAL_MAX_SIZE = "300M"
JOURNAL_MAX_AGE = "14days"

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("minipc-monthly-cleanup")


def human_size(size_bytes: int) -> str:
    """Return a compact binary-size representation."""
    size = float(max(size_bytes, 0))
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TiB"


def path_size(path: Path) -> int:
    """Measure regular files below a path without following symlinks."""
    total = 0
    if not path.exists():
        return total

    try:
        for root, dir_names, file_names in os.walk(path, followlinks=False):
            root_path = Path(root)
            dir_names[:] = [
                name for name in dir_names if not (root_path / name).is_symlink()
            ]
            for file_name in file_names:
                file_path = root_path / file_name
                try:
                    file_stat = file_path.lstat()
                    if stat.S_ISREG(file_stat.st_mode):
                        total += file_stat.st_size
                except OSError as exc:
                    log.warning("Cannot inspect %s: %s", file_path, exc)
    except OSError as exc:
        log.warning("Cannot scan %s: %s", path, exc)
    return total


def run_command(command: list[str], *, dry_run: bool) -> bool:
    """Run one cleanup command and log errors without hiding later tasks."""
    display_command = " ".join(command)
    if dry_run:
        log.info("[dry-run] Would run: %s", display_command)
        return True

    executable = Path(command[0])
    if not executable.exists():
        log.error("Required command is missing: %s", executable)
        return False

    log.info("Running: %s", display_command)
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=3600,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.error("Could not run %s: %s", executable, exc)
        return False

    if result.stdout.strip():
        log.info("%s", result.stdout.strip())
    if result.stderr.strip():
        log.warning("%s", result.stderr.strip())
    if result.returncode != 0:
        log.error("Command exited with status %d: %s", result.returncode, display_command)
        return False
    return True


def clean_apt_cache(*, dry_run: bool) -> bool:
    """Remove downloaded package archives without uninstalling packages."""
    before = path_size(APT_CACHE_DIR)
    log.info("APT archive cache currently uses %s", human_size(before))
    return run_command(["/usr/bin/apt-get", "clean"], dry_run=dry_run)


def vacuum_journal(*, dry_run: bool) -> bool:
    """Remove old journal segments while retaining recent diagnostics."""
    return run_command(
        [
            "/usr/bin/journalctl",
            f"--vacuum-size={JOURNAL_MAX_SIZE}",
            f"--vacuum-time={JOURNAL_MAX_AGE}",
        ],
        dry_run=dry_run,
    )


def docker_is_available() -> bool:
    """Return whether the Docker daemon can currently accept commands."""
    try:
        result = subprocess.run(
            ["/usr/bin/docker", "info", "--format", "{{.ServerVersion}}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Docker availability check failed: %s", exc)
        return False
    return result.returncode == 0


def clean_docker_build_cache(*, dry_run: bool) -> bool:
    """Prune only unused build cache older than 30 days."""
    if not dry_run and not docker_is_available():
        log.warning("Docker is unavailable; skipping Docker build-cache cleanup")
        return True

    return run_command(
        [
            "/usr/bin/docker",
            "builder",
            "prune",
            "--force",
            "--filter",
            f"until={DOCKER_CACHE_MIN_AGE_HOURS}h",
        ],
        dry_run=dry_run,
    )


def clean_old_browser_cache(*, dry_run: bool) -> bool:
    """Delete old regular cache files without following symlinks."""
    cutoff = time.time() - (BROWSER_CACHE_MIN_AGE_DAYS * 24 * 60 * 60)
    removed_bytes = 0
    removed_files = 0
    failures = 0

    for cache_dir in BROWSER_CACHE_DIRS:
        if not cache_dir.exists():
            log.info("Browser cache directory does not exist; skipping %s", cache_dir)
            continue

        log.info(
            "Scanning %s for cache files older than %d days",
            cache_dir,
            BROWSER_CACHE_MIN_AGE_DAYS,
        )
        directories: list[Path] = []
        try:
            for root, dir_names, file_names in os.walk(cache_dir, followlinks=False):
                root_path = Path(root)
                directories.append(root_path)
                dir_names[:] = [
                    name
                    for name in dir_names
                    if not (root_path / name).is_symlink()
                ]

                for file_name in file_names:
                    file_path = root_path / file_name
                    try:
                        file_stat = file_path.lstat()
                        if not stat.S_ISREG(file_stat.st_mode):
                            continue
                        if file_stat.st_mtime >= cutoff:
                            continue

                        removed_bytes += file_stat.st_size
                        removed_files += 1
                        if not dry_run:
                            file_path.unlink()
                    except FileNotFoundError:
                        continue
                    except OSError as exc:
                        failures += 1
                        log.warning("Cannot remove %s: %s", file_path, exc)

            if not dry_run:
                for directory in reversed(directories):
                    if directory == cache_dir:
                        continue
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
        except OSError as exc:
            failures += 1
            log.warning("Cannot scan %s: %s", cache_dir, exc)

    action = "Would remove" if dry_run else "Removed"
    log.info(
        "%s %d old browser cache files totaling %s",
        action,
        removed_files,
        human_size(removed_bytes),
    )
    return failures == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report cleanup actions without deleting anything",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.dry_run and os.geteuid() != 0:
        log.error("This worker must run as root; use --dry-run for a safe preview")
        return 2

    disk_before = shutil.disk_usage("/")
    log.info(
        "Monthly cleanup started%s; root free space: %s",
        " in dry-run mode" if args.dry_run else "",
        human_size(disk_before.free),
    )

    tasks = (
        ("APT cache", clean_apt_cache),
        ("system journal", vacuum_journal),
        ("Docker build cache", clean_docker_build_cache),
        ("browser caches", clean_old_browser_cache),
    )
    failed_tasks: list[str] = []
    for task_name, task in tasks:
        log.info("Starting %s cleanup", task_name)
        try:
            if not task(dry_run=args.dry_run):
                failed_tasks.append(task_name)
        except Exception:
            log.exception("Unexpected failure during %s cleanup", task_name)
            failed_tasks.append(task_name)

    disk_after = shutil.disk_usage("/")
    reclaimed = disk_after.free - disk_before.free
    if args.dry_run:
        log.info("Dry run completed; no files were changed")
    else:
        log.info(
            "Monthly cleanup finished; reclaimed %s; root free space: %s",
            human_size(reclaimed),
            human_size(disk_after.free),
        )

    if failed_tasks:
        log.error("Cleanup completed with failed tasks: %s", ", ".join(failed_tasks))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
