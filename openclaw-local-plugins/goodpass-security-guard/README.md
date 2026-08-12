# Goodpass Security Guard

Deterministic OpenClaw plugin guard for Goodpass and related WhatsApp agents.

## Purpose

- Blocks prompt extraction, jailbreaks, secret/config/log requests, shell probes, and unrelated internal-system chat before model/tool use.
- Blocks dangerous operational tools for public-facing agents.
- Limits outbound message sends per inbound turn.
- Sanitizes outbound internal leakage patterns before delivery.
- Writes local audit state and logs under `.openclaw/security` and `.openclaw/logs/security`.

## Install

Copy this folder to the OpenClaw local plugin directory on the target host:

```bash
cp -r openclaw-local-plugins/goodpass-security-guard ~/.openclaw/local-plugins/
```

Add `goodpass-security-guard` to `plugins.allow`, enable it under `plugins.entries`, and add the local plugin path under `plugins.load.paths` in `~/.openclaw/openclaw.json`.

Configure private phone values only on the target host, not in Git:

```json
{
  "plugins": {
    "entries": {
      "goodpass-security-guard": {
        "enabled": true,
        "config": {
          "bossPhone": "+62...",
          "davinaEscalationPhone": "+62...",
          "blockHours": 24,
          "alertBoss": false
        }
      }
    }
  }
}
```

Optional hard-block sender list for WO AI:

```bash
export WO_AI_BLOCKED_SENDERS="+62..., +62..."
```

