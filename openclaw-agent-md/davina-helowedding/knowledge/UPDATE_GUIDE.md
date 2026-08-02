# Knowledge Update Guide

These files are the operator-maintained source of truth for Davina.

## Safe Update Process

1. Edit only the relevant knowledge file.
2. Set `last_updated` to the current date.
3. Keep incomplete entries as `DRAFT`.
4. Change the document or entry to `ACTIVE` or `VERIFIED` only after the Wedding Organizer team approves it.
5. Add a `Valid until` date for prices, promotions, packages, and appointment slots.
6. Remove or mark outdated entries `EXPIRED`; do not silently leave old prices active.
7. Never put API keys, passwords, OTPs, payment credentials, government IDs, or customer chat transcripts in these files.
8. Keep internal contacts only in `ESCALATION_CONTACTS.md`.

## Recommended Review Frequency

- Appointment availability: whenever slots change.
- Packages and pricing: on every commercial update.
- Working hours: before holidays or schedule changes.
- Venue coverage: whenever travel or venue policy changes.
- Escalation contacts: immediately after staff or routing changes.
- Policies: only after authorized management approval.

After material updates, use a local embedded test to verify Davina answers from the new facts. Do not test by sending live WhatsApp messages.
