# Mili Zoho Mail

OpenClaw plugin for one primary Zoho mailbox. Eight tools provide connection status, folders, search, email content, draft creation, approved plaintext sending, read/unread/archive/move updates and reversible Trash deletion. No organization administration or permanent purge. No third-party packages required; Node 22+ with JSON.rawJSON.

Only Mili receives tools. Every execution checks runtime requesterSenderId against private authorized-users.json; tool arguments cannot set sender identity. OAuth credential is kept outside agent workspace. Each token refresh verifies the expected primary ZOHO_ACCOUNT mailbox, then fixes every request to that account. HTTPS endpoints come from a fixed region map; arbitrary URLs and account IDs are never accepted. IDs retain integer precision. Redirects and automatic network retries are disabled. Draft/send operations use durable request IDs to suppress concurrent/restart retries; uncertain outcomes require inspection.

The send approval flag is asserted by Mili after interpreting an authorized user's actual instruction. This is not an independent human confirmation service. Prompt-injection rules and exact recipient/content approval remain in ZOHO_MAIL.md and SECURITY.md.

## Private setup

Default state directory: `~/.openclaw/zoho-mail-sindy` (or MILI_ZOHO_STATE_DIR). Directory 0700, files 0600. Never publish credentials.json, authorized-users.json, operations.json, received mail or actual mailbox identifiers.

Create authorized-users.json locally with senderIds copied from the verified local Mili USER.md. Credentials JSON fields: region, mailbox, clientId, clientSecret, refreshToken, accountId. Do not store a login password. Scopes: ZohoMail.accounts.READ, ZohoMail.messages.ALL, ZohoMail.folders.READ. No organization/admin scopes.

Run `node setup.mjs`; visit http://localhost:18891. Create a Zoho Server-based Application using redirect http://localhost:18891/callback. Enter client details locally, select the matching data centre and authorize as the intended mailbox owner. Setup verifies the primary mailbox before saving. It sends no email. The installed local setup page is pinned to the intended mailbox; public backup replaces that address with an example address. Update that pin locally for deployment.

Plugin registration: add directory to plugins.load.paths, allow/enable mili-zohomail, and add the eight mili_mail_* names from index.js to Mili's tool allowlist. Refresh the persisted registry with `openclaw plugins registry --refresh`, then restart gateway after installation; OAuth completion later needs no restart. Setup UI binds loopback, checks Host/Origin/CSRF/state, expires pending authorization after ten minutes and never logs submitted secrets.

Tests: `node index.test.js` (mocked network only, no live delivery). Actual mailbox connection and provider compatibility need OAuth plus a read-only status check. Existing draft bodies and attachments are not implemented. No scheduler.

API references: [OAuth](https://www.zoho.com/mail/help/api/using-oauth-2.html), [Drafts](https://www.zoho.com/mail/help/api/post-save-draft-template.html), [Search](https://www.zoho.com/mail/help/api/get-search-emails.html), [Move](https://www.zoho.com/mail/help/api/move-email.html).
