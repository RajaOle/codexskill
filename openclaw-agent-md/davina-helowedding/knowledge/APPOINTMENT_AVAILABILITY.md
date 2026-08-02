# Appointment Availability

status: VERIFIED
last_updated: 2026-07-23
timezone: Asia/Jakarta
visibility: PUBLIC

No dated appointment slot is currently published.

## Consultation Options

- Online consultation: WhatsApp / video call / Zoom by appointment.
- In-person consultation: Helo Wedding office or agreed client location by appointment.
- Default duration: 60 minutes when not otherwise specified.
- Consultant/team: Fifi (Wedding Consultant) / Tim Helo WO.
- Office location: Jl. Kalibaru Timur Dalam IV No. 28F, Bungur, Senen, Jakarta Pusat.
- Initial consultation note: Bebas biaya konsultasi awal unless the team states otherwise for a special arrangement.

## Slot Template

Copy one block per real slot:

### [YYYY-MM-DD HH:MM]

- Status: CONFIRMED_AVAILABLE
- Mode: online | in-person
- Duration: 60 minutes
- Consultant/team: Fifi (Wedding Consultant) / Tim Helo WO
- Location or meeting method: Online (WhatsApp / Zoom) / Office (Jl. Kalibaru Timur Dalam IV No. 28F, Bungur, Senen, Jakarta Pusat)
- Valid until: [YYYY-MM-DD]
- Notes: Bebas biaya konsultasi awal

Allowed status values:

- `CONFIRMED_AVAILABLE`
- `PROVISIONAL`
- `HELD`
- `BOOKED`
- `UNAVAILABLE`
- `EXPIRED`

Davina may offer only `CONFIRMED_AVAILABLE` slots that have not passed `Valid until`. Without a dated confirmed slot, Davina may collect preferred day/time and say the team will confirm availability.
