# OpenClaw VPS Migration Manifest

Generated for MiniPC to VPS migration on 2026-09-02.

## Goal

Move OpenClaw agents, Goodpass backend helpers, Moura/Mouru automation, Mourgirls social, Drinkmouru/YapperAI social, and Bray Ajaaa social support to a VPS without re-linking accounts unless provider sessions reject host migration.

## Source Of Truth

- Public/redacted backup repo: `/home/olekamole/codexskill`
- Private runtime source: `/home/olekamole/.openclaw`
- Service units: `/home/olekamole/.config/systemd/user`
- Goodpass API: `/home/olekamole/goodpass-read-api`
- Goodpass callback static server: `/home/olekamole/goodpass-auth-callback`
- Instagram workers: `/home/olekamole/instagram-autoreply`, `/home/olekamole/instagram-mourgirls-autoreply`, `/home/olekamole/instagram-bray-ajaaa`
- YapperAI social router: `/home/olekamole/YapperAI`
- Moura helpers: `/home/olekamole/scripts/moura_*.py`
- Public tunnel unit/token: `/home/olekamole/.config/systemd/user/cloudflared-n8n.service`, `/home/olekamole/.config/cloudflared-n8n/token.env`

## Agents To Migrate

| Agent | Workspace | Runtime State | Primary Channel |
| --- | --- | --- | --- |
| `goodpass-admin` | `.openclaw/workspace-goodpass-admin` | `.openclaw/memory/goodpass-admin.sqlite*` | WhatsApp default account |
| `moura-alexandra` | `.openclaw/workspace-moura-alexandra` | `.openclaw/memory/moura-alexandra.sqlite*`, `.openclaw/moura-*` | WhatsApp `moura-alexandra` account |
| `mourgirls-social` | `.openclaw/workspace-mourgirls-social` | OpenClaw agent DB under `.openclaw/agents/mourgirls-social` | Instagram worker |
| `instagram-social` | `.openclaw/workspace-instagram-social` | OpenClaw agent DB under `.openclaw/agents/instagram-social` | Instagram worker |
| `bray-ajaaa` | `.openclaw/workspace-bray-ajaaa` | OpenClaw agent DB under `.openclaw/agents/bray-ajaaa` | Instagram/YapperAI/OpenClaw |
| `davina-helowedding` | `.openclaw/workspace-davina-helowedding` | OpenClaw agent DB under `.openclaw/agents/davina-helowedding` | WhatsApp/OpenClaw |
| `yasmin-zahirawedding` | `.openclaw/workspace-yasmin-zahirawedding` | OpenClaw agent DB under `.openclaw/agents/yasmin-zahirawedding` | WhatsApp/OpenClaw |
| `wo-ai-sales` | `.openclaw/workspace-wo-ai-sales` | OpenClaw agent DB under `.openclaw/agents/wo-ai-sales` | WhatsApp/OpenClaw |
| `main` | `.openclaw/workspace` | OpenClaw agent DB under `.openclaw/agents/main` | OpenClaw default workspace |

## Agent Instruction Files In Private Archive

The current full private archive `openclaw-vps-runtime-20260902-203607.tar.gz` includes live runtime instruction files for:

- `.openclaw/workspace-goodpass-admin/`
- `.openclaw/workspace-moura-alexandra/`
- `.openclaw/workspace-mourgirls-social/`
- `.openclaw/workspace-instagram-social/`
- `.openclaw/workspace-bray-ajaaa/`
- `.openclaw/workspace-davina-helowedding/`
- `.openclaw/workspace-yasmin-zahirawedding/`
- `.openclaw/workspace-wo-ai-sales/`
- `.openclaw/workspace/`
- `.openclaw/workspace-attestations/`
- `YapperAI/personas/social-replies/`

Core files present across these workspaces include:

- `AGENTS.md`
- `USER.md`
- `IDENTITY.md`
- `TOOLS.md`
- `HEARTBEAT.md`
- `SOUL.md`
- `MEMORY.md`
- `SECURITY.md`
- `CUSTOMER_SERVICE.md`
- `MARKETING.md`
- `PRODUCT_KNOWLEDGE.md`
- `PRODUCT_CATALOG.md`

Restore from the private archive first. Use the redacted public backup repo `/home/olekamole/codexskill/openclaw-agent-md/` only as a review/recovery copy, not as the primary runtime restore source.

## OpenClaw Config And Credentials

Must copy as private runtime data:

