<p align="center">
  <img src="assets/logo.svg" alt="Pool Maintenance Tracker logo" width="120">
</p>

<h1 align="center">Pool Maintenance Tracker</h1>

<p align="center">
  A Home Assistant integration that tracks pool maintenance through a public,
  mobile-first web page — opened from a QR code or NFC tag in your pool's machine room.
  <br><br>
  <a href="https://github.com/lucasgiovanny/pool-maintenance-tracker/actions/workflows/ci.yml"><img src="https://github.com/lucasgiovanny/pool-maintenance-tracker/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/lucasgiovanny/pool-maintenance-tracker/actions/workflows/validate.yml"><img src="https://github.com/lucasgiovanny/pool-maintenance-tracker/actions/workflows/validate.yml/badge.svg" alt="Validate"></a>
  <a href="https://github.com/lucasgiovanny/pool-maintenance-tracker/releases"><img src="https://img.shields.io/github/v/release/lucasgiovanny/pool-maintenance-tracker?include_prereleases" alt="Release"></a>
  <img src="https://img.shields.io/badge/HACS-custom-41BDF5.svg" alt="HACS custom">
</p>

---

Whoever maintains the pool — you, family, or an external technician — scans a tag,
taps what they did (washed the filter, added salt, measured pH…), and hits save.
No Home Assistant login, no app. The integration turns those submissions into
native HA entities, keeps a persistent maintenance log, and reminds you when
periodic tasks are overdue.

## How it works

1. The integration serves a self-contained web page at a non-guessable URL
   (`/api/pool_maintenance_tracker/<token>/page`).
2. You write that URL to an NFC tag or print the QR code (both are provided as
   entities) and stick it in the machine room.
3. Anyone who opens the page picks who they are, taps the maintenance tiles,
   fills in readings, and submits — works fine on mobile data.
4. The integration validates the submission, updates the entities, fires an
   event for your automations, appends to the log, and sends notifications
   when something needs attention.

The page adapts to your pool: tiles and entities are created only for the
equipment you actually have.

## Installation

### HACS (recommended)

1. In HACS, open **⋮ → Custom repositories**.
2. Add `https://github.com/lucasgiovanny/pool-maintenance-tracker` with category **Integration**.
3. Search for **Pool Maintenance Tracker**, install it, and restart Home Assistant.

### Manual

Copy `custom_components/pool_maintenance_tracker` into your `config/custom_components`
folder and restart Home Assistant.

## Configuration

Go to **Settings → Devices & services → Add integration → Pool Maintenance Tracker**.

1. **Name and pool type** — salt water, manually dosed chlorine, or other.
   The type pre-selects the equipment modules.
2. **Equipment modules** — toggle what your pool actually has:

   | Module | Adds |
   |---|---|
   | Salt chlorinator | Chlorinator output/mode, salt readings, salt refills, cell-cleaning tracking |
   | pH doser acid tank | Acid tank level + refill tracking, low-level alert |
   | Filter | Filter wash tracking + reminder |
   | pH probe | Probe calibration tracking + reminder |
   | Cleaning tasks | Vacuum / waterline / basket logging |

   Water testing (pH, free chlorine) and the maintenance log are always on.
3. **Page and reminders** — page language (English/Portuguese), optional
   `notify.*` service for alerts, and reminder periods (defaults: filter 30 days,
   pH probe 60 days, chlorinator cell 90 days).

Everything can be changed later via **Configure** on the integration — including
disabling modules (their entities are removed) and regenerating the access token.

Multiple pools? Just add the integration again.

### People on the page

The "who is logging" chips are your active Home Assistant users plus a generic
**Technician** chip — no extra configuration needed. New HA users appear
automatically.

## QR code / NFC tag

After setup, the pool device provides two diagnostic entities:

- `image.<pool>_page_qr_code` — a QR code of the page URL. Open it, print it,
  or scan it straight from the dashboard.
- `sensor.<pool>_page_url` — the full URL, ready to copy into an NFC-writing app.

The URL contains a random 256-bit token. Anyone with the URL can log
maintenance (that's the point), but the endpoints are write-only, validated,
rate-limited, and can never control your equipment. If a tag is lost, regenerate
the token in the integration options and rewrite the tag.

> The page URL uses your external Home Assistant URL when configured
> (**Settings → System → Network**) so it works over mobile data.

## Entities

Created per pool (depending on enabled modules):

- **Numbers** (manually declared values): pH, free chlorine (ppm), salt (g/L),
  salt added (kg), chlorinator output (g/h)
- **Selects**: chlorinator mode (smart/manual/boost), acid tank level (full…¼)
- **Timestamps**: last water test, filter wash, cell cleaning, probe calibration,
  acid refill, cleaning, and last maintenance of any kind
- **Binary sensors**: filter wash due, cell cleaning due, probe calibration due
- **`sensor.<pool>_last_record`**: `who · date · what` summary, with the last
  20 records as attributes
- **`event.<pool>_maintenance_logged`**: fires on every submission

## Automations

Every accepted submission also fires a `pool_maintenance_tracker_record` event
on the bus:

```yaml
trigger:
  - platform: event
    event_type: pool_maintenance_tracker_record
action:
  - service: notify.mobile_app_me
    data:
      message: >
        {{ trigger.event.data.person }} logged:
        {{ trigger.event.data.categories | join(', ') }}
```

## Payload API

The page posts JSON to `/api/pool_maintenance_tracker/<token>/log`. You can use
the endpoint directly (e.g. from a shortcut):

```json
{
  "version": 2,
  "person": "Lucas",
  "logged_at": "2026-07-26T14:30:00+01:00",
  "categories": ["water_test", "filter_wash"],
  "readings": { "ph": 7.2, "free_chlorine": 1.2, "salt": 4.5 },
  "chlorinator": { "output": 5, "mode": "smart" },
  "salt": { "added_kg": 25 },
  "acid": { "level": "quarter" },
  "cleaning": { "types": ["vacuum", "waterline"] }
}
```

Rules: every field is optional; `null`/absent fields change nothing;
out-of-range values (pH 6–9, chlorine 0–10 ppm, salt 0–10 g/L, salt added
0–500 kg, output 0–10 g/h) are ignored and echoed back in the `ignored` list;
sections for disabled modules are ignored; a payload with nothing valid gets
`400`. Timestamps older than 7 days or more than 1 hour in the future are
replaced with server time.

## Security notes

- Endpoints accept only `GET` (page) and `POST` (log); they are write-only
  declarative state — nothing can command your equipment.
- Non-guessable 256-bit token in the path, compared in constant time.
- Rate limits: 10 posts/min per IP, 30 posts/5 min per token, and repeated
  invalid-token attempts get an IP timeout.
- The page is fully self-contained (no external fonts/scripts) and served with
  a strict Content-Security-Policy, `noindex`, and `no-store`.

## Development

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
.venv/bin/ruff check .
```

## License

[MIT](LICENSE)
