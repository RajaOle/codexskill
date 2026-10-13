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

The paired Google server now uses `table-tools.js`: automatic live header discovery, named-field data writes, backend row selection, idempotent keys, concurrent-change checks and full readback. No manual table registration. `initialize_table` creates a new/entirely blank table once; populated/preformatted templates cannot be overwritten. Existing reference/template cells and formulas remain protected. Raw mutation routes cannot bypass table protection. Human edits/direct API clients remain outside its lock; Google writes are not cross-client transactions.

Document support: DOCX/DOCM, XLSX/XLSM, PPTX/PPTM, ODT/ODS/ODP via bounded Python ZIP/XML extraction; DOC/XLS/PPT/RTF via isolated-profile LibreOffice with macros disabled. Text, CSV/TSV, JSON/XML/HTML are read as inert text. Embedded Office images are not OCRed by direct extraction; stored spreadsheet values are not recalculated. Expansion limit 40 MiB/10000 entries. Text chunks have `nextChar`; continue using `start_char`. PDFs expose page continuation; finish text continuation within the current page chunk first. Drive documents use `gdrive__read_document` with the same local reader. No external uploads or messages.

Private catalogs, attachments, transcripts, tokens, operational backups and live config must never be synced to the public Markdown backup repository.
