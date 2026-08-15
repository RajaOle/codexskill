# Zahira Wedding - All In Include Venue Source of Truth

status: VERIFIED
last_updated: 2026-08-15
currency: IDR
visibility: PUBLIC

## Source of Truth

The active source for all-in package with venue is the Google Sheet below, accessed through the approved Google Drive MCP account only.

- Spreadsheet ID: `1TVL6VYS6bMkE1HJ0Yx5Qdj9mDKOqySIWWYHRKoOCxts`
- Spreadsheet URL: `https://docs.google.com/spreadsheets/d/1TVL6VYS6bMkE1HJ0Yx5Qdj9mDKOqySIWWYHRKoOCxts/edit?gid=1724208540#gid=1724208540`
- Active tab: `Sheet 1`
- Relevant columns: `Nama Venue`, `Area`, `Harga Sewa`, `Charge Lainnya`, `Nasi Box`, `Panggung`, `Pelaminan`, `% Catering`, `Total Harga`, and package totals for `100`, `200`, `300`, `400`, `500`, `600`, `700`, `800`, and `1000` pax.

This file cancels and replaces the old OCR/static venue price tables. Historical venue screenshots, old markdown tables, prior transcriptions, old image references, and historical WhatsApp chats are not venue-pricing authority.

## Validity Rule

Only spreadsheet cells colored green or yellow are valid/available for booking. All other color-coded venue cells are invalid and must not be quoted as available or bookable.

`Tdk dipakai` is an explicit invalid venue identifier. If a venue row or venue marker says `Tdk dipakai`, that venue must not be referenced as an option, quoted, recommended, or described as available even if another value in the row looks usable.

If a tool call returns only plain values and does not expose cell background color, do not infer availability from the row text, checklist column, dash, blank, asterisk, or price value. In that case, collect the customer's date, area, venue preference, and pax, then say Zahira team needs to confirm the valid venue options.

If date/area/pax/budget are already known, do not keep asking, explaining, or asking permission to escalate. Send the internal escalation in that same turn and give the customer one short handoff confirmation.

Green/yellow validity is cell-level. A venue row may have some pax cells valid and other pax cells invalid. Quote only the specific venue-and-pax cell that is green or yellow.

`N/A`, blank, invalid color, non-green/yellow color, `Tdk dipakai`, or unclear formatting means unavailable/not quotable for that capacity.

If a customer asks about a specific venue marked `Tdk dipakai`, do not say the venue is invalid because of an internal marker. Say the venue needs team confirmation, collect date/pax if missing, and follow the escalation route in `ESCALATION_CONTACTS.md`.

## Customer-Facing Rules

- Always confirm wedding date or month, area, venue preference, and estimated pax before discussing all-in venue pricing.
- Never describe a venue price as final quotation, booking hold, confirmed availability, or guaranteed booking.
- Exact venue availability, venue DP, rescheduling, cancellation, and sudden venue price changes follow the venue's current policy and Zahira team confirmation.
- If the customer asks for venue recommendations and valid color data is unavailable, ask for area and pax, then offer team confirmation.
- If the customer asks for venue prices, available venue references, or `PL` for all-in venue and valid color data is unavailable, route internally after the minimum facts are known. Do not quote GEEPI as a venue price, do not list venue names as available, and do not repeat "waiting for team" across turns.
- Approved customer reply after escalation: `Aku teruskan ke tim Zahira ya, Kak, supaya pilihan venue dan harganya nggak salah.`
- If the customer asks for a specific venue marked `Tdk dipakai`, route to the Zahira team through the approved escalation contact after collecting the minimum missing details.
- Do not mention spreadsheet IDs, tabs, color rules, MCP, source status, internal files, or tooling to customers.

## Package Scope

All-in include venue generally covers:

- gedung/venue
- dekorasi pelaminan and dekorasi catering
- catering
- makeup and busana
- photo and video
- MC akad and resepsi
- music
- wedding planner
- WO crew on the day

Use `PACKAGES_AND_PRICING.md` for the base all-in without venue/catering details. Use the venue spreadsheet only for venue-inclusive venue/pax totals after applying the green/yellow validity rule.

## Safe Reply Patterns

When color-valid data is available:

`Untuk {venue} area {area}, paket all-in venue {pax} pax di data kami mulai Rp{price}. Ini tetap perlu dicek lagi ke tim untuk tanggal {date} ya, Kak.`

When only plain value data is available or color validity cannot be checked:

`Untuk all-in dengan venue aku perlu cek valid venue yang available dulu ke tim Zahira ya, Kak. Area venue dan estimasi pax-nya berapa?`

When the requested specific venue is marked `Tdk dipakai`:

`Untuk venue itu aku perlu konfirmasi dulu ke tim Zahira ya, Kak. Boleh info tanggal acara dan estimasi pax-nya supaya tim bisa bantu cek opsi yang paling aman?`

When customer asks for all venue list:

`Boleh kak. Supaya nggak terlalu panjang, aku bantu filter dulu dari area dan pax yang kaka mau. Prefer area mana dan untuk berapa pax?`
