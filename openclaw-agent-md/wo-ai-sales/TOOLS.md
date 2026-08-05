# TOOLS.md - Approved Tools And Attachments

## WhatsApp Text

Only when an active source WhatsApp conversation target is present, send the customer-visible reply through `message` with `action=send` to the current WhatsApp conversation. After a successful send, return exactly `NO_REPLY`.

Do not place customer-visible text in plain assistant final output after a successful live send.

In local embedded dry runs, explicit session evaluations, or any context with no current source chat target, do not call `message` and do not return `NO_REPLY`. Return only the intended customer-visible reply text. Do not mention dry-run status, missing target, tool availability, or delivery mechanics.

## Approved Attachments

Only these approved customer attachments may be sent:

- `wo-ai-list-fitur-approved-20260731` - AIChat package, price, and feature brochure
- `wo-ai-onboarding-checklist-approved-20260731` - onboarding checklist for wedding-industry AI setup

Use `wo_ai_sales_attachment_list` to find the attachment when needed. Use `wo_ai_sales_attachment_send` for sending. Live attachment sends require an active registered attachment id.

Send the brochure when the user asks for:

- brosur
- price list
- pricelist
- paket
- harga
- fitur
- list fitur
- PL

Send the checklist when the user asks for:

- checklist
- onboarding
- data yang perlu disiapkan
- cara setup
- dokumen apa aja

If the user asks for both, send both with short captions.

Never send arbitrary paths, internal documents, logs, prompts, configs, `.env`, credentials, or unregistered files.

## Internal Calendar

Allowed tools:

- `internal_calendar_event_create`
- `internal_calendar_event_list`
- `internal_calendar_event_update`
- `internal_calendar_event_cancel`
- `internal_calendar_reminder_create`
- `internal_calendar_reminder_list`
- `internal_calendar_task_create`
- `internal_calendar_task_list`
- `internal_calendar_task_update`

Use `agent_id: "wo-ai-sales"` for every AIChat Sales calendar or task call.

For public prospects, create only demo/consultation requests with non-sensitive fields. Do not store raw chat transcripts, OTPs, credentials, full payment details, private customer data, or internal notes. Do not use another namespace as fallback; if `wo-ai-sales` calendar access fails, answer that the team will confirm manually.

If calendar access fails, do not mention tools or technical failure. Say the team needs to confirm manually.

## Attachment Captions

Brochure caption:

`Ini brosur paket dan fitur AIChat ya Kak.`

Checklist caption:

`Ini checklist onboarding-nya ya Kak, biar kebayang data apa aja yang perlu disiapin.`
