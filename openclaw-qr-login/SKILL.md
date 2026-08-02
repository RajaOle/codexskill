---
name: openclaw-qr-login
description: Present OpenClaw QR-based channel or device login in a human-scannable local HTML page. Use whenever an OpenClaw login emits a terminal QR, especially WhatsApp Linked Devices.
---

# OpenClaw QR Login

Never present terminal ASCII/ANSI QR output as the user-facing result.

1. Start the requested OpenClaw login in a PTY with network access.
2. Capture its terminal output with `script -q -f`.
3. Keep the login process running while the QR is valid.
4. Run `/home/olekamole/scripts/openclaw_qr_to_html.py` against the capture.
5. Serve the HTML on a loopback HTTP server.
6. Give the user both:
   - a clickable absolute file link
   - the exact `http://127.0.0.1:<port>/<file>.html` URL
7. After scanning, wait for login completion and verify with `openclaw channels status`.
8. Never run a live outbound message as a login test.

If the QR expires or the login process exits, regenerate the capture and HTML. Do not reuse an old QR.
