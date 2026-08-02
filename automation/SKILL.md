---
name: automation
description: Automation skill for shell scripts, Python utility scripts, scheduled cron jobs, file watchers, webhook handlers, and admin task bots. Trigger for any task involving repetitive work, scheduled jobs, file monitoring, alerting, or building small helper tools.
---

# Automation

## Shell Script Template

```bash
#!/bin/bash
set -euo pipefail   # exit on error, undefined vars, pipe failures
IFS=$'\n\t'

# ─── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/logs/$(basename "$0" .sh).log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# ─── Logging ───────────────────────────────────────────────────────────────────
log() { echo "[$TIMESTAMP] $*" | tee -a "$LOG_FILE"; }
err() { echo "[$TIMESTAMP] ERROR: $*" >&2 | tee -a "$LOG_FILE"; exit 1; }

mkdir -p "$(dirname "$LOG_FILE")"
log "=== Starting $0 ==="

# ─── Main ──────────────────────────────────────────────────────────────────────
# ... your logic here ...

log "=== Done ==="
```

---

## Python Utility Script Template

```python
#!/usr/bin/env python3
"""
brief_description.py — what this script does
Usage: python3 brief_description.py [args]
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("script.log"),
    ]
)
log = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()

    log.info("Starting...")
    # ... logic ...
    log.info("Done.")

if __name__ == "__main__":
    main()
```

---

## Cron Reference

```bash
crontab -e    # edit
crontab -l    # list

# Format: MIN HOUR DOM MON DOW COMMAND
# ┌─ minute (0-59)
# │ ┌─ hour (0-23)
# │ │ ┌─ day of month (1-31)
# │ │ │ ┌─ month (1-12)
# │ │ │ │ ┌─ day of week (0=Sun)
# │ │ │ │ │
# * * * * * /path/to/command

# Examples
0  3 * * *  /home/olekamole/scripts/backup.sh           # daily 3am
*/5 * * * * /home/olekamole/scripts/healthcheck.sh      # every 5 min
0  0 * * 0  /home/olekamole/scripts/weekly_cleanup.sh  # weekly Sunday midnight
@reboot     /home/olekamole/scripts/start_tracker.sh   # on boot

# Log cron output
0 3 * * * /home/olekamole/scripts/backup.sh >> /var/log/backup.log 2>&1
```

---

## File Watcher (Python)

```python
#!/usr/bin/env python3
"""Watch a directory and trigger an action on new files."""

import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

WATCH_PATH = "/home/olekamole/yolo-vision/known_faces"

class FaceHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        filepath = event.src_path
        print(f"New file: {filepath}")
        # e.g., run face recognition, send alert, move file

if __name__ == "__main__":
    observer = Observer()
    observer.schedule(FaceHandler(), WATCH_PATH, recursive=False)
    observer.start()
    print(f"Watching: {WATCH_PATH}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
```

```bash
pip install watchdog --break-system-packages
```

---

## Healthcheck Script

```bash
#!/bin/bash
# healthcheck.sh — check key services and alert if down

SERVICES=("docker" "ssh")
NVR_URL="http://192.168.1.175:5000"
CAMERA_IP="192.168.1.249"
ALERT_LOG="/home/olekamole/logs/healthcheck.log"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# Check systemd services
for svc in "${SERVICES[@]}"; do
    if ! systemctl is-active --quiet "$svc"; then
        echo "[$(ts)] ALERT: $svc is DOWN" >> "$ALERT_LOG"
        # Optionally: restart or notify
        systemctl restart "$svc"
    fi
done

# Check Frigate
if ! curl -sf "$NVR_URL/api/version" > /dev/null; then
    echo "[$(ts)] ALERT: Frigate NVR unreachable" >> "$ALERT_LOG"
    docker restart frigate
fi

# Check camera ping
if ! ping -c 1 -W 2 "$CAMERA_IP" > /dev/null 2>&1; then
    echo "[$(ts)] WARN: Camera $CAMERA_IP not responding" >> "$ALERT_LOG"
fi

echo "[$(ts)] Healthcheck complete" >> "$ALERT_LOG"
```

---

## Face Crop Cleanup Script

```bash
#!/bin/bash
# clean_old_faces.sh — delete face crops older than N days

SAVE_PATH="/home/olekamole/yolo-vision/known_faces"
KEEP_DAYS=30

find "$SAVE_PATH" -name "face_ch*.jpg" -mtime +$KEEP_DAYS -delete
echo "[$(date)] Cleanup done: removed files older than $KEEP_DAYS days"
```

Add to cron:
```
0 4 * * * /home/olekamole/scripts/clean_old_faces.sh >> /home/olekamole/logs/cleanup.log 2>&1
```

---

## Startup Script (tracker auto-start)

```bash
#!/bin/bash
# start_tracker.sh — launch person_tracker8.py on boot

cd /home/olekamole/yolo-vision
source venv/bin/activate
nohup python3 person_tracker8.py >> /home/olekamole/logs/tracker.log 2>&1 &
echo $! > /tmp/tracker.pid
echo "[$(date)] Tracker started, PID: $(cat /tmp/tracker.pid)"
```

Or use systemd (preferred — see `sysadmin.md` for service template).

---

## Alert via Telegram (optional)

```python
import requests
import os

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

def send_alert(message: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": message})

def send_photo(image_path: str, caption: str = ""):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(image_path, "rb") as f:
        requests.post(url, data={"chat_id": CHAT_ID, "caption": caption}, files={"photo": f})
```
