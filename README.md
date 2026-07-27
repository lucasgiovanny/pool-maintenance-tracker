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
3. Anyone who opens the page picks who they are, optionally adjusts the date
   (defaults to today), taps the maintenance tiles, fills in readings, and
   submits — works fine on mobile data.
4. The integration validates the submission, updates the entities, fires an
   event for your automations, appends to the log, and sends notifications
   when something needs attention.
5. A **Report** tab on the same page (optional, on by default) gives whoever
   maintains the pool — even without HA access — an overview: current values,
   periodic task status with overdue badges, extra equipment entities you
   choose (e.g. your heat pump), a shared **notes diary**, and the recent
   maintenance history. Toggle it under **Configure → Page and notifications**.

### Notes

Notes are a page-only diary — they never become HA entities. Add one on the
log form (optional field, back-dated with the record; a note without any tile
selected is also accepted). The report tab shows the diary read-only, keeping
the latest 50, append-only.

### Equipment on the report

Under **Configure → Linked sensors → Extra entities on the report tab**, pick
any entities from other integrations (heat pump switch, power sensor, …). The
report shows their current state formatted automatically — measurements with
units, on/off with "since when", and `schedule` helpers with *turns on/off at
…* plus their real weekly grid (read from HA's storage for UI-created
schedules; schedules are configuration, so they are kept out of the history
charts).

### Wall dashboard (kiosk)

Got a small screen next to the pool? The integration also serves a **dark,
display-only dashboard** designed for a 7-inch landscape screen (and up):

- water readings (probe values when linked, your manual readings otherwise),
- equipment states, including your extra entities,
- periodic tasks and overdue alerts,
- a big **countdown to the next schedule change** ("turns on in 03:41:04"),
  shown only when a `schedule` entity is among your extra entities.

It has no touch targets and no navigation — just point a browser at it in
kiosk mode. It refreshes itself every 30 seconds. Find its URL in the
`kiosk_url` attribute of the QR code entity; turn it off under
**Configure → Page and notifications**.

### History tab

A third tab charts the pool over time (7 days / 30 days / 6 months):

- **Water readings** — daily averages from the linked probes (HA long-term
  statistics) as a line, with your manual readings overlaid as dots.
- **Equipment** — daily averages for numeric extra entities, and *hours on per
  day* bars for on/off entities (computed from the HA recorder history, so
  limited by your recorder retention — 10 days by default).

Charts are lightweight inline SVG — no external libraries, still one
self-contained page.

The page adapts to your pool: tiles and entities are created only for the
equipment you actually have.

<p align="center">
  <img src="assets/page-screenshot.png" alt="The maintenance page (Portuguese, salt pool with a linked temperature probe)" width="560">
</p>

## Installation

### HACS (recommended)

1. In HACS, open **⋮ → Custom repositories**.
2. Add `https://github.com/lucasgiovanny/pool-maintenance-tracker` with category **Integration**.
3. Search for **Pool Maintenance Tracker**, install it, and restart Home Assistant.

### Manual

Copy `custom_components/pool_maintenance_tracker` into your `config/custom_components`
folder and restart Home Assistant.

> The integration ships its own brand icon (shown in the integrations list on
> Home Assistant 2026.3 or newer).

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
3. **Page and reminders** — page language (English, Portuguese, Spanish,
   French, German, Italian), optional `notify.*` service for alerts, and
   reminder periods (defaults: filter 30 days, pH probe 60 days, chlorinator
   cell 90 days).

   Notifications are entirely optional: leave the service empty and the
   integration sends nothing — the "due" binary sensors and the maintenance
   event remain available to drive your own automations instead.

Everything can be changed later via **Configure** on the integration — including
disabling modules (their entities are removed) and regenerating the access token.

Multiple pools? Just add the integration again.

### People on the page

The "who is logging" chips are your active Home Assistant users plus a generic
**Technician** chip — no configuration needed, and new HA users appear
automatically. To show only some users, pick them under **Configure → People
on the page**.

### Linked sensors (smart probes)

