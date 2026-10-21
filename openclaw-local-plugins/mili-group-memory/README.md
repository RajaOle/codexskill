# Mili persistent group memory

Small local continuity layer, not a full transcript dump. Injects at most 6,000 UTF-8 bytes before a turn, including eight evidence-linked facts and six recent excerpts. Current group input and successful outgoing replies are saved automatically. Important notes use `mili_group_memory_remember`; missing historical details use `mili_group_memory_recall`. No extra model calls, embeddings or scheduled jobs. Recall reads only Mili's existing SQLite transcript index and joins the exact scoped group across historical session windows.

## Private setup

Create `~/.openclaw/mili-group-memory` with mode 0700. Its `scope.json` (0600) must contain agentId `mili`, channel `whatsapp`, accountId, groupId, sessionKey `agent:mili:whatsapp:group:<groupId>` and senderIds copied from verified local user identities. Do not publish this file. `state.json` (0600) holds private group notes and recent excerpts; do not publish it or seed it with another conversation's content. The default history database is Mili's own agent database. The factory accepts isolated root/database paths for tests only.

Load/allow/enable the `mili-group-memory` plugin and allow its two tools only for Mili. Refresh the plugin registry and restart the gateway. Never change group routing, session reset policy or global memory sharing to enable this feature. Add GROUP_MEMORY.md to Mili's task references. Keep AGENTS.md below 20,000 bytes.

## Boundaries and persistence

Runtime loading requires exact agent, session key, channel, account and verified sender. Wrong groups, DMs, other agents and background/local sessions receive nothing. Tool identity comes from runtime metadata, not arguments. Evidence for note updates must belong to the same group's stored history or a captured authorized current inbound message. Older evidence cannot overwrite a newer correction. Only user/assistant transcript text is returned; tool payloads, reasoning and other sessions are excluded.

Writes serialize in-process, write a private temporary file, fsync, rename atomically and fsync the directory. Each incoming/outgoing update commits immediately, so a gateway stop need not trigger a memory flush. Invalid snapshots are preserved for operator repair instead of silently replaced. Notes are historical data, not fresh approvals or instructions. Runtime state and group identifiers stay private; public backups contain code, tests, empty setup guidance and prompts only.

Run `node index.test.js` under Node 22+ with node:sqlite. Tests use synthetic isolated SQLite fixtures and include a fresh process reading the saved snapshot, cross-group isolation, evidence checks, bounded prompts and corruption preservation. Do not send WhatsApp test messages.
