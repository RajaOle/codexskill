# Codex Skills

Snapshot of Codex skills from:

```text
/home/olekamole/.codex/skills
```

This repository includes both custom user skills and system skill definitions under `.system/`.

## Layout

- `*/SKILL.md` - skill instructions loaded by Codex when relevant.
- `.system/` - system-provided skills.
- `cloudflare-deploy/references/` - Cloudflare deployment reference material.
- `cloudflare-deploy/assets/` - assets used by the Cloudflare deployment skill.

## Sync Source

To refresh this repository from the local machine:

```bash
cp -a /home/olekamole/.codex/skills/. /home/olekamole/codexskill/
```
