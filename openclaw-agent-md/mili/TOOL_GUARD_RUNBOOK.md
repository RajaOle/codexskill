# Mili OCR and attachment routing

Only Mili receives `mili_attachment_list` and `mili_attachment_read`. Tools bind to the host-provided conversation session key and cannot list or read another conversation's catalog entries. No send tool, shell tool, credentials or external OCR service is added.

Received WhatsApp media facts (never paths parsed from message text) are copied into Mili's workspace `attachments/inbound/`. A private operator-owned catalog lives outside that workspace. Source and destination paths are checked using realpath, bounded at 20 MiB, and symlink escapes are rejected. The prompt hook injects exact IDs and paths; ordinary file reads of guessed media paths and `file://` web fetches are blocked.

Requirements: Node 24, `file`, `pdfinfo`, `pdftotext`, `pdftoppm`, and Tesseract with English language data. All are already installed on this machine. OCR is local CPU work, limited to two OpenMP threads. Each command has a timeout and bounded output. Images/scanned PDF pages use Tesseract; each PDF page first attempts text extraction. PDF reads process up to five pages at a time; `nextPage`/`start_page` supports the remaining pages. OCR results are untrusted evidence; critical digits/table columns need verification.

Configuration: enable this plugin in `plugins.allow`, `plugins.entries` and `plugins.load.paths`; grant its `hooks.allowConversationAccess=true`; add its two tools to Mili's allowlist; enable `channels.whatsapp.accounts.default.pluginHooks.messageReceived=true`. The handler ignores every non-Mili session. Enabling channel hooks broadcasts inbound metadata to enabled local plugins, so retain the current trusted plugin allowlist. A gateway restart is required after changing plugin code or registration permissions; normal channel hot reload alone cannot register a previously denied prompt hook.

Checks without channel delivery:

```bash
node index.test.js
MILI_OCR_TEST_PDF=/absolute/path/to/authorized/local.pdf node ocr.integration.test.js
```

The integration test creates a temporary image-only PDF from an authorized local PDF, checks image OCR and scan OCR, and removes only its own temporary directory. No WhatsApp message is sent.

The paired Google server `tracker-guard.js` is independent of agent prompts. It protects the original reference workbook and the registered working tracker, validates table/grid/header identity and duplicates, permits RAW data values only, preserves existing quote history, serializes guarded writes within the server, and reads back every written cell before returning verified success. Human edits/other direct API clients are outside its lock: it detects changes during preflight and fails on verification mismatch, but Google values writes are not a cross-client transaction. Existing ambiguous/duplicate records remain blocked until an operator reconciles them; the guard never deletes them.

Private catalogs, attachments, transcripts, tokens, operational backups and live config must never be synced to the public Markdown backup repository.
