---
name: coding
description: "Software engineering skill for reading, writing, fixing, refactoring, testing, and reviewing code. Trigger for any code task: new features, bug fixes, code review, documentation generation, test writing, or understanding an existing codebase."
---

# Coding & Software Engineering

## Core Principles

- **Read the full file first** before editing — never patch blindly
- **Return the complete revised file** — no snippets, no diffs; the user should be able to copy-paste and replace
- **Explain the why** — one sentence per change is enough
- **Python 3.11** is the target for all AI/CV work on this machine
- **OpenClaw prompt budget** — when designing OpenClaw agents, keep runtime-loaded `AGENTS.md` under 20,000 bytes. Use `AGENTS.md` as a compact router/table of contents and place detailed persona, workflows, examples, SOPs, and knowledge in separate files loaded on demand.

---

## Workflow

### Understanding a Codebase
1. List the directory structure first (`ls -la`, `find . -name "*.py"`)
2. Read entry points and main files
3. Identify imports and dependencies
4. Note threading, async, or subprocess patterns
5. Summarize architecture before suggesting changes

### Writing New Features
1. Check existing patterns in the file — match the style
2. Identify shared state, locks, or queues that the feature must integrate with
3. Write the feature with error handling included
4. Add a brief comment block above complex logic
5. Return the full revised file

### Bug Fixing
1. Reproduce the error mentally from the traceback or description
2. Find the root cause (not just the symptom)
3. Check for related bugs in nearby code
4. Fix, then verify no other call sites are broken
5. Return the full revised file

### Refactoring
1. Do not change behavior — only structure
2. One concern per refactor (e.g., extract a function, or rename, not both)
3. Preserve all existing comments unless they're wrong
4. Return the full revised file

### OpenClaw Agent Prompt Engineering
1. Design the always-loaded `AGENTS.md` as a bibliography, load order, and routing contract, not the full prompt body.
2. Keep `AGENTS.md` below 20,000 bytes before runtime testing; prefer a target below 18,000 bytes to leave room for future edits.
3. Move bulky details into route-specific files such as `SECURITY.md`, `CUSTOMER_JOURNEY.md`, `TOOLS.md`, `FOLLOW_UP.md`, `CONVERSATION_STYLE.md`, and `knowledge/*.md`.
4. Preserve capability by replacing removed detail with explicit route instructions that tell the agent which file to read for each case.
5. Verify with `wc -c AGENTS.md` and a local non-delivery dry run; never use live WhatsApp delivery for prompt-size testing.

---

## Python-Specific Rules (this machine)

```python
# ✅ Correct inference device check
import openvino as ov
core = ov.Core()
INFER_DEVICE = "GPU" if "GPU" in core.available_devices else "CPU"

# ✅ Correct pip for system Python
pip install package --break-system-packages

# ✅ Use pyenv for AI work
pyenv shell 3.11.x
python -m venv venv
source venv/bin/activate

# ❌ Never
device = "cuda"
torch.cuda.is_available()  # always False on this machine
```

### Threading pattern (NVR pipeline)
```python
# Always use per-channel locks
raw_locks[ch]  = threading.Lock()   # protects raw frame
disp_locks[ch] = threading.Lock()   # protects annotated frame
inference_lock = threading.Lock()   # OpenVINO compiled model is NOT concurrent-safe

# Use daemon=True for background threads
threading.Thread(target=fn, args=(ch,), daemon=True).start()
```

### RTSP reconnection pattern
```python
def grab_frames(ch):
    while True:
        ret, frame = caps[ch].read()
        if ret:
            with raw_locks[ch]:
                raw_frames[ch] = frame
        else:
            time.sleep(0.1)
            caps[ch] = cv2.VideoCapture(build_rtsp(ch))
            caps[ch].set(cv2.CAP_PROP_BUFFERSIZE, 1)
```

---

## Code Review Checklist

- [ ] No hardcoded credentials or IPs (use constants at top or env vars)
- [ ] All threads use daemon=True
- [ ] Shared state protected by locks
- [ ] RTSP streams have reconnect logic
- [ ] OpenVINO device checked at runtime, not hardcoded
- [ ] No `device="cuda"` anywhere
- [ ] Exception handling in inference and file I/O blocks
- [ ] Logging uses timestamps for long-running processes

---

## Testing

For CV/tracking scripts, test by:
1. Run with a single camera stream first
2. Check `[INFER]` log lines confirm GPU device
3. Verify face crops saved to `known_faces/` with expected dimensions
4. Check FPS counter in display window
5. Let run 10+ minutes to confirm no memory leak or thread deadlock

---

## Git Commit Conventions

```
feat(tracker): add multi-face sorting by area
fix(stream): handle RTSP disconnect on channel probe
refactor(infer): extract postprocess into helper function
docs(readme): add pyenv setup instructions
```
