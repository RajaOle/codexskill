---
name: security
description: Security skill for secret scanning, dependency vulnerability checks, permission audits, API key handling, SSH hardening, TLS setup, firewall configuration, and threat-model reviews. Trigger for any security audit, hardening request, credential management, or when reviewing code that handles passwords, keys, or user data.
---

# Security

## ⚠️ Secrets in This Codebase

Current known credentials in scripts (to be moved to env vars):
```python
NVR_IP   = "192.168.1.168"
NVR_USER = "admin"
NVR_PASS = "REPLACE_WITH_ENV_VAR"   # ← hardcoded, should be env var
```

**These are in local scripts only. Never commit to a public repo.**

---

## Secret Management

### Move credentials to `.env`
```bash
# .env file (never commit this)
NVR_IP=192.168.1.168
NVR_USER=admin
NVR_PASS=
CAMERA_IP=192.168.1.249
```

```python
# Load in Python
import os
from dotenv import load_dotenv
load_dotenv()

NVR_IP   = os.environ["NVR_IP"]
NVR_USER = os.environ["NVR_USER"]
NVR_PASS = os.environ["NVR_PASS"]
```

```bash
# Install dotenv
pip install python-dotenv --break-system-packages
# or in venv: pip install python-dotenv

# Add to .gitignore
echo ".env" >> .gitignore
echo "*.env" >> .gitignore
```

### Secret scanning
```bash
# Scan for secrets before commit
pip install detect-secrets
detect-secrets scan > .secrets.baseline
detect-secrets audit .secrets.baseline

# Or use trufflehog (more thorough)
docker run --rm trufflesecurity/trufflehog filesystem /home/olekamole/yolo-vision
```

---

## File Permissions

```bash
# Check permissions on sensitive files
ls -la ~/.ssh/
ls -la ~/.env 2>/dev/null || echo "no .env found"
ls -la /home/olekamole/yolo-vision/*.py

# Fix permissions
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh/
chmod 600 .env

# Find world-writable files (security risk)
find /home/olekamole -perm -o+w -type f 2>/dev/null

# Find setuid binaries
find / -perm /4000 -type f 2>/dev/null | head -20
```

---

## Firewall (UFW)

```bash
# Status
ufw status verbose

# Basic hardening rules
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow from 192.168.1.0/24 to any port 5000   # Frigate — LAN only
ufw allow from 192.168.1.0/24 to any port 8554   # RTSP — LAN only
ufw enable

# Block a specific IP
ufw deny from <suspicious_ip>

# Check what's listening
ss -tulpn | grep LISTEN
```

---

## SSH Hardening

```bash
# /etc/ssh/sshd_config — recommended settings
PermitRootLogin no
PasswordAuthentication no
ChallengeResponseAuthentication no
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys
AllowUsers olekamole
MaxAuthTries 3
LoginGraceTime 20
X11Forwarding no
ClientAliveInterval 300
ClientAliveCountMax 2

# Restart after changes
systemctl restart sshd
```

---

## Dependency Vulnerability Checks

```bash
# Check Python packages for known CVEs
pip install pip-audit --break-system-packages
pip-audit

# Or using safety
pip install safety --break-system-packages
safety check

# Update vulnerable packages
pip install --upgrade <package>

# List installed versions
pip freeze > requirements.txt
```

---

## API Key Handling

```python
# ✅ Correct: always read from env
import os
API_KEY = os.environ.get("MY_API_KEY")
if not API_KEY:
    raise EnvironmentError("MY_API_KEY not set")

# ❌ Never hardcode
API_KEY = "sk-abc123..."
```

---

## TLS / HTTPS (for API services)

```bash
# Self-signed cert (dev only)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout server.key -out server.crt

# Let's Encrypt (production, if domain available)
apt install certbot
certbot certonly --standalone -d yourdomain.com

# Nginx reverse proxy with TLS
# proxy_pass to FastAPI/Frigate on localhost
```

---

## Audit Log Checklist

Before deploying any new script that handles auth or network:

