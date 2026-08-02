#!/usr/bin/env python3
"""Convert a captured OpenClaw terminal QR into a scannable local HTML page."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path


ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
QR_BLOCK_RE = re.compile(r"[\u2580-\u259f]")


def extract_qr_lines(source: Path) -> list[str]:
    text = source.read_text(encoding="utf-8", errors="replace")
    clean = ANSI_RE.sub("", text).replace("\r", "")
    lines = [line for line in clean.splitlines() if QR_BLOCK_RE.search(line)]
    if len(lines) < 10:
        raise ValueError("No complete terminal QR matrix was found")
    return lines[-32:]


def render_html(lines: list[str], title: str) -> str:
    qr = "\n".join(html.escape(line, quote=False) for line in lines)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #eef1f4;
      color: #17191c;
      font-family: system-ui, sans-serif;
    }}
    main {{
      width: min(94vw, 980px);
      padding: 24px;
      text-align: center;
    }}
    h1 {{ margin: 0 0 8px; font-size: 24px; letter-spacing: 0; }}
    p {{ margin: 0 0 20px; color: #4d535b; }}
    .qr-wrap {{ overflow: auto; padding: 8px; }}
    pre {{
      display: inline-block;
      margin: 0;
      padding: 18px;
      border: 1px solid #c8cdd3;
      background: #fff;
      color: #000;
      font-family: "DejaVu Sans Mono", "Liberation Mono", monospace;
      font-size: 12px;
      font-weight: 400;
      line-height: 1;
      letter-spacing: 0;
      text-align: left;
      white-space: pre;
    }}
    small {{ display: block; margin-top: 16px; color: #69717b; }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
    <p>WhatsApp → Linked devices → Link a device, then scan this QR.</p>
    <div class="qr-wrap"><pre>{qr}</pre></div>
    <small>This QR is temporary. Regenerate the page if WhatsApp reports that it expired.</small>
  </main>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--title", default="Yasmin WhatsApp Login")
    args = parser.parse_args()

    lines = extract_qr_lines(args.source)
    args.output.write_text(render_html(lines, args.title), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
