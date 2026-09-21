---
name: local-scraper-guardrails
description: Run an existing local scraper with bounded, checkpoint-aware execution and hard stops for CAPTCHA, rate limits, or other block signals. Use for scraping continuation, scraper audits, or local scraper jobs; do not use for generic web research.
---

# Local Scraper Guardrails

Use the repository's local scraper engine. Do not replace it with an LLM-based scraper, agent browser workflow, or ad hoc extraction script unless the user explicitly requests a redesign.

## Before Running

- Read applicable `AGENTS.md` files and the scraper README/config.
- Identify the real entrypoint, data directory, checkpoint/progress file, lock file, and existing run logs.
- Inspect current progress, record count, pending scope, and stale locks. Remove a lock only after confirming its recorded process is gone; report that cleanup.
- Preserve user changes and existing data. Never reset, truncate, or overwrite scraped records to make a run start clean.
- Prefer the smallest useful scope: one category, one region/tile, one browser session, concurrency `1`, and an explicit record/result cap.

## Execution

- Use the local engine's checkpoint/resume path. Keep deduplication enabled.
- Keep pacing and cooldowns enabled. Do not increase concurrency or remove delays to accelerate a run.
- Use dry-run first when behavior is uncertain. For a requested live run, state the cap and stop conditions before starting.
- Use only authorized network paths. Do not add free public proxies, CAPTCHA-solving, stealth plugins, fingerprint spoofing, or IP rotation intended to evade a block.
- If an authorized proxy is already part of the local design, keep one stable proxy per browser session and never log proxy credentials.

## Mandatory Stop Conditions

Stop the current run immediately on any of these:

- CAPTCHA, reCAPTCHA, `/sorry/`, unusual-traffic, or automated-query interstitial.
- HTTP `403`, `429`, repeated `5xx`, authentication challenge, or explicit rate-limit response.
- Repeated navigation failures, sudden empty-result responses, or other evidence that the source is rejecting traffic.
- Any unexpected data-loss, lock, or checkpoint error.

After stopping: preserve the checkpoint, close the browser, clean only the process-owned lock, and report the exact signal and last completed scope. Do not auto-retry, rotate IPs, or switch channels to bypass the stop. Resume only after a human decision and cooldown.

## After Running

Verify record count, progress/checkpoint state, completed scope, pause/error flags, and lock cleanup. Report remaining scope and whether a block signal occurred. Mention CPU, memory, or duration impact when material.

For code changes, use the coding workflow: read full files before editing, keep changes narrow, add focused tests, and validate without live source traffic where possible.
