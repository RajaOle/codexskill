---
name: mlops
description: MLOps skill for YOLO model training, OpenVINO export and inference, dataset management, experiment tracking, and CV pipeline optimization on Intel hardware. Trigger for anything involving YOLO, OpenVINO, model export, inference pipelines, tracking, face detection, or computer vision on this machine.
---

# MLOps — Intel i5-1235U + Iris Xe

## Hardware Constraints

| Resource | Spec | Impact |
|----------|------|--------|
| GPU | Intel Iris Xe (iGPU, shared RAM) | Use OpenVINO GPU device |
| RAM | 8GB shared CPU+GPU | Keep models small (yolo11s not yolo11x) |
| CPU | i5-1235U 10-core | CPU fallback is viable |
| **NO CUDA** | No NVIDIA | Never use `device="cuda"` |

---

## Model Setup (One-Time Export)

```bash
# Activate Python 3.11 environment
cd ~/yolo-vision
source venv/bin/activate

# Export YOLO11s to OpenVINO format
# imgsz=640 for full resolution, half=True for FP16 on Iris Xe
python3 -c "
from ultralytics import YOLO
m = YOLO('yolo11s.pt')
m.export(format='openvino', imgsz=640, half=True)
"
# Output: yolo11s_openvino_model/yolo11s.xml

# For lower-latency (smaller input):
python3 -c "
from ultralytics import YOLO
m = YOLO('yolo11s.pt')
m.export(format='openvino', imgsz=320, half=False)
"
```

**Critical**: The exported model input size MUST match `INFER_W / INFER_H` in your script. Mismatch causes `RuntimeError: shape=[1,3,640,640] vs tensor shape=(1,3,320,320)`.

---

## OpenVINO Inference — Pure Runtime (no Ultralytics at inference time)

```python
import openvino as ov
import numpy as np
import cv2

# Device selection
core = ov.Core()
OV_DEVICE = "GPU" if "GPU" in core.available_devices else "CPU"

# Load model
MODEL_XML  = "yolo11s_openvino_model/yolo11s.xml"
ov_model   = core.read_model(MODEL_XML)
compiled   = core.compile_model(ov_model, OV_DEVICE)

# Preprocess
def preprocess(frame, w=640, h=640):
    img = cv2.resize(frame, (w, h))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = img.astype(np.float32) / 255.0
    img = np.transpose(img, (2, 0, 1))   # HWC → CHW
    return np.expand_dims(img, 0)         # → [1,3,H,W]

# Infer
inp    = preprocess(frame)
result = compiled([inp])
output = list(result.values())[0]        # shape: [1, 84, 8400]

# Postprocess (YOLO11s output format)
preds     = output[0].T                  # [8400, 84]
boxes     = preds[:, :4]                 # cx, cy, w, h (normalized to INFER size)
scores    = preds[:, 4:]
class_ids = np.argmax(scores, axis=1)
confs     = scores[np.arange(len(scores)), class_ids]
```

---

## COCO Class IDs (YOLO11s)

```python
TARGET_CLASSES = {
    0:  "person",
    2:  "car",
    3:  "motorcycle",
    15: "cat",
    16: "dog",
}
# Lizard is NOT in COCO — yolo11s cannot detect it natively
# Full COCO list: 80 classes, IDs 0-79
```

---

## Face Detection — YuNet

```bash
# Download model (one-time)
wget https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
# Place in: ~/yolo-vision/face_detection_yunet_2023mar.onnx
```

```python
import cv2

yunet = cv2.FaceDetectorYN.create(
    model           = "face_detection_yunet_2023mar.onnx",
    config          = "",
    input_size      = (640, 360),   # match frame size
    score_threshold = 0.5,
    nms_threshold   = 0.3,
    top_k           = 20
)

# Detect (must match input_size to frame dims)
yunet.setInputSize((frame_w, frame_h))
_, faces = yunet.detect(frame)
# faces: array of [x, y, w, h, ...landmarks..., score]
```

---

## Face Crop Best Practices

```python
# Generous padding for head + shoulders
pad_top    = int(fh * 0.5)    # 50% of face height above
pad_sides  = int(fw * 0.4)    # 40% sides
pad_bottom = int(fh * 1.2)    # 120% below (chin + shoulders)

x1 = max(0, fx - pad_sides)
y1 = max(0, fy - pad_top)
x2 = min(orig_w, fx + fw + pad_sides)
y2 = min(orig_h, fy + fh + pad_bottom)

# Minimum crop size filter (skip noise)
if crop_w < FACE_MIN_SIZE or crop_h < FACE_MIN_SIZE:
    continue

# Upscale small crops for readability
if crop_w < 200:
    scale = 200 / crop_w
    face_crop = cv2.resize(face_crop, (int(crop_w*scale), int(crop_h*scale)),
                           interpolation=cv2.INTER_CUBIC)

# Save at high quality
cv2.imwrite(filename, face_crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
```

---

## Performance Tuning

| Parameter | Value | Notes |
|-----------|-------|-------|
| `INFER_W/H` | 640×640 | Best accuracy; use 320 if CPU only |
| `CONF_THRESH` | 0.35 | Lower = more detections, more FP |
| `FACE_COOLDOWN` | 10s | Seconds between face saves per channel |
| `FACE_MIN_SIZE` | 20px | Skip tiny faces |
| `inference_lock` | Required | OpenVINO compiled model is NOT thread-safe |