Already have automatic measurements — a Blue Connect probe, a Fluidra/other
pool integration? Link those entities under **Configure → Linked sensors**
(pH, free chlorine, salt, water temperature). Then:

- the maintenance page shows the live probe values right next to the manual
  readings, so whoever is testing can compare on the spot;
- every record stores a snapshot of the probe values at log time — a handy
  audit trail of manual reading vs. probe (e.g. to spot calibration drift).

You also choose how linked sensors interact with the manual entities
(**Linked sensor behavior**):

- **Show on page only** (default) — entities stay purely manual; the probe's
  own entity remains your live value.
- **Fill on record** — when a record is saved without a manual reading for a
  value, the probe's current value fills the entity. Manual readings always win.
- **Mirror** — entities continuously follow the linked sensors (manual values
  get overwritten on the next probe update).

## QR code / NFC tag

After setup, the pool device provides:

- `image.<pool>_page_qr_code` — a QR code of the page URL. Open it, print it,
  or scan it straight from the dashboard. Its `url` attribute holds the full
  URL, ready to copy into an NFC-writing app.
- A **Visit** link on the device page that opens the maintenance page directly.

There is also a **printable machine-room manual**: the link at the bottom of
the logging page opens a print-ready sheet (A4) with the QR code, a marked
space to stick your NFC tag, and step-by-step instructions for technicians —
print it (or save as PDF) straight from the browser.

The URL contains a random 256-bit token. Anyone with the URL can log
maintenance (that's the point), but the endpoints are write-only, validated,
rate-limited, and can never control your equipment. If a tag is lost, regenerate
the token in the integration options and rewrite the tag.

> The page URL uses your external Home Assistant URL when configured
> (**Settings → System → Network**) so it works over mobile data.

## Entities

Created per pool (depending on enabled modules):

- **Numbers** (manually declared values): pH, free chlorine (ppm), water
  temperature (°C), salt (g/L), salt added (kg), chlorinator output (g/h)
- **Selects**: chlorinator mode (smart/manual/boost), acid tank level (full…¼)
- **Timestamps**: last water test, salt added, filter wash, cell cleaning,
  probe calibration, acid refill, cleaning, and last maintenance of any kind —
  all driven by the date picked on the page, so back-dated work is recorded on
  the right day
- **Binary sensors**: filter wash due, cell cleaning due, probe calibration due
- **`sensor.<pool>_last_record`**: `who · date · what` summary, with the last
  20 records (including their ids) as attributes

Made a mistake? Call the **`pool_maintenance_tracker.delete_record`** action
(Developer tools → Actions): pick the pool and optionally a `record_id` from
the last-record sensor attributes — without an id it deletes the most recent
record. Task timestamps are rebuilt from the remaining records.
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
  "readings": { "ph": 7.2, "free_chlorine": 1.2, "salt": 4.5, "temperature": 27.5 },
  "chlorinator": { "output": 5, "mode": "smart" },
  "salt": { "added_kg": 25 },
  "acid": { "level": "quarter" },
  "cleaning": { "types": ["vacuum", "waterline"] },
  "note": "free text ≤ 500 chars (goes to the page-only notes diary)"
}
```

A payload containing only a valid `note` is accepted too — it stores the note
without creating a maintenance record.

Valid `categories`: `water_test`, `chlorinator`, `salt`, `filter_wash`,
`cell_clean`, `probe_calibration`, `acid_refill`, `cleaning` (limited to the
enabled modules).

Rules: every field is optional; `null`/absent fields change nothing;
out-of-range values (pH 6–9, chlorine 0–10 ppm, salt 0–10 g/L, salt added
0–500 kg, output 0–10 g/h) are ignored and echoed back in the `ignored` list;
sections for disabled modules are ignored; a payload with nothing valid gets
`400`. `logged_at` older than 7 days or more than 1 hour in the future is
replaced with server time (the page lets you back-date up to 6 days).

## Security notes

- Endpoints accept only `GET` (page) and `POST` (log); nothing can
  command your equipment. With the report tab enabled, anyone holding the page
  URL can also *read* the declared pool state, the chosen extra entities and
  recent records, and *add notes* — disable the tab in the options if you
  don't want that.
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