- `.openclaw/openclaw.json`
- `.openclaw/secrets.env`
- `.openclaw/gdrive-credentials.json`
- `.openclaw/gdrive-token.json` if present
- `.openclaw/credentials/`
- `.openclaw/local-plugins/`
- `.openclaw/agents/`
- `.openclaw/memory/`
- `.openclaw/mcp-servers/`
- root OpenClaw SOP docs: `AGENTS.md`, `OPENCLAW_AGENT_DRY_RUN_SOP.md`, `OPENCLAW_QR_LOGIN_SOP.md`

Current top-level OpenClaw secret keys:

- `DEEPSEEK_API_KEY`
- `GEMINI_API_KEY`
- `GEMINI_CLI_TRUST_WORKSPACE`
- `GOG_KEYRING_PASSWORD`
- `GOODPASS_PUBLIC_SEARCH_ANON_KEY`
- `GOODPASS_PUBLIC_SEARCH_ENDPOINT`
- `GOODPASS_READ_API_URL`
- `GOOGLE_API_KEY`
- `GOOGLE_PLACES_API_KEY`
- `WHATSAPP_PAID_SEARCH_SECRET`

## Goodpass API Required Env

File: `/home/olekamole/goodpass-read-api/secrets.env`

- `APP_BASE_URL`
- `KYC_SUBMIT_FUNCTION_NAME`
- `LOG_LEVEL`
- `NOTIFICATION_OUTBOX_FUNCTION_NAME`
- `ONBOARDING_TOKEN_TTL_SECONDS`
- `SUPABASE_AUTH_LIST_MAX_PAGES`
- `SUPABASE_AUTH_LIST_PAGE_SIZE`
- `SUPABASE_SECRET_KEY`
- `SUPABASE_URL`
- `WACLI_STORE`
- `WA_NOTIFICATION_WORKER_BATCH_LIMIT`
- `WA_NOTIFICATION_WORKER_DRY_RUN`
- `WA_NOTIFICATION_WORKER_ENABLED`
- `WA_NOTIFICATION_WORKER_MIN_SEND_INTERVAL_SECONDS`
- `WA_NOTIFICATION_WORKER_POLL_SECONDS`
- `WA_VERIFICATION_REPLY_INITIAL_LOOKBACK_MINUTES`
- `WA_VERIFICATION_REPLY_SCAN_LIMIT`
- `WA_VERIFICATION_REPLY_WORKER_ENABLED`
- `WA_VERIFICATION_REPLY_WORKER_POLL_SECONDS`
- `WHATSAPP_NOTIFICATION_WORKER_SECRET`
- `WHATSAPP_PAID_SEARCH_SECRET`

Goodpass local state to preserve:

- `goodpass-read-api/goodpass-db-local/*.sqlite`
- `goodpass-read-api/goodpass-db-local/*_uploads/`
- `goodpass-read-api/goodpass-db-local/wa_verification_reply_worker_state.json`

Goodpass API endpoints on source:

- `GET /health`
- `POST /whatsapp-auth`
- `POST /auth/activate`
- `POST /user-status`
- `POST /select-onboarding-type`
- `POST /company-onboarding/start`
- `POST /generate-onboarding-link`
- `POST /onboarding/verify`
- `POST /kyc-draft/upsert`
- `POST /kyc-draft/status`
- `POST /kyc-draft/submit`
- `POST /paid-search/submit`
- `POST /report-draft/upsert`
- `POST /report-draft/status`
- `POST /report-draft/submit`
- `POST /report-verification/reply`
- `POST /report-verification/status`
- `POST /report-verification/finalize`
- `POST /active-report/repayment/upsert`
- `POST /active-report/repayment/status`
- `POST /active-report/repayment/submit`
- `POST /active-report/restructure/upsert`
- `POST /active-report/restructure/status`
- `POST /active-report/restructure/submit`
- `POST /active-report/add-info/upsert`
- `POST /active-report/add-info/status`
- `POST /active-report/add-info/submit`
- `POST /active-report/repayment-status`
- `POST /active-report/installment-schedule`

## Instagram / Social Required Env

Files:

- `/home/olekamole/instagram-autoreply/.env`
- `/home/olekamole/instagram-mourgirls-autoreply/.env`
- `/home/olekamole/instagram-bray-ajaaa/.env`

Common required keys:

- `IG_API_MODE`
- `IG_AUTOREPLY_HOST`
- `IG_AUTOREPLY_PORT`
- `IG_DRY_RUN`
- `IG_PRIVATE_REPLY_AFTER_COMMENT`
- `IG_REPLY_MODE`
- `IG_VERIFY_TOKEN`
- `IG_WEBHOOK_PATH`
- `META_APP_SECRET`
- `META_PAGE_ACCESS_TOKEN`
- `META_PAGE_ID`
- `OPENCLAW_AGENT`
- `OPENCLAW_BIN`
- `OPENCLAW_ENABLED`
- `OPENCLAW_TIMEOUT`

Additional keys present for Bray/Mourgirls:

- `IG_ACCOUNT_ID`
- `IG_OWN_USERNAME`
- `IG_USER_ACCESS_TOKEN`

Additional keys present for Mourgirls:

- `IG_BACKFILL_COMMENTS_LIMIT`
- `IG_BACKFILL_ENABLED`
- `IG_BACKFILL_INTERVAL_SECONDS`
- `IG_BACKFILL_LOOKBACK_HOURS`
- `IG_BACKFILL_MAX_PAGES`
- `IG_BACKFILL_MEDIA_LIMIT`
- `IG_BACKFILL_ON_STARTUP`
- `IG_BACKFILL_STARTUP_RETRY_ATTEMPTS`
- `IG_BACKFILL_STARTUP_RETRY_SECONDS`
- `IG_PRIVATE_REPLY_API_VERSION`
- `IG_PRIVATE_REPLY_GRAPH_HOST`
- `IG_THREAD_CONTEXT_COMMENT_LIMIT`
- `IG_THREAD_CONTEXT_ENABLED`
- `IG_THREAD_CONTEXT_MAX_CHARS`
- `IG_THREAD_CONTEXT_REPLY_LIMIT`

YapperAI state/config to preserve:

- `YapperAI/config/accounts.live.toml`
- `YapperAI/config/accounts.toml`
- `YapperAI/config/rules/`
- `YapperAI/var/*.sqlite3*`
- `YapperAI/personas/social-replies/`

## Systemd Units To Restore

Core:

- `cloudflared-n8n.service`
- `openclaw-gateway.service`
- `openclaw-health-guard.service`
- `openclaw-health-guard.timer`
- `openclaw-skill-audit.service`
- `openclaw-skill-audit.timer`
- `openclaw-skill-audit.path`
- `openclaw-skill-audit-enforcer.service`
- `openclaw-skill-audit-enforcer.timer`
- `openclaw-gdrive-refresh.service`
- `openclaw-gdrive-refresh.timer`

Goodpass:

- `goodpass-read-api.service`
- `goodpass-auth-callback.service`
- `goodpass-wa-notification-worker.service`
- `goodpass-wa-verification-reply-worker.service`
- `goodpass-user-md-guard.service`
- `goodpass-user-md-guard.timer`
- `goodpass-user-md-guard.path`

Moura:

- `moura-reminders.service`
- `moura-reminders.timer`
- `moura-reengagement.service`
- `moura-reengagement.timer`
- `moura-eval-checkpoint.service`
- `moura-eval-checkpoint.timer`

Social:

- `instagram-autoreply.service`
- `instagram-mourgirls-autoreply.service`
- `yapperai-live.service`
- `yapperai-shadow.service`
- `yapperai-shadow-replay.service`

## VPS Base Packages

Install before restore:

```bash
sudo apt update
sudo apt install -y git curl rsync tar nodejs npm python3 python3-venv python3-pip sqlite3 jq ripgrep ufw fail2ban cloudflared
```

OpenClaw itself currently runs from:

```text
/home/olekamole/.npm-global/lib/node_modules/openclaw/dist/index.js
```

Install matching OpenClaw on VPS, or copy `.npm-global` only if package install is not possible.

## Important Migration Constraints

- Do not push private runtime archive to GitHub.
- Do not print `secrets.env`, `creds.json`, provider tokens, or Supabase service role key in chat.
- Stop source services before final archive if doing a live cutover, so SQLite WAL files and WhatsApp sessions are consistent.
- Run only one host as production owner at a time. Running MiniPC and VPS simultaneously can double-send WhatsApp/Instagram replies.
- WhatsApp sessions may still invalidate when moved to new host/IP. Copying credentials avoids normal setup, but provider-side linked-device checks can force QR relink.
- Meta Instagram webhooks must be switched to VPS public HTTPS URLs after VPS is live.
- If Cloudflare Tunnel is reused, migrate `.config/cloudflared-n8n/token.env` and enable `cloudflared-n8n.service` on VPS.
- `GOODPASS_READ_API_URL` currently points to local Goodpass API; update only if path/port/domain changes on VPS.