### Expected throughput on this hardware
- GPU (Iris Xe): ~15-25 FPS per channel at 640×640
- CPU fallback: ~5-10 FPS per channel at 640×640
- 9 channels: expect 1-3 FPS per channel when batched

---

## Model Versioning

```bash
# Keep exports tagged by date
mv yolo11s_openvino_model/ yolo11s_openvino_model_2025-05-04/
ln -s yolo11s_openvino_model_2025-05-04/ yolo11s_openvino_model

# Always test after re-export
python3 -c "
import openvino as ov, numpy as np
core = ov.Core()
m = core.compile_model('yolo11s_openvino_model/yolo11s.xml', 'CPU')
dummy = np.zeros((1,3,640,640), np.float32)
out = list(m([dummy]).values())[0]
print('Output shape:', out.shape)  # expect: (1, 84, 8400)
"
```

---

## Future: Facial Recognition with CompreFace

For true person identification (not just face detection):
- **Double Take** + **CompreFace** stack
- CompreFace runs as Docker container
- Training: add labeled face images per person
- At inference: send YuNet crop → CompreFace → get person name + confidence
- Integrate into `face_snapshot_worker()` to log who was seen, when

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `shape=[1,3,640,640] vs tensor=(1,3,320,320)` | imgsz mismatch | Match `INFER_W/H` to export imgsz |
| `GPU not in available_devices` | Driver issue | Falls back to CPU automatically |
| YuNet: `FileNotFoundError` | ONNX not downloaded | `wget` the model file |
| Zero faces detected | Frame too dark / face too small | Lower `score_threshold`, raise `FACE_MIN_SIZE` |
| Very slow inference | Running on CPU, not GPU | Check `log(f"Device: {OV_DEVICE}")` output |

---

## SOP-OPS-04 — Verifying and Installing OpenClaw Skills from ClawHub

Target audience: System Administrator (`olekamole`)

Objective: Establish a strict technical verification process to prevent malicious payloads, unauthorized credential harvesting, or compromised helper binaries from infecting the OpenClaw agent framework during custom skill installations.

### Pre-Installation Verification Workflow

1. Verify the VirusTotal badge.
   - Dashboard inspection: before downloading or cloning any skill repository, open the ClawHub dashboard and locate the target skill.
   - Look for the automated VirusTotal scan certificate.
   - Rule: never install or run a skill that lacks a clean, updated scan certificate or displays a failed security flag.

2. Inspect for rogue binaries and prompts.
   - Dependency check: review the skill documentation, installation scripts, and initialization prompts.
   - Run the preinstalled static scanner before any install attempt: `/home/olekamole/scripts/openclaw-skill-audit.sh /path/to/extracted/skill/directory`.
   - Be highly suspicious of any custom skill that asks to install external helper binaries or utilities, including `openclaw-core` lookalikes or `AuthTool`.
   - Red flags: prompts requesting the download of separate installer packages, executable binaries, or password-protected `.zip` files.
   - Legitimate OpenClaw skills should rely on standard Python dependencies or native OpenClaw bindings.

3. Enable interception wrappers.
   - Framework-level shielding: before executing the skill within the active runtime environment, ensure network and runtime interception tools are active.
   - Initialize security wrappers such as `ClawNet` or `openclaw-shield` when available.
   - These tools operate at the framework level to intercept incoming skill calls, forcing the LLM model to analyze script code for hidden payloads or obfuscated commands before execution.

4. Execute post-install sandboxing.
   - Isolate and test: install the skill into an isolated Python environment.
   - Run a localized test loop to confirm the skill only accesses the specific APIs, devices, or folders it explicitly requires for accounting, tracking, or automation functions.

### Security Verification Checklist

| Verification Step | Target Indicator | Action if Failed |
|-------------------|------------------|------------------|
| Payload Integrity | VirusTotal clean stamp | Abort installation immediately |
| Static Skill Audit | `/home/olekamole/scripts/openclaw-skill-audit.sh` passes with no critical alerts | Abort installation on critical alerts; manually review warnings |
| Dependency Check | No external `.zip` or unverified `.exe` / `.bin` tools requested | Reject skill and isolate the repo |
| Runtime Control | `openclaw-shield` active and intercepting scripts | Halt framework until shield is active |

### Operational Enforcement

- The scanner is installed at `/home/olekamole/scripts/openclaw-skill-audit.sh`.
- The aggregate guard is installed at `/home/olekamole/scripts/openclaw-skill-audit-all.sh`.
- The user systemd timer `openclaw-skill-audit.timer` runs the audit every 15 minutes and after boot.
- The user systemd path unit `openclaw-skill-audit.path` runs the audit when OpenClaw skill/plugin directories change.
- The user systemd timer `openclaw-skill-audit-enforcer.timer` checks every 10 minutes that the audit timer and path unit remain enabled and active.
- Logs are written under `/home/olekamole/.openclaw/logs/security/`.
- User lingering must remain enabled for boot persistence: `loginctl show-user olekamole -p Linger` should return `Linger=yes`.
