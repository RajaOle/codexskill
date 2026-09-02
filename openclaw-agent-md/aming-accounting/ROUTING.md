# Aming Accounting Routing

This is a redacted public backup note for the local OpenClaw routing change.

## Runtime Intent

- Dedicated agent id: `aming-accounting`
- Display identity: `Aming`
- Linked WhatsApp account: `default`
- Linked WhatsApp number: redacted, single owned number ending in `6479`
- Accounting group: `120363409581382436@g.us`
- Goodpass direct chats remain routed to `goodpass-admin` on the same `default` WhatsApp account.

## Operational Policy

The accounting group uses a lean workflow:

- Use the faster flash model with reasoning/thinking disabled by default.
- Keep tool access scoped to messaging, receipt image/OCR support, and Google Drive/Sheets accounting actions.
- Avoid broad code, gateway, session, browser, web, generation, voice, and unrelated business tools.
- For ordinary expense requests, do not inspect monthly rollover, total rows, historical schemas, or unrelated months unless explicitly asked or formula validation fails.
- Do a minimal duplicate check, write only the required input cells, verify formulas/readback, then send a short result to the source group.

## Safety Notes

- This file intentionally excludes full phone numbers, credentials, tokens, spreadsheet-private values, attachments, transcripts, and runtime state.
- Do not use live WhatsApp delivery tests for this route. Use local dry-run or direct plugin/unit tests only.
