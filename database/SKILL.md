---
name: database
description: Database skill for SQLite and PostgreSQL admin, SQL queries, migrations, backups, CSV/Excel data processing, and ETL scripts. Trigger for any data storage, query writing, migration task, data import/export, or report generation from structured data.
---

# Database & Data Work

## SQLite (Local — default for scripts on this machine)

```python
import sqlite3
from pathlib import Path

DB_PATH = Path("/home/olekamole/data/app.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # dict-like rows
    conn.execute("PRAGMA journal_mode=WAL")  # better concurrency
    return conn

# Create table
with get_conn() as conn:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS detections (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            channel   INTEGER NOT NULL,
            timestamp TEXT    NOT NULL,
            class     TEXT    NOT NULL,
            confidence REAL   NOT NULL,
            face_path TEXT
        )
    """)

# Insert
with get_conn() as conn:
    conn.execute(
        "INSERT INTO detections (channel, timestamp, class, confidence, face_path) VALUES (?,?,?,?,?)",
        (ch, time.strftime("%Y-%m-%d %H:%M:%S"), "person", 0.87, filename)
    )

# Query
with get_conn() as conn:
    rows = conn.execute(
        "SELECT * FROM detections WHERE channel=? ORDER BY timestamp DESC LIMIT 10", (1,)
    ).fetchall()
    for row in rows:
        print(dict(row))
```

---

## Detection Logging Schema (for NVR pipeline)

```sql
-- Track all object detections
CREATE TABLE IF NOT EXISTS detections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    channel     INTEGER NOT NULL,
    timestamp   TEXT    NOT NULL,
    class       TEXT    NOT NULL,
    confidence  REAL    NOT NULL,
    face_path   TEXT,                   -- path to saved face crop if any
    bbox_x1     INTEGER,
    bbox_y1     INTEGER,
    bbox_x2     INTEGER,
    bbox_y2     INTEGER
);

-- Index for fast time-range queries
CREATE INDEX IF NOT EXISTS idx_detections_time ON detections(timestamp);
CREATE INDEX IF NOT EXISTS idx_detections_channel ON detections(channel);

-- Daily summary view
CREATE VIEW IF NOT EXISTS daily_summary AS
SELECT
    DATE(timestamp) as day,
    channel,
    class,
    COUNT(*) as count,
    AVG(confidence) as avg_conf
FROM detections
GROUP BY day, channel, class
ORDER BY day DESC;
```

---

## PostgreSQL (if needed for multi-service setup)

```bash
# Install
apt install postgresql postgresql-contrib -y
systemctl enable postgresql
systemctl start postgresql

# Create database and user
sudo -u postgres psql
CREATE USER olekamole WITH PASSWORD 'yourpass';
CREATE DATABASE nvr_data OWNER olekamole;
\q

# Connect
psql -U olekamole -d nvr_data
```

```python
# Python connection (psycopg2)
import psycopg2

conn = psycopg2.connect(
    host     = "localhost",
    dbname   = "nvr_data",
    user     = os.environ["DB_USER"],
    password = os.environ["DB_PASS"]
)
```

---

## CSV / Excel Processing

```python
import csv
import json
from pathlib import Path

# Read CSV
def read_csv(path: str) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

# Write CSV
def write_csv(path: str, rows: list[dict], fieldnames: list[str]):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

# Export detections to CSV report
def export_detections_report(db_path: str, output_csv: str):
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM detections ORDER BY timestamp DESC"
    ).fetchall()
    if rows:
        write_csv(output_csv, [dict(r) for r in rows], list(rows[0].keys()))
    conn.close()
    print(f"Exported {len(rows)} rows to {output_csv}")
```

---

## Backups

```bash
# SQLite backup (safe even while DB is in use)
sqlite3 /home/olekamole/data/app.db ".backup /home/olekamole/backups/app_$(date +%Y%m%d).db"

# Automate with cron
0 2 * * * sqlite3 /home/olekamole/data/app.db ".backup /home/olekamole/backups/app_$(date +\%Y\%m\%d).db"

# Keep only last 7 days
0 2 * * * find /home/olekamole/backups -name "app_*.db" -mtime +7 -delete

# PostgreSQL dump
pg_dump -U olekamole nvr_data > backup_$(date +%Y%m%d).sql
```

---

## ETL — Face Crop Index

```python
"""
Build a SQLite index of all saved face crops.
Useful for review, deduplication, or feeding to CompreFace.
"""
import sqlite3
import os
import time
from pathlib import Path

FACES_DIR = "/home/olekamole/yolo-vision/known_faces"
DB_PATH   = "/home/olekamole/data/faces.db"

conn = sqlite3.connect(DB_PATH)
conn.execute("""
    CREATE TABLE IF NOT EXISTS face_index (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        filename  TEXT UNIQUE,
        channel   INTEGER,
        timestamp TEXT,
        width     INTEGER,
        height    INTEGER,
        reviewed  INTEGER DEFAULT 0,
        label     TEXT
    )
""")

for f in Path(FACES_DIR).glob("face_ch*.jpg"):
    parts = f.stem.split("_")
    ch    = int(parts[1].replace("ch", ""))
    ts_ms = int(parts[2])
    ts    = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts_ms / 1000))
    conn.execute(
        "INSERT OR IGNORE INTO face_index (filename, channel, timestamp) VALUES (?,?,?)",
        (str(f), ch, ts)
    )

conn.commit()
conn.close()
print(f"Indexed {len(list(Path(FACES_DIR).glob('*.jpg')))} face crops")
```

---

## Data Validation

```python
def validate_detection_row(row: dict) -> list[str]:
    """Return list of validation errors, empty = valid."""
    errors = []
    if not isinstance(row.get("channel"), int):
        errors.append("channel must be int")
    if not row.get("timestamp"):
        errors.append("timestamp required")
    if not 0.0 <= float(row.get("confidence", -1)) <= 1.0:
        errors.append("confidence must be 0.0-1.0")
    if row.get("class") not in {"person", "car", "motorcycle", "cat", "dog"}:
        errors.append(f"unknown class: {row.get('class')}")
    return errors
```
