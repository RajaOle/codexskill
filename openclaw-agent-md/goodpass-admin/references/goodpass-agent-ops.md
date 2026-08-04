# Goodpass Agent Operations

Use this file for Goodpass WhatsApp entry, delivery, auth, onboarding, KYC, reports, paid detailed search, and workflow/tool behavior.

## WhatsApp Entry Rule

For any Goodpass WhatsApp direct message that is only a greeting, menu request, help request, or clearly re-opens the conversation, such as `halo`, `halo goodpass`, `hi`, `hello`, `pagi`, `siang`, `malam`, `menu`, `start`, `mulai`, `help`, `bantuan`, `fitur`, `apa saja menunya`, or similar short openers, treat it as a session-entry message even if OpenClaw is continuing an older persisted DM session.

For these entry messages:

1. If the verified sender phone is available in runtime context, call `goodpass_user_status` first.
2. If `goodpass_user_status` is unavailable, denied, or fails, do not use command, shell, exec, HTTP fallback, local API fallback, or debug inspection. Show the public Goodpass entry menu from `references/goodpass-chat-sop.md` and add one short line: `Status akun dan saldo kredit sementara belum bisa dicek.`
3. Do not show raw `[goodpass admin]` or `[Goodpass Admin]` status lines to WhatsApp users.
4. If the user is signed up or signed in, show the authenticated Goodpass menu from `references/goodpass-chat-sop.md` with the user's registered `public.profiles` name or WhatsApp display name and the exact remaining credit balance.
5. If the user is not registered, show the public Goodpass entry menu from `references/goodpass-chat-sop.md`.
6. Do not reply with casual small talk like `Halo juga` for these entry messages.

If `goodpass_user_status` fails, still show the public entry menu and use:

`Status akun dan saldo kredit sementara belum bisa dicek.`

## WhatsApp Delivery Rule

For every visible Goodpass WhatsApp direct-message reply, send the user-facing text with the `message` tool using `action: "send"`, `channel: "whatsapp"`, and the current verified sender/chat phone as `target`.

Do not rely on plain assistant text as the final delivery path. Plain assistant text may remain internal and not reach WhatsApp.

Send only the final user-facing message through the tool. Do not expose tool names, local paths, internal routing, logs, or debug details in the WhatsApp text.

One inbound user turn may produce at most one outbound WhatsApp message. Never send progress, loading, waiting, fetching, or placeholder messages. If the required capability is unavailable, send one concise limitation or next-step message. After the first successful `message` send, make no more tool calls and return exactly `NO_REPLY`.

## Policy Reference Use

When asked about Goodpass privacy, terms, additional terms, confidentiality, report inquiry, acceptable use, liability, or user rights, read the relevant reference file before answering unless the exact policy point is already present in `MEMORY.md` or startup context.

Do not invent policy language. Summarize accurately, mention the source document by name, and avoid long quotes.

## KYC and Report Creation

KYC is not a gate for creating a new report.

- During `buat laporan baru`, never check KYC status, never ask for KTP, and never start KYC intake.
- If a report draft is complete, show the report summary and ask for confirmation.
- After the user confirms, call `goodpass_report_draft_submit`.
- If `goodpass_report_draft_submit` succeeds, tell the user the report was submitted.
- If `goodpass_report_draft_submit` fails with a KYC-related error, say the system still has an old KYC gate and tell the operator/admin; do not ask the WhatsApp user to complete KYC for report creation.
- KYC is required only for `cek data detail` / paid detailed search.

For KYC:

- Ask for the minimum next input.
- Use OCR results when available.
- If the user confirms the KTP is theirs, submit the complete KYC draft without asking for a second confirmation.
- Do not echo full NIK, full KTP address, or other sensitive KYC data back into chat.

## WhatsApp Auth and Onboarding Tools

For WhatsApp sign up, sign in, login, register, profile, or KYC requests, first read `references/goodpass-whatsapp-auth-flow.md` and use the Edge Function magic-link hot path. Do not use Supabase OTP.

Goodpass onboarding still goes through the local FastAPI backend unless the auth-flow reference says otherwise.

Legacy tool:

- `goodpass_whatsapp_auth`
- Input: one WhatsApp phone number in the POST body.
- Output: login/signup status, `user_id`, and `requires_onboarding`.
- Trust boundary: because the request came from the verified WhatsApp channel, the WhatsApp phone number is the phone-verification layer. Do not ask for SMS OTP and do not call Supabase OTP flows.

Current tools:

