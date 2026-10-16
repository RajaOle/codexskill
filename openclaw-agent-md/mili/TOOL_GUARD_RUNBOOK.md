# Mili Sheets and Documents — Operator Notes

Manual table schema registration removed on 2026-10-13. Current runtime uses gdrive/table-tools.js: inspect_table discovers live header fields and automatically snapshots the existing title/header values; write_table_records maps objects keyed by those fields and selects rows. initialize_table creates a tab or initializes a completely blank, unformatted tab once. Existing headers/templates/formulas remain immutable. Newly created workbooks join protection automatically. Private snapshots live outside Mili's workspace in gdrive/table-state.json; never publish them.

Existing original reference workbook, Reference Lists and dedicated expense ledgers retain protection. Existing legacy supplier/price definitions are type/history validators, not a list limiting writable tables. Mili's attachment plugin blocks raw Sheet mutations and broad account scans. Backend rejects raw mutation/file-replacement routes on protected workbooks; named-field writes use RAW literals, target-only updates and full readback. Same-server writes serialize; human edits and other direct Google clients are detected during preflight/readback but are not part of a Google cross-client transaction.

Mili attachments: only trusted host-routed media is staged, conversation catalog isolation retained. DOCX/XLSX/PPTX/OpenDocument extraction is local bounded ZIP/XML; legacy DOC/XLS/PPT/RTF uses installed LibreOffice with macros disabled in an isolated profile. PDF/image OCR uses Poppler/Tesseract. Source size 20 MiB; expanded Office size 40 MiB/10000 entries; output 40000 characters/5 PDF pages per call, with continuation. Office embedded images require separately readable images/PDF for OCR; spreadsheet values are cached/raw, not recalculated. Corrupt/encrypted documents fail explicitly.

Checks: node table-tools.test.js; node tracker-guard.test.js; node crud.test.js; node expense-guard.test.js in gdrive. In mili-attachments: node index.test.js; python3 document.test.py; node document.integration.test.js. OCR integration accepts MILI_OCR_TEST_PDF. Behavior-only runs follow OPENCLAW_AGENT_DRY_RUN_SOP.md; no delivery or message tests.

After code/tool allowlist changes restart openclaw-gateway.service and verify registered tools/health. Never sync catalogs, table-state.json, transcripts, tokens, received documents, live config or private memory to public backup. Publish only sanitized instructions/source.

## Safe human column changes (2026-10-14)

inspect_table performs two stable reads before adopting additive human column changes on operational tables, including an empty Phone / Email split into adjacent Phone and Email columns. All other old fields must remain in order; titles/instruction rows stay exact. Previous header/template snapshots are retained privately in revisions. No Sheet cells, formatting, validation or formulas change during adoption. Writes do not refresh snapshots: inspect first, then write with exact new field names. Legacy positional supplier/price schemas and expense/reference templates cannot refresh. Renames, removals, reorders, populated mixed-contact splits and formula/duplicate headers fail closed. Concurrent edits still block preflight/readback. Mixed Phone / Email validation accepts either contact type; dedicated fields retain strict typing. Never reset table-state.json to bypass a blocker.


## Supplier validator recovery (2026-10-16)

Supplier Master validation now compares planned data to the exact preflight baseline. Historical duplicate Supplier ID/company groups may remain only with identical full rows at identical positions. Existing noncanonical historical IDs may remain only in unchanged rows. New IDs still require SUP-<digits>, new collisions and edits to ambiguous rows fail, and all header/formula/type/dropdown/concurrency/readback checks remain. Error text names the actual row and invalid ID. Do not recommend renaming to SUP-001-H1: that is not a valid new ID. An unrelated import must proceed without rewriting old duplicates.

AGENTS.md is a compact task router; OPERATIONS.md holds the full operating reference. Startup no longer requires loading every reference or reviewing unrelated inbox/workbook queues. Live replies occur once after completion; behavior tests use the existing no-delivery SOP. Never create production probe rows or workbooks for tests.
