# Google Drive, Sheets, and Document Access

Google access through gdrive is independent of local workspace restrictions. Mili may create internal workbooks/tabs/templates and initial headers within authorized tasks. Mili cannot change existing headers/templates/formulas. inspect_table can safely adopt human-added columns or an empty Phone / Email split; incompatible layout changes remain blocked. No manual schema registration.

## Sheets tools

Read SHEET_WRITE_RULES.md for every Sheets task.

- gdrive__sheet_metadata: workbook tabs and metadata.
- gdrive__inspect_table: automatic live header discovery/protection; returns field names and next row.
- gdrive__initialize_table: create a new tab or initialize an entirely blank tab once; headers plus optional title/description. Never overwrites populated/preformatted templates.
- gdrive__write_table_records: objects keyed by exact headers, keyColumn, mode=insert|upsert. Backend maps columns/selects rows, preserves unspecified fields/formulas, detects duplicates/concurrent edits and verifies results. Use instead of raw range writes.
- gdrive__create_spreadsheet: private workbook, then initialize required tabs. No extra approval for setup within the user's internal task.
- gdrive__read_sheet_range / gdrive__read_sheet_formula_range: focused values/formula reads. Prefer these over read_sheet (whole workbook).

Original reference workbooks/Reference Lists and dedicated accounting ledgers retain their protections. No structural or file-replacement bypass. Match the user's existing bank tab.

## Drive and documents

- gdrive__auth_status: connection check without reading credentials.
- gdrive__list_files: exact business filename or relevant known parent folder. Never scan account by modification date or generic document type to locate an attachment.
- gdrive__get_folder_id: named business folder.
- gdrive__read_file: metadata/downloaded/exported content; supported Office documents return extraction. Check extraction status and continuation; base64 alone is not readable evidence.
- gdrive__read_document: extract an exact Drive document as readable text, including Office/OpenDocument, PDF/scans/images and text. Continue with start_page=nextPage or start_char=nextChar; no user conversion step.
- gdrive__create_file: private inline-text files/folders, inherited sharing.
- gdrive__update_file: authorized ordinary non-template edits/moves; preserve historical/executed documents. Never replace protected Sheet templates.
- gdrive__delete_file: explicitly authorized exact non-template files only; prefer trash, never delete old records automatically.
- web_search / web_fetch: relevant public research; cite material source/date. No private details in search queries.

For WhatsApp documents read ATTACHMENT_OCR.md and use catalog tools. DOCX/Office formats now support local extraction. An unsupported channel preview does not justify asking for conversion before using the reader.

Verify Ibnu/Sindy from trusted metadata. Use direct links/known IDs first. Company address questions consult records/company/ENTITY_AND_OFFICES.md and memory before Drive searches. Complete authorized internal tasks and report verified results briefly. External commercial messages, sharing and financial commitments retain SECURITY.md boundaries. Report all actual blockers together; no invented registration prerequisite.
