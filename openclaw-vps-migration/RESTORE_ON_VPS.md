# Restore OpenClaw Stack On VPS

Assumption: VPS user is also `olekamole` and home path is `/home/olekamole`. If different, update paths in systemd unit files and config before starting services.

## 1. Prepare VPS

```bash
sudo apt update
sudo apt install -y git curl rsync tar nodejs npm python3 python3-venv python3-pip sqlite3 jq ripgrep ufw fail2ban cloudflared
sudo loginctl enable-linger olekamole
mkdir -p /home/olekamole
```

Install pyenv/Python 3.11.9 if YapperAI/Instagram units will use the current hardcoded path:

```bash
curl https://pyenv.run | bash
pyenv install 3.11.9
```

Install OpenClaw so this path exists:

```text
/home/olekamole/.npm-global/lib/node_modules/openclaw/dist/index.js
```

## 2. Copy Private Archive

Use the encrypted archive for transfer/email after encrypting the current full archive:

```text
/home/olekamole/openclaw-vps-migration/openclaw-vps-runtime-20260902-203607.tar.gz.gpg
```

Do not transfer the unencrypted `.tar.gz` through email or chat. Keep the GPG password separate from the archive.

From MiniPC:

```bash
scp /home/olekamole/openclaw-vps-migration/openclaw-vps-runtime-20260902-203607.tar.gz.gpg olekamole@VPS_HOST:/home/olekamole/
```

On VPS:

```bash
cd /home/olekamole
gpg -d openclaw-vps-runtime-20260902-203607.tar.gz.gpg > openclaw-vps-runtime-20260902-203607.tar.gz
tar -xzf openclaw-vps-runtime-20260902-203607.tar.gz
chmod 700 /home/olekamole/.openclaw /home/olekamole/.openclaw/credentials /home/olekamole/.ssh 2>/dev/null || true
chmod 600 /home/olekamole/.openclaw/secrets.env /home/olekamole/goodpass-read-api/secrets.env 2>/dev/null || true
find /home/olekamole/.openclaw/credentials -type f -exec chmod 600 {} +
find /home/olekamole/.config/systemd/user -type f -name '*.service' -o -name '*.timer' -o -name '*.path'
```

## 3. Verify Agent Instruction Files

The private runtime archive contains the live OpenClaw agent workspaces and their runtime-loaded instruction files. These are the files OpenClaw agents need on the VPS:

```text
/home/olekamole/.openclaw/workspace-goodpass-admin/
/home/olekamole/.openclaw/workspace-moura-alexandra/
/home/olekamole/.openclaw/workspace-mourgirls-social/
/home/olekamole/.openclaw/workspace-instagram-social/
/home/olekamole/.openclaw/workspace-bray-ajaaa/
/home/olekamole/.openclaw/workspace-davina-helowedding/
/home/olekamole/.openclaw/workspace-yasmin-zahirawedding/
/home/olekamole/.openclaw/workspace-wo-ai-sales/
/home/olekamole/.openclaw/workspace-attestations/
/home/olekamole/YapperAI/personas/social-replies/
```

Verify core prompt files after extraction:

```bash
find /home/olekamole/.openclaw -path '*/workspace-*/*.md' -maxdepth 3 -type f | sort
find /home/olekamole/YapperAI/personas/social-replies -maxdepth 1 -type f -name '*.md' | sort
```

Expected important files include:

```text
AGENTS.md
USER.md
IDENTITY.md
TOOLS.md
HEARTBEAT.md
SOUL.md
MEMORY.md
SECURITY.md
CUSTOMER_SERVICE.md
MARKETING.md
PRODUCT_KNOWLEDGE.md
PRODUCT_CATALOG.md
```

Public/redacted copies are also backed up in GitHub through `/home/olekamole/codexskill` under `openclaw-agent-md/`. Those are useful for review and recovery, but the private runtime archive is the source to restore on the VPS because it includes live workspaces, state, credentials, memory, and non-public operational files.

## 4. Rebuild Python Environments

Goodpass API:

```bash
cd /home/olekamole/goodpass-read-api
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Instagram/YapperAI:

```bash
cd /home/olekamole/YapperAI
/home/olekamole/.pyenv/versions/3.11.9/bin/python -m unittest discover -s tests -v
/home/olekamole/.pyenv/versions/3.11.9/bin/python -m yapperai.service --config config/accounts.toml --check
```

## 5. Load Systemd Units

```bash
systemctl --user daemon-reload
systemctl --user enable openclaw-gateway.service cloudflared-n8n.service
systemctl --user enable goodpass-read-api.service goodpass-auth-callback.service
systemctl --user enable goodpass-wa-notification-worker.service goodpass-wa-verification-reply-worker.service
systemctl --user enable moura-reminders.timer moura-reengagement.timer moura-eval-checkpoint.timer
systemctl --user enable openclaw-health-guard.timer openclaw-skill-audit.timer openclaw-skill-audit.path openclaw-skill-audit-enforcer.timer
```

Start in this order:

```bash
systemctl --user start openclaw-gateway.service cloudflared-n8n.service
systemctl --user start goodpass-read-api.service goodpass-auth-callback.service
systemctl --user start goodpass-wa-notification-worker.service goodpass-wa-verification-reply-worker.service
systemctl --user start moura-reminders.timer moura-reengagement.timer moura-eval-checkpoint.timer
```

Start Instagram/YapperAI only after public webhook cutover is ready:

```bash
systemctl --user start instagram-autoreply.service
systemctl --user start instagram-mourgirls-autoreply.service
systemctl --user start yapperai-live.service
```

## 6. Health Checks

```bash
systemctl --user status openclaw-gateway.service --no-pager
systemctl --user status goodpass-read-api.service --no-pager
curl -s http://127.0.0.1:8081/health
curl -s http://127.0.0.1:8090/
journalctl --user -u openclaw-gateway.service -n 80 --no-pager
journalctl --user -u goodpass-read-api.service -n 80 --no-pager
```

OpenClaw:

```bash
/home/olekamole/.npm-global/bin/openclaw channels status
/home/olekamole/.npm-global/bin/openclaw gateway probe
```

Do not run live WhatsApp send tests unless exact owned test number is approved for that test.

## 7. Production Cutover

1. Stop source MiniPC production services.
2. Create final archive after services stop.
3. Copy final archive to VPS and restore.
4. Start VPS OpenClaw and Goodpass API.
5. Verify local health.
6. Update public reverse proxy/webhook DNS to VPS.
7. Start Instagram/YapperAI publishing services only after Meta webhook target points to VPS.
8. Monitor journal logs for 30 minutes.

Rollback: stop VPS social/WhatsApp services, restart MiniPC services, switch webhooks back.
