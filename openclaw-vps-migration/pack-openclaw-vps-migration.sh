#!/usr/bin/env bash
set -euo pipefail

STAMP="$(date +%Y%m%d-%H%M%S)"
BASE="/home/olekamole"
OUT_DIR="$BASE/openclaw-vps-migration"
ARCHIVE="$OUT_DIR/openclaw-vps-runtime-$STAMP.tar.gz"
MANIFEST="$OUT_DIR/openclaw-vps-runtime-$STAMP.files.txt"

mkdir -p "$OUT_DIR"
cd "$BASE"

INCLUDE_FILE="$(mktemp)"
trap 'rm -f "$INCLUDE_FILE"' EXIT

cat > "$INCLUDE_FILE" <<'PATHS'
.openclaw/openclaw.json
.openclaw/secrets.env
.openclaw/gdrive-credentials.json
.openclaw/gdrive-token.json
.openclaw/credentials
.openclaw/mcp-servers
.openclaw/local-plugins
.openclaw/agents
.openclaw/memory
.openclaw/moura-allowed-refs
.openclaw/moura-campaign-claims
.openclaw/moura-contacts
.openclaw/moura-reengagement
.openclaw/moura-reminders
.openclaw/workspace
.openclaw/workspace-attestations
.openclaw/workspace-bray-ajaaa
.openclaw/workspace-davina-helowedding
.openclaw/workspace-goodpass-admin
.openclaw/workspace-instagram-social
.openclaw/workspace-moura-alexandra
.openclaw/workspace-mourgirls-social
.openclaw/workspace-wo-ai-sales
.openclaw/workspace-yasmin-zahirawedding
.config/systemd/user/openclaw-gateway.service
.config/systemd/user/cloudflared-n8n.service
.config/systemd/user/openclaw-health-guard.service
.config/systemd/user/openclaw-health-guard.timer
.config/systemd/user/openclaw-skill-audit.service
.config/systemd/user/openclaw-skill-audit.timer
.config/systemd/user/openclaw-skill-audit.path
.config/systemd/user/openclaw-skill-audit-enforcer.service
.config/systemd/user/openclaw-skill-audit-enforcer.timer
.config/systemd/user/openclaw-gdrive-refresh.service
.config/systemd/user/openclaw-gdrive-refresh.timer
.config/systemd/user/goodpass-read-api.service
.config/systemd/user/goodpass-auth-callback.service
.config/systemd/user/goodpass-wa-notification-worker.service
.config/systemd/user/goodpass-wa-verification-reply-worker.service
.config/systemd/user/goodpass-user-md-guard.service
.config/systemd/user/goodpass-user-md-guard.timer
.config/systemd/user/goodpass-user-md-guard.path
.config/systemd/user/moura-reminders.service
.config/systemd/user/moura-reminders.timer
.config/systemd/user/moura-reengagement.service
.config/systemd/user/moura-reengagement.timer
.config/systemd/user/moura-eval-checkpoint.service
.config/systemd/user/moura-eval-checkpoint.timer
.config/systemd/user/instagram-autoreply.service
.config/systemd/user/instagram-mourgirls-autoreply.service
.config/systemd/user/yapperai-live.service
.config/systemd/user/yapperai-shadow.service
.config/systemd/user/yapperai-shadow-replay.service
.config/openclaw-guards/goodpass-user-md
.config/cloudflared-n8n/token.env
goodpass-read-api
goodpass-auth-callback
instagram-autoreply
instagram-mourgirls-autoreply
instagram-bray-ajaaa
YapperAI
scripts/goodpass_whatsapp_qr_login.mjs
scripts/wacli_goodpass_qr_auth.mjs
scripts/moura_campaign_claims.py
scripts/moura_contacts.py
scripts/moura_eval_checkpoint.sh
scripts/moura_reengagement.py
scripts/moura_reminders.py
scripts/test_moura_reminders.py
scripts/openclaw-health-guard.js
scripts/openclaw_agent_dry_run.py
scripts/openclaw_agent_load_test.py
scripts/openclaw_qr_to_html.py
scripts/openclaw-skill-audit-all.sh
scripts/openclaw-skill-audit.sh
scripts/openclaw-skill-audit-ensure-enabled.sh
AGENTS.md
OPENCLAW_AGENT_DRY_RUN_SOP.md
OPENCLAW_QR_LOGIN_SOP.md
PATHS

while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  if [[ -e "$path" ]]; then
    printf '%s\n' "$path"
  fi
done < "$INCLUDE_FILE" > "$MANIFEST"

tar --create --gzip --file "$ARCHIVE" \
  --exclude='*/.git' \
  --exclude='*/node_modules' \
  --exclude='*/.venv' \
  --exclude='*/__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.log' \
  --exclude='.openclaw/agents/*/sessions' \
  --exclude='.openclaw/media/inbound' \
  --files-from "$MANIFEST" \
  --warning=no-file-changed

chmod 600 "$ARCHIVE" "$MANIFEST"

printf 'Archive: %s\n' "$ARCHIVE"
printf 'Manifest: %s\n' "$MANIFEST"
printf 'Size: '
du -h "$ARCHIVE" | awk '{print $1}'
printf 'Files/directories included: '
wc -l < "$MANIFEST"
