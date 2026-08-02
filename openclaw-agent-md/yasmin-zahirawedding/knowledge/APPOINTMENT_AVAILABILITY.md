# Appointment Availability

status: VERIFIED
last_updated: 2026-07-29
timezone: Asia/Jakarta
visibility: PUBLIC

No dated appointment slot is currently published.

## Consultation Options

- Online consultation: WhatsApp / video call / Zoom by appointment.
- In-person consultation: Zahira Wedding office or agreed client location by appointment.
- Default duration: 60 minutes when not otherwise specified.
- Consultant/team: Tim Wedding Consultant Zahira Wedding.
- Office location: Cluster Durian by Permata, Jl. Durian Barat II No. D2, Jagakarsa, Jakarta Selatan 12620.
- Initial consultation note: Bebas biaya konsultasi awal unless the team states otherwise for a special arrangement.

## Slot Template

Copy one block per real slot:

### [YYYY-MM-DD HH:MM]

- Status: CONFIRMED_AVAILABLE
- Mode: online | in-person
- Duration: 60 minutes
- Consultant/team: Tim Wedding Consultant Zahira Wedding
- Location or meeting method: Online (WhatsApp / Zoom) / Office (Cluster Durian by Permata, Jl. Durian Barat II No. D2, Jagakarsa, Jakarta Selatan 12620)
- Valid until: [YYYY-MM-DD]
- Notes: Bebas biaya konsultasi awal

Allowed status values:

- `CONFIRMED_AVAILABLE`
- `PROVISIONAL`
- `HELD`
- `BOOKED`
- `UNAVAILABLE`
- `EXPIRED`

Yasmin may offer only `CONFIRMED_AVAILABLE` slots that have not passed `Valid until`. Without a dated confirmed slot, Yasmin may collect preferred day/time and say the team will confirm availability.
