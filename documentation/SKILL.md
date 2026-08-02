---
name: documentation
description: Documentation skill for writing READMEs, runbooks, changelogs, implementation specs, handover notes, and API docs. Trigger for any request to document a system, write a README, create a runbook, generate a changelog, or produce technical handover material.
---

# Documentation

## OpenClaw Agent Prompt Documents

When writing or restructuring OpenClaw agent prompts, design for the runtime injection limit first.

- Keep runtime-loaded `AGENTS.md` under 20,000 bytes; target under 18,000 bytes when practical.
- Treat `AGENTS.md` as a table of contents, bibliography, load order, and routing contract.
- Put detailed persona, workflows, examples, SOPs, templates, and knowledge in separate route-specific files.
- Preserve capability by adding clear references from `AGENTS.md` to the exact file that must be read for each task type.
- Verify size with `wc -c AGENTS.md` and use a local non-delivery dry run; do not send live WhatsApp messages for prompt validation.

## README Template

```markdown
# Project Name

> One-line description of what this does.

## Requirements

- Debian 13 / Ubuntu 22+
- Python 3.11 (via pyenv)
- Intel Iris Xe iGPU (optional, falls back to CPU)
- OpenVINO ≥ 2024.0
- RTSP camera / Hikvision NVR

## Setup

```bash
# Clone
git clone https://github.com/youruser/project.git
cd project

# Python env
pyenv shell 3.11.x
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Environment
cp .env.example .env
nano .env   # fill in credentials

# One-time model export
python3 -c "from ultralytics import YOLO; YOLO('yolo11s.pt').export(format='openvino', imgsz=640, half=True)"
```

## Usage

```bash
source venv/bin/activate
python person_tracker8.py
# Press Q to quit
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `NVR_IP` | `192.168.1.168` | NVR IP address |
| `INFER_W/H` | `640` | Model input size (must match export) |
| `FACE_COOLDOWN` | `10` | Seconds between face saves per channel |
| `CONF_THRESH` | `0.35` | Detection confidence threshold |

## Known Issues

- PMU error `Unable to poll intel GPU stats` — cosmetic noise, ignore
- Python 3.13 incompatible with PyTorch/OpenVINO — use 3.11

## License

MIT
```

---

## Runbook — Person Tracker

```markdown
# Runbook: person_tracker8.py

**Purpose**: Real-time person/object detection across NVR channels with face snapshot saving.

## Start

```bash
cd ~/yolo-vision
source venv/bin/activate
python person_tracker8.py
```

## Stop

Press `Q` in the display window, or:
```bash
kill $(cat /tmp/tracker.pid)
```

## As systemd service

```bash
systemctl start nvr-tracker
systemctl stop nvr-tracker
systemctl status nvr-tracker
journalctl -u nvr-tracker -f
```

## Health checks

1. Check `face_pipeline.log` for recent `[INFER]` lines
2. Verify `known_faces/` is receiving new files
3. Check display shows `[GPU]` not `[CPU]` in tile header
4. Confirm FPS counter > 1 in bottom-left

## Common issues

| Symptom | Fix |
|---------|-----|
| `shape mismatch` error | Reexport model with matching imgsz |
| No faces saved | Check YuNet .onnx exists; check `FACE_MIN_SIZE` |
| All channels show "CONNECTING" | Check NVR IP and credentials in .env |
| Running on CPU, expected GPU | Run `python3 -c "import openvino as ov; print(ov.Core().available_devices)"` |
```

---

## Changelog Format (Keep a Changelog)

```markdown
# Changelog

All notable changes to this project will be documented here.

## [Unreleased]

## [1.3.0] — 2025-05-04

### Added
- Multi-channel face detection with YuNet
- Per-channel save cooldown (`FACE_COOLDOWN = 10s`)
- Deduplication queue to prevent double-processing
- Detailed logging to `face_pipeline.log`

### Changed
- Inference now uses pure OpenVINO runtime (no Ultralytics at inference time)
- INFER_W/H increased from 320 to 640 for better accuracy

### Fixed
- Shape mismatch error when model export size differs from script size
- Thread race condition in face queue processing

## [1.2.0] — 2025-04-29

### Added
- YuNet face detector integration
- Face crop saving with generous head+shoulder padding

### Fixed
- RTSP stream dropping every 1-2h (added preset-rtsp-restream)
```

---

## Handover Notes Template

```markdown
# Handover Notes — [Project/System] — [Date]

## System Overview
Brief description of what this system does.

## Access

| Resource | Details |
|----------|---------|
| MiniPC SSH | `ssh olekamole@[IP]` |
| Frigate UI | `http://192.168.1.175:5000` |
| Config files | `/home/olekamole/frigate/config/config.yml` |
| Tracker logs | `/home/olekamole/yolo-vision/face_pipeline.log` |

## Running Services

| Service | How to check | How to restart |
|---------|-------------|----------------|
| Frigate | `docker ps` | `docker restart frigate` |
| Tracker | `systemctl status nvr-tracker` | `systemctl restart nvr-tracker` |

## Known Issues

List of current known issues, their status, and workarounds.

## Pending Tasks

- [ ] Fix inside_house zone coordinates in Frigate config
- [ ] Integrate CompreFace for facial recognition
- [ ] Set up alerting via Telegram bot

## Useful Commands

```bash
# Quick health check
/home/olekamole/scripts/health_report.sh

# View recent face detections
ls -lt known_faces/ | head -20

# Restart everything
docker restart frigate && systemctl restart nvr-tracker
```
```

---

## Auto-generate Docstrings (Python)

For any complex function, always include:

```python
def postprocess(output: np.ndarray, orig_w: int, orig_h: int) -> list[tuple]:
    """
    Convert raw YOLO output to bounding box detections.

    Args:
        output:  Raw model output array, shape [1, 84, 8400]
        orig_w:  Original frame width in pixels
        orig_h:  Original frame height in pixels

    Returns:
        List of (x1, y1, x2, y2, confidence, class_id) tuples,
        filtered to TARGET_IDS and CONF_THRESH.

    Notes:
        YOLO outputs cx,cy,w,h normalized to INFER_W/INFER_H.
        Coordinates are rescaled to original frame dimensions.
    """
```
