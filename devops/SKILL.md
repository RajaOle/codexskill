---
name: devops
description: DevOps skill for Git workflows, CI/CD pipelines, Dockerfile and Compose files, environment variable management, deployment scripts, rollback procedures, and release checklists. Trigger for deployment, release, pipeline, or infrastructure-as-code tasks.
---

# DevOps

## Git Workflow

```bash
# Daily workflow
git status
git pull origin main
git checkout -b feature/my-feature
# ... make changes ...
git add -p                          # stage interactively
git commit -m "feat(tracker): add cooldown per channel"
git push origin feature/my-feature

# Merge
git checkout main
git merge --no-ff feature/my-feature
git push origin main
git branch -d feature/my-feature

# Undo last commit (keep changes)
git reset --soft HEAD~1

# Discard all local changes
git checkout -- .
```

### Commit message format
```
type(scope): short description

Types: feat, fix, refactor, docs, test, chore, perf
Examples:
  feat(tracker): add face cooldown per channel
  fix(stream): handle RTSP reconnect on channel probe
  perf(infer): use GPU device when Iris Xe available
  docs(readme): add pyenv setup instructions
  chore(deps): update ultralytics to 8.2
```

### .gitignore for this machine
```gitignore
# Python
__pycache__/
*.pyc
*.pyo
venv/
.venv/
*.egg-info/

# ML artifacts
yolo11s_openvino_model/
*.pt
*.onnx
*.xml
*.bin

# Data
known_faces/
*.jpg
*.mp4
*.avi
face_pipeline.log

# Secrets
.env
*.env
secrets/

# OS
.DS_Store
Thumbs.db
```

---

## Environment Management

```bash
# .env.example — commit this (no real values)
NVR_IP=192.168.1.168
NVR_USER=admin
NVR_PASS=
CAMERA_IP=192.168.1.249
API_KEY=
DB_PATH=/home/olekamole/data/app.db

# .env — DO NOT COMMIT
NVR_IP=192.168.1.168
NVR_USER=admin
NVR_PASS=replace_with_real_value_locally
API_KEY=changeme_abc123

# Load in shell scripts
set -a && source .env && set +a

# Load in Python
from dotenv import load_dotenv
load_dotenv()
```

---

## Deployment Script

```bash
#!/bin/bash
# deploy.sh — deploy latest code and restart service
set -euo pipefail

SERVICE_NAME="nvr-tracker"
APP_DIR="/home/olekamole/yolo-vision"
VENV="$APP_DIR/venv"
BRANCH="${1:-main}"

echo "[$(date)] Deploying branch: $BRANCH"

cd "$APP_DIR"
git fetch origin
git checkout "$BRANCH"
git pull origin "$BRANCH"

# Install/update deps
source "$VENV/bin/activate"
pip install -r requirements.txt --quiet

# Restart service
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME" --no-pager

echo "[$(date)] Deploy complete."
```

---

## Rollback Procedure

```bash
#!/bin/bash
# rollback.sh — revert to previous commit and restart
set -euo pipefail

APP_DIR="/home/olekamole/yolo-vision"
SERVICE_NAME="nvr-tracker"

cd "$APP_DIR"

CURRENT=$(git rev-parse --short HEAD)
PREVIOUS=$(git rev-parse --short HEAD~1)

echo "Rolling back from $CURRENT to $PREVIOUS"
git checkout HEAD~1

source venv/bin/activate
pip install -r requirements.txt --quiet

sudo systemctl restart "$SERVICE_NAME"
echo "Rollback complete. Now at: $PREVIOUS"
```

---

## Release Checklist

Before tagging a release:

- [ ] All tests pass: `pytest tests/ -v`
- [ ] No hardcoded credentials: `grep -r "password\|secret\|token\|api_key" *.py`
- [ ] `.env.example` is up to date
- [ ] `requirements.txt` frozen: `pip freeze > requirements.txt`
- [ ] CHANGELOG.md updated
- [ ] `git status` clean
- [ ] Service tested on restart: `systemctl restart nvr-tracker`
- [ ] Face crops saving correctly
- [ ] GPU/CPU device confirmed in logs

```bash
# Tag a release
git tag -a v1.3.0 -m "Release v1.3.0: multi-channel face detection"
git push origin v1.3.0
```

---

## Docker Compose — CI-style Validation

```bash
# Validate compose file
docker compose config

# Test build without running
docker compose build

# Full test cycle
docker compose down
docker compose up -d
sleep 5
docker compose ps       # all should be "running"
docker compose logs --tail=20
```

---

## Backup Before Deploy

```bash
# Always snapshot DB before deploy
sqlite3 /home/olekamole/data/app.db \
    ".backup /home/olekamole/backups/pre-deploy-$(date +%Y%m%d-%H%M%S).db"
echo "Pre-deploy backup done."
```

---

## requirements.txt Management

```bash
# Freeze current env
source venv/bin/activate
pip freeze > requirements.txt

# Install from frozen
pip install -r requirements.txt

# Core deps for CV/NVR stack
# requirements.txt
ultralytics>=8.0
openvino>=2024.0
opencv-python-headless
numpy
python-dotenv
fastapi
uvicorn[standard]
psutil
watchdog
```