- `goodpass_user_status`: input is one verified WhatsApp phone number. Output says whether the phone is not yet registered or signed up/signed in, plus `user_credits.credits_remaining`.
- `goodpass_select_onboarding_type`: input is `user_id` and `type`, where `type` is `company` or `individual`. Company is supported; individual is not implemented yet.
- `goodpass_company_onboarding_start`: input is `user_id` and existing `company_id`. Output is draft onboarding status for that company.
- `goodpass_generate_onboarding_link`: input is `user_id` and existing `company_id`. Output is a secure onboarding URL using `?t=<token>` for WhatsApp CLI delivery.
- `goodpass_kyc_draft_upsert`: input is verified WhatsApp phone plus collected profile/KYC fields and optional `ktp_image_path` or `ktp_image_base64`.
- `goodpass_kyc_draft_status`: input is verified WhatsApp phone. Output is local draft status and missing fields.
- `goodpass_kyc_draft_submit`: input is verified WhatsApp phone. Output is submitted pending KYC record after matching the phone to `auth.users`.
- `goodpass_report_draft_upsert`: input is verified WhatsApp reporter phone plus collected report fields, reportee identity fields, chronology, and optional local evidence file paths.
- `goodpass_report_draft_status`: input is verified WhatsApp reporter phone. Output is local report draft completeness and missing fields.
- `goodpass_report_draft_submit`: input is verified WhatsApp reporter phone. Output is submitted report identifiers after matching the phone to `auth.users`.

Display rule: after sign up/sign in, and whenever an authenticated Goodpass menu is shown, do not include raw `[goodpass admin]` or `[Goodpass Admin]` status lines. Use returned status internally, then display the authenticated menu from `references/goodpass-chat-sop.md` with the exact `user_credits.credits_remaining` balance. Do not guess credit balances.

For Add New Report, follow `references/goodpass-chat-sop.md`. Draft locally first with `goodpass_report_draft_upsert`, confirm with the user, then submit with `goodpass_report_draft_submit`. Do not call Supabase report tables directly from OpenClaw.

## Onboarding Link Rules

When a user asks to onboard or continue onboarding through WhatsApp after auth, use the verified WhatsApp sender number from channel context if available; otherwise ask for their WhatsApp number.

If onboarding is required, continue onboarding questions in WhatsApp first. Once an existing company row is available, call `goodpass_company_onboarding_start`.

Only call `goodpass_generate_onboarding_link` when file upload or web confirmation is needed, then send that secure link through WhatsApp.

The web link must use a secure token parameter like `?t=...`, never a raw phone number. Do not expose Supabase service role keys, database rows, backend internals, or raw token hashes.

For testing only, the FastAPI backend verifies the clicked onboarding token with the service role and sets the company member invitation accepted. Treat this as temporary plumbing. Once user-token auth is ready, the clicked web app must continue as the authenticated user and use user-scoped Supabase access, not service-role access.

## Paid Detailed Search

Paid detailed search can run inside WhatsApp through `goodpass_paid_search_submit` after public search, candidate selection, completed KYC, and explicit agreement to the additional terms plus 10-credit deduction.

OpenClaw must never hold or send Supabase service-role credentials. The MiniPC signs the request with `WHATSAPP_PAID_SEARCH_SECRET`, and the Edge Function keeps service-role access server-side.

Mandatory preflight before `goodpass_paid_search_submit`:

- Always verify reporter profile readiness using the verified WhatsApp sender phone in the format expected by the paid-search backend.
- If reporter profile is missing, do one automatic create/repair/sync attempt first, then continue to submit once the profile is available.
- If profile is still missing after one repair attempt, stop and send only one user-facing next step, then wait for user reply. Do not keep retrying in a loop.

Strict fallback discipline:

- Never expose internal debug details to WhatsApp users.
- On paid-search failures, use max one or two short user messages: one failure notice and one next action only.
- Do not enter investigative/debug chat mode with end users.

Paid-search source-of-truth rules:

- For `cek data detail`, the only allowed data source is the successful `goodpass_paid_search_submit` tool result for that same request.
- Never compose detailed-report values from reminders, memory notes, old chats, script files, cron text, or guessed/inferred values.
- Never substitute `loan amount` or reminder amount as `outstanding`. Use the paid-search field for outstanding balance exactly as returned.
- If a required field is missing in the paid-search result, say the field is not available; do not fill it from another source.
- If paid-search submit fails or returns no valid result, do not send any report detail content.

Paid-search delivery boundary:

- Return paid-search details only to the same authenticated WhatsApp requester who initiated and consented to that paid search.
- Do not forward paid-search detail content to another phone number or third party from inside the same flow.

Paid-search results are read-only. Do not turn a paid-search result into an active-report management context.

Report mutation actions such as repayment proof, restructure, add info, document changes, or status changes require active-report ownership/authorization through the relevant tools, even when the WhatsApp sender is the configured boss/admin phone.

Boss/operator identity allows local operations requests. It does not bypass Goodpass product authorization in user-facing workflows.

## STOP Rule

If the user sends `stop` or `STOP`, immediately halt the current workflow and clear pending follow-up steps for that flow.

After `STOP`, send one short acknowledgement only. Do not continue with queued operational messages.
