---
name: observability
description: Observability skill for log parsing, health checks, uptime monitoring, metrics dashboards, error summaries, alert rules, and incident reports. Trigger for monitoring, debugging a live system, checking service health, reviewing logs, or setting up alerts.
---

# Observability

## Log Locations

| Source | Location / Command |
|--------|-------------------|
| Frigate NVR | `docker logs frigate -f` |
| Tracker app | `/home/olekamole/yolo-vision/face_pipeline.log` |
| System journal | `journalctl -xe` |
| Cron output | `/var/log/syslog` (grep for CRON) |
| Auth/SSH | `/var/log/auth.log` |
| API service | `journalctl -u nvr-api -f` |

---

## Log Tailing & Parsing

```bash
# Follow live
tail -f /home/olekamole/yolo-vision/face_pipeline.log

# Last N lines
tail -200 face_pipeline.log

# Filter by keyword
grep "ALERT\|ERROR\|WARN" face_pipeline.log
grep "\[INFER\]" face_pipeline.log | tail -20
grep "\[SAVED\]" face_pipeline.log | wc -l   # count saved faces

# Time range (journalctl)
journalctl -u frigate --since "2025-05-04 08:00" --until "2025-05-04 10:00"

# Count errors per hour
grep "ERROR" face_pipeline.log | awk '{print $1" "$2}' | cut -c1-14 | sort | uniq -c
```

---

## Health Check Script

```bash
#!/bin/bash
# health_report.sh — print system health summary

echo "=== System Health Report: $(date) ==="

# CPU / RAM
echo ""
echo "── CPU / RAM ──────────────────────────────"
top -bn1 | grep "Cpu(s)" | awk '{print "CPU: " $2 "% user, " $4 "% system"}'
free -h | awk '/Mem:/ {print "RAM: " $3 " used / " $2 " total"}'

# Disk
echo ""
echo "── Disk ───────────────────────────────────"
df -h / | awk 'NR==2 {print "Root: " $3 " used / " $2 " total (" $5 " used)"}'
echo "Known faces dir: $(du -sh /home/olekamole/yolo-vision/known_faces 2>/dev/null | cut -f1)"

# Services
echo ""
echo "── Services ────────────────────────────────"
for svc in docker ssh; do
    if systemctl is-active --quiet "$svc"; then
        echo "  $svc: ✓ running"
    else
        echo "  $svc: ✗ STOPPED"
    fi
done

# Docker containers
echo ""
echo "── Containers ──────────────────────────────"
docker ps --format "  {{.Names}}: {{.Status}}"

# Frigate
echo ""
echo "── Frigate API ─────────────────────────────"
if curl -sf http://192.168.1.175:5000/api/version > /dev/null; then
    VER=$(curl -s http://192.168.1.175:5000/api/version)
    echo "  Frigate: ✓ online ($VER)"
else
    echo "  Frigate: ✗ UNREACHABLE"
fi

# Camera
echo ""
echo "── Camera ──────────────────────────────────"
if ping -c 1 -W 2 192.168.1.249 > /dev/null 2>&1; then
    echo "  Camera 192.168.1.249: ✓ reachable"
else
    echo "  Camera 192.168.1.249: ✗ not responding"
fi

echo ""
echo "=== End of report ==="
```

---

## Python psutil Metrics

```python
import psutil
import time

def get_metrics() -> dict:
    vm   = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "ts":           time.strftime("%Y-%m-%d %H:%M:%S"),
        "cpu_pct":      psutil.cpu_percent(interval=1),
        "ram_used_gb":  round(vm.used / 1e9, 2),
        "ram_pct":      vm.percent,
        "disk_free_gb": round(disk.free / 1e9, 2),
        "disk_pct":     disk.percent,
    }

# Log every minute
while True:
    m = get_metrics()
    print(f"[{m['ts']}] CPU:{m['cpu_pct']}%  RAM:{m['ram_pct']}%  Disk free:{m['disk_free_gb']}GB")
    time.sleep(60)
```

---

## Face Pipeline Metrics Summary

```python
"""Parse face_pipeline.log and print a summary."""
import re
from collections import defaultdict
from pathlib import Path

log_path = Path("/home/olekamole/yolo-vision/face_pipeline.log")
lines    = log_path.read_text().splitlines()

saved   = [l for l in lines if "[SAVED]" in l]
errors  = [l for l in lines if "EXCEPTION" in l or "ERROR" in l]
workers = [l for l in lines if "[WORKER]" in l and "nothing saved" in l]
infers  = [l for l in lines if "[INFER]" in l]

# Saved per channel
by_channel = defaultdict(int)
for line in saved:
    m = re.search(r"CH(\d+)", line)
    if m:
        by_channel[int(m.group(1))] += 1

print("=== Face Pipeline Summary ===")
print(f"Total infer log lines : {len(infers)}")
print(f"Faces saved           : {len(saved)}")
print(f"Failed saves          : {len(workers)}")
print(f"Exceptions            : {len(errors)}")
print(f"\nSaved per channel:")
for ch, count in sorted(by_channel.items()):
    print(f"  CH{ch}: {count}")
```

---

## Alert Rules (bash)

```bash
# alert_rules.sh — run from cron every 5 min
ALERT_LOG="/home/olekamole/logs/alerts.log"

# RAM > 90%
RAM_PCT=$(free | awk '/Mem:/ {printf "%.0f", $3/$2*100}')
if [ "$RAM_PCT" -gt 90 ]; then
    echo "[$(date)] ALERT: RAM at ${RAM_PCT}%" >> "$ALERT_LOG"
fi

# Disk > 85%
DISK_PCT=$(df / | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$DISK_PCT" -gt 85 ]; then
    echo "[$(date)] ALERT: Disk at ${DISK_PCT}%" >> "$ALERT_LOG"
fi

# Frigate down
if ! curl -sf http://192.168.1.175:5000/api/version > /dev/null; then
    echo "[$(date)] ALERT: Frigate NVR unreachable" >> "$ALERT_LOG"
    docker restart frigate
fi
```

---

## Incident Report Template

```markdown
## Incident Report — [DATE] [SHORT TITLE]

**Time detected**: 
**Duration**: 
**Severity**: Low / Medium / High

### What happened
Short description of the incident.

### Impact
- What was affected
- How long

### Root cause
The underlying reason.

### Timeline
- HH:MM — First symptom observed
- HH:MM — Investigation started
- HH:MM — Root cause identified
- HH:MM — Fix applied
- HH:MM — Service restored

### Fix applied
What was done to resolve it.

### Prevention
What will be done to prevent recurrence.
```
