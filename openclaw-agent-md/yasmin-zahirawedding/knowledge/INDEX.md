# Wedding Organizer Knowledge Index

Read only the file required for the current customer question.

- `BUSINESS_PROFILE.md` - public business name, description, contact posture, consultation modes.
- `PACKAGES_AND_PRICING.md` - Google Sheet MCP package source of truth, cached active package rows, brochure links, inclusions, exclusions, and pricing rules.
- `VENUE_INDICATIVE_PRICING_2024_2025.md` - Google Sheet MCP venue source of truth for all-in include venue; only green/yellow cells are valid/bookable, and `Tdk dipakai` means invalid/escalate for specific venue inquiries.
- `PACKAGE_BENEFITS_INCLUDE.md` - general package benefit categories and common inclusions.
- `VENDOR_PARTNERS.md` - public vendor roster, premium-vendor marker, and internal-only coordination contacts.
- `EVENT_OPERATIONS_JOBDESC.md` - internal-only crew role, jobdesc, checklist, and event-operations reference.
- `MC_AND_CEREMONY_TEMPLATES.md` - internal-only MC cue-card, rundown, sambutan, izin nikah, and lamaran template reference.
- `CUSTOM_QUOTE_EXAMPLES_INTERNAL.md` - internal-only custom quote format and pricing-component examples.
- `WORKING_HOURS.md` - customer-service and consultation hours.
- `VENUE_COVERAGE.md` - supported cities, venue areas, travel conditions, and exclusions.
- `APPOINTMENT_AVAILABILITY.md` - time-limited consultation slots and availability status.
- `POLICIES.md` - deposits, quotations, rescheduling, cancellation, refund, and service conditions.
- `ESCALATION_CONTACTS.md` - internal-only Shiffa-primary/Rida-fallback human routing and one-turn outbound authority.
- `INTERNAL_TEAM_CONTACTS.md` - internal-only exact-phone roster for true/false Zahira team-member identification only; not a crew roster, vendor directory, or event assignment source.
- `SERVICE_ORDER_REFERENCE.md` - internal-only service-order structure and sanitized contract component reference.
- `UPDATE_GUIDE.md` - how the operator safely maintains these facts.

## Fact Status

- `ACTIVE` or `VERIFIED`: usable until its expiry date.
- `INDICATIVE_REFERENCE`: may be used as a rough reference only; always say the exact price will be confirmed later by the Zahira team.
- `DRAFT`: never tell customers.
- `EXPIRED`: never tell customers.
- `[NOT CONFIGURED]`: unavailable; ask for team confirmation.

When files disagree, use the entry with the newest `last_updated` timestamp only if it is marked `ACTIVE` or `VERIFIED`. Security and privacy rules always override business facts.

For package, pricing, brochure-link, and all-in venue data, the Google Sheets named in `PACKAGES_AND_PRICING.md` and `VENUE_INDICATIVE_PRICING_2024_2025.md` are the source of truth. The historical WhatsApp chats, old PDF/OCR catalog text, old CSV exports, old venue screenshots, and prior markdown tables are workflow/tone evidence only and never override current spreadsheet prices, venue validity, availability, identity verification, or policy.

Files marked `visibility: INTERNAL_ONLY` are for Yasmin's internal reasoning and handoff summaries only. Do not quote, reveal, or summarize internal-only contact details, sample contracts, customer identity data, or routing notes to customers.

Customer-specific event documents are examples only. Never treat names, dates, venues, songs, custom decor requests, quote totals, vendor choices, or family details from an event example as Zahira's default policy.