- [ ] No credentials hardcoded in source
- [ ] `.env` excluded from git
- [ ] File permissions: configs 600, scripts 700
- [ ] Firewall allows only LAN access to NVR/camera ports
- [ ] SSH: password auth disabled, pubkey only
- [ ] `pip-audit` or `safety check` run on requirements
- [ ] No open ports to WAN except SSH (and only if needed)
- [ ] Logs don't contain passwords or tokens

---

## Threat Model — Home NVR Setup

| Asset | Threat | Mitigation |
|-------|--------|-----------|
| NVR credentials | Leaked via script commit | Move to `.env`, never push |
| Camera feed | LAN interception | Keep on isolated VLAN if possible |
| Frigate web UI | Unauthorized access | Firewall to LAN only (`192.168.1.0/24`) |
| SSH access | Brute force | `fail2ban` + pubkey only |
| Face image crops | Privacy | Store locally only, encrypt if cloud sync |

```bash
# Install fail2ban (SSH brute force protection)
apt install fail2ban -y
systemctl enable fail2ban
systemctl start fail2ban
fail2ban-client status sshd
```

---

## SOP-OPS-04 — Verifying and Installing OpenClaw Skills from ClawHub

Target audience: System Administrator (`olekamole`)

Objective: Establish a strict technical verification process to prevent malicious payloads, unauthorized credential harvesting, or compromised helper binaries from infecting the OpenClaw agent framework during custom skill installations.

### Pre-Installation Verification Workflow

1. Verify the VirusTotal badge.
   - Dashboard inspection: before downloading or cloning any skill repository, open the ClawHub dashboard and locate the target skill.
   - Look for the automated VirusTotal scan certificate.
   - Rule: never install or run a skill that lacks a clean, updated scan certificate or displays a failed security flag.

2. Inspect for rogue binaries and prompts.
   - Dependency check: review the skill documentation, installation scripts, and initialization prompts.
   - Run the preinstalled static scanner before any install attempt: `/home/olekamole/scripts/openclaw-skill-audit.sh /path/to/extracted/skill/directory`.
   - Be highly suspicious of any custom skill that asks to install external helper binaries or utilities, including `openclaw-core` lookalikes or `AuthTool`.
   - Red flags: prompts requesting the download of separate installer packages, executable binaries, or password-protected `.zip` files.
   - Legitimate OpenClaw skills should rely on standard Python dependencies or native OpenClaw bindings.

3. Enable interception wrappers.
   - Framework-level shielding: before executing the skill within the active runtime environment, ensure network and runtime interception tools are active.
   - Initialize security wrappers such as `ClawNet` or `openclaw-shield` when available.
   - These tools operate at the framework level to intercept incoming skill calls, forcing the LLM model to analyze script code for hidden payloads or obfuscated commands before execution.

4. Execute post-install sandboxing.
   - Isolate and test: install the skill into an isolated Python environment.
   - Run a localized test loop to confirm the skill only accesses the specific APIs, devices, or folders it explicitly requires for accounting, tracking, or automation functions.

### Security Verification Checklist

| Verification Step | Target Indicator | Action if Failed |
|-------------------|------------------|------------------|
| Payload Integrity | VirusTotal clean stamp | Abort installation immediately |
| Static Skill Audit | `/home/olekamole/scripts/openclaw-skill-audit.sh` passes with no critical alerts | Abort installation on critical alerts; manually review warnings |
| Dependency Check | No external `.zip` or unverified `.exe` / `.bin` tools requested | Reject skill and isolate the repo |
| Runtime Control | `openclaw-shield` active and intercepting scripts | Halt framework until shield is active |

### Operational Enforcement

- The scanner is installed at `/home/olekamole/scripts/openclaw-skill-audit.sh`.
- The aggregate guard is installed at `/home/olekamole/scripts/openclaw-skill-audit-all.sh`.
- The user systemd timer `openclaw-skill-audit.timer` runs the audit every 15 minutes and after boot.
- The user systemd path unit `openclaw-skill-audit.path` runs the audit when OpenClaw skill/plugin directories change.
- The user systemd timer `openclaw-skill-audit-enforcer.timer` checks every 10 minutes that the audit timer and path unit remain enabled and active.
- Logs are written under `/home/olekamole/.openclaw/logs/security/`.
- User lingering must remain enabled for boot persistence: `loginctl show-user olekamole -p Linger` should return `Linger=yes`.
