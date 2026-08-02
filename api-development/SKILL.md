---
name: api-development
description: API development skill for building REST APIs with FastAPI, auth flows, API testing, OpenAPI docs, and backend integrations. Trigger for any task involving building a web service, HTTP endpoint, API client, dashboard backend, or webhook handler.
---

# API Development

## FastAPI — Standard Setup (Python 3.11)

```bash
source ~/yolo-vision/venv/bin/activate
pip install fastapi uvicorn[standard] python-dotenv
```

```python
# main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os

app = FastAPI(title="NVR API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],   # adjust for production
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}
```

```bash
# Run
uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# Access docs
# http://localhost:8080/docs      (Swagger UI)
# http://localhost:8080/redoc     (ReDoc)
```

---

## NVR Status API (example for this machine)

```python
from fastapi import FastAPI
from fastapi.responses import FileResponse
import sqlite3
import os
import time
import cv2
from pathlib import Path

app = FastAPI(title="MiniPC NVR API")

DB_PATH    = "/home/olekamole/data/app.db"
FACES_DIR  = "/home/olekamole/yolo-vision/known_faces"

# ── Detection history ──────────────────────────────────────────────────────────
@app.get("/detections")
def get_detections(channel: int = None, limit: int = 50):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if channel:
        rows = conn.execute(
            "SELECT * FROM detections WHERE channel=? ORDER BY timestamp DESC LIMIT ?",
            (channel, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM detections ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Face crops ─────────────────────────────────────────────────────────────────
@app.get("/faces")
def list_faces(channel: int = None):
    files = sorted(Path(FACES_DIR).glob("face_ch*.jpg"), reverse=True)
    if channel:
        files = [f for f in files if f"_ch{channel}_" in f.name]
    return [{"filename": f.name, "path": str(f), "size": f.stat().st_size} for f in files[:100]]

@app.get("/faces/{filename}")
def get_face_image(filename: str):
    path = Path(FACES_DIR) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(str(path), media_type="image/jpeg")

# ── System status ──────────────────────────────────────────────────────────────
@app.get("/status")
def system_status():
    import psutil
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "ram_used_gb": round(psutil.virtual_memory().used / 1e9, 2),
        "ram_total_gb": round(psutil.virtual_memory().total / 1e9, 2),
        "disk_free_gb": round(psutil.disk_usage("/").free / 1e9, 2),
        "uptime_s": int(time.time() - psutil.boot_time()),
    }
```

---

## Auth — API Key (simple, for internal tools)

```python
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
import os

API_KEY_HEADER = APIKeyHeader(name="X-API-Key")

def require_api_key(api_key: str = Security(API_KEY_HEADER)):
    if api_key != os.environ.get("API_KEY"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    return api_key

@app.get("/protected", dependencies=[Security(require_api_key)])
def protected_route():
    return {"message": "authorized"}
```

```bash
# Set in .env
API_KEY=changeme_longrandstring

# Call with key
curl -H "X-API-Key: changeme_longrandstring" http://localhost:8080/protected
```

---

## Pydantic Models

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class Detection(BaseModel):
    channel:    int
    timestamp:  str
    class_name: str = Field(alias="class")
    confidence: float = Field(ge=0.0, le=1.0)
    face_path:  Optional[str] = None

class DetectionCreate(BaseModel):
    channel:    int
    class_name: str
    confidence: float
```

---

## API Testing

```bash
# Quick curl tests
curl http://localhost:8080/health
curl http://localhost:8080/detections?channel=1&limit=5
curl http://localhost:8080/status

# With jq for pretty JSON
curl -s http://localhost:8080/detections | jq '.[0]'
```

```python
# pytest + httpx for automated tests
import pytest
from httpx import AsyncClient
from main import app

@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
```

```bash
pip install pytest pytest-asyncio httpx
pytest tests/ -v
```

---

## Run as systemd service

```ini
# /etc/systemd/system/nvr-api.service
[Unit]
Description=NVR FastAPI Service
After=network.target

[Service]
Type=simple
User=olekamole
WorkingDirectory=/home/olekamole/projects/nvr-api
ExecStart=/home/olekamole/.pyenv/shims/python -m uvicorn main:app --host 0.0.0.0 --port 8080
Restart=on-failure
EnvironmentFile=/home/olekamole/projects/nvr-api/.env

[Install]
WantedBy=multi-user.target
```

---

## Webhook Handler (receive Frigate events)

```python
from fastapi import Request

@app.post("/webhook/frigate")
async def frigate_webhook(request: Request):
    payload = await request.json()
    event_type = payload.get("type")       # "new", "update", "end"
    camera     = payload.get("camera")
    label      = payload.get("after", {}).get("label")
    confidence = payload.get("after", {}).get("top_score")

    if event_type == "new" and label == "person":
        # log or trigger alert
        print(f"New person detected on {camera} ({confidence:.2f})")

    return {"ok": True}
```

Configure in Frigate `config.yml`:
```yaml
notifications:
  webhook:
    url: http://192.168.1.xxx:8080/webhook/frigate
```
