# Aming Accounting Routing

This is a redacted public backup note for the local OpenClaw routing change.

## Runtime Intent

- Dedicated agent id: `aming-accounting`
- Display identity: `Aming`
- Linked WhatsApp account: `default`
- Linked WhatsApp number: redacted, single owner-approved account
- Accounting group identifiers: redacted; maintain mappings only in private runtime configuration
- Goodpass direct chats remain routed to `goodpass-admin` on the same `default` WhatsApp account.

## Operational Policy

The accounting group uses a lean workflow:

- Aming handles two separate businesses: Mouru and Orvena International Trading. Resolve the business from the source group before loading modules, opening files, or writing a ledger.
- Primary model: `deepseek/deepseek-flash`; fallback: `deepseek/deepseek-v4-flash`. Gemini is not configured for Aming.
- Receipt extraction uses Tesseract and approved OCR tools. DeepSeek structures OCR text; it does not fill unreadable fields. Aming has no image model configured.
- Keep tool access scoped to messaging, receipt image/OCR support, and Google Drive/Sheets accounting actions.
- Avoid broad code, gateway, session, browser, web, generation, voice, and unrelated business tools.
- For ordinary expense requests, do not inspect monthly rollover, total rows, historical schemas, or unrelated months unless explicitly asked or formula validation fails.
- Do a minimal duplicate check, write only the required input cells, verify formulas/readback, then send a short result to the source group.
- Keep Mouru and Orvena separate. Load the project-specific module rather than importing another company's template.
- Orvena/Sindy entries use only `gdrive__record_expense`: row 3 is the immutable header, data starts at row 4, A:E and G are inputs, and F is a protected formula.
- The backend rejects raw/structural mutations of the registered Sindy workbook and chooses the next business row itself.
- After a provider error or timeout, inspect the live ledger before retrying and reuse uploaded receipts. Never replay completed side effects blindly.

## Safety Notes

- This file intentionally excludes full phone numbers, credentials, tokens, spreadsheet-private values, attachments, transcripts, and runtime state.
- Do not use live WhatsApp delivery tests for this route. Use local dry-run or direct plugin/unit tests only.
