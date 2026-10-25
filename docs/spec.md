# TankTutor for Home Assistant — short specification

Status: implemented in 0.1.0 (2026-10-26); open points below. Tracks TankTutor issue #68.
Source of truth for the server side: `POST /devices/readings` in the TankTutor API (4.4.0),
`apps/api/src/devices/ingestRoutes.ts`. This document describes only what the integration
does with it; if the API changes, the API wins.

## 1. Scope

In: push to TankTutor, from Home Assistant (HA), the readings the user maps explicitly.
Out: actuators, reading data back from TankTutor, any entity created in HA by this
integration (the first version creates **no entities**, only a service-like background
sender and diagnostics), direct integrations with single manufacturers.

## 2. Server contract (as implemented in 4.4.0)

`POST https://tanktutor.org/api/devices/readings` (base URL configurable)

- Auth: `Authorization: Bearer <device key>`; one key per tank, created by the user in TankTutor.
- Body: `{"readings": [ ... ]}`, 1 to 60 entries.
- Reading: `{"type", "value", "unit"?, "measuredAt"?, "name"?, "basis"?}`.
  - `value` must be a finite number.
  - `measuredAt`: ISO 8601 **with** zone offset; at most 5 minutes in the future and 7 days in the past.
    Without it the server uses its own clock.
  - Within one batch a `(type, name, measuredAt)` triple may appear once; without `measuredAt` once per type.
- A retry of an already stored `(tank, type, measuredAt)` is ignored, not an error: resending is safe.

| `type` | `unit` accepted | Notes |
|---|---|---|
| `temperature` | `C` (default), `F` | water |
| `ph` | none | |
| `conductivity` | none (µS/cm) | |
| `salinity` | `ppt` (default), `SG` | marine and brackish tanks only; a density the server cannot convert rejects the batch |
| `ammonia` | none (mg/L) | `basis`: `free` (default) or `total` |
| `ambient_temperature` | `C`, `F` | air |
| `ambient_humidity` | none (%) | air, 0–100 |
| `event` | none | `name` required (`[a-z0-9_]{1,40}`), `value` 0 or 1; built-in names `leak`, `level_low`, `level_high`, at most 10 custom names per tank |

Responses:

| Status | Body | Meaning | Integration action |
|---|---|---|---|
| 200 | `{"saved": n, "ignored"?: m}` | batch processed (`ignored`: implausible, duplicate, over the custom-event cap, type not allowed for the tank) | drop the batch from the queue |
| 400 | `invalid_device_readings` | **whole batch rejected, no detail on which entry** | see 5.3 |
| 401 | `authentication_required` / `invalid_device_key` | missing or revoked key | start HA reauth |
| 403 | `account_suspended` | account suspended | keep queue, retry hourly, show a repair issue |
| 429 | `rate_limited` + `Retry-After` | one request per 5 minutes **per user** (all keys together) | wait `Retry-After`, keep queue |
| 5xx / network | | | exponential backoff 1 min → 1 h, keep queue |

Only a request that passes validation and is accepted consumes the window: a `400` (validation runs first) and a `429` do not.
Windows are **fixed and aligned to the clock** (multiples of 5 minutes since the epoch, not "5 minutes after the last send"): after a `200`, the next send is possible from the next window boundary.

## 3. Shape

- Custom integration, domain `tanktutor`, `custom_components/tanktutor/`, MIT.
- One **config entry per tank** (the key is per tank). `iot_class`: `cloud_push`.
- Distribution: GitHub mirror `tanktutor-org/tanktutor-homeassistant` as a HACS custom repository
  (HACS supports only public GitHub repos); source of truth on the TankTutor Gitea.
  Tagged releases (`vX.Y.Z`, matching `manifest.json` `version`).
- No third-party Python dependencies: use HA's `aiohttp` client session.

## 4. Configuration

### 4.1 Config flow
1. `user`: base URL (default production) and device key. The key is stored in the config entry data;
   it is never logged.
2. Validation: `GET /devices/me` (TankTutor 4.5.0) answers `{"tankName", "waterType"}` without side effects
   and without using the rate-limit window. `401` → "key not accepted" (stays on the form), `403` →
   suspended account, network error or `5xx` → "cannot reach TankTutor". A server without the endpoint
   (`404`) does not block the setup: the key is then checked at the first send, as before. The tank name
   becomes the title of the entry.
3. `unique_id`: SHA-256 prefix of the key (the key itself must not be the id).
4. `reauth`: asks for a new key and checks it the same way before saving it.

### 4.2 Options flow (the mapping)
Zero or more mappings, each: source entity → TankTutor type.

| TankTutor type | Candidate entities | Unit handling |
|---|---|---|
| `temperature` | `sensor`, device class `temperature` | `°C`/`°F` as reported |
| `ambient_temperature` | same, user picks which is air | same |
| `ambient_humidity` | `sensor`, device class `humidity` | `%` only |
| `ph` | `sensor`, device class `ph` or any numeric sensor | no unit sent |
| `conductivity` | `sensor`, device class `conductivity` | convert `mS/cm`→µS/cm ×1000, `S/cm`→×1e6; other units: entity refused |
| `salinity` | any numeric sensor | `ppt` or `SG`; the unit is chosen by the user in the mapping and never guessed from the value; an entity with another unit is refused |
| `ammonia` | any numeric sensor | `mg/L` or `ppm` (equal) only; user chooses `free` or `total` explicitly |
| `event` | `binary_sensor` | `on`=1, `off`=0; option **invert**; name chosen from a list (`leak`, `level_low`, `level_high`) or a custom name validated against `[a-z0-9_]{1,40}`; default proposed from device class (`moisture` → `leak`) |

Rules: a type can be mapped at most once per entry (an event name once); nothing is sent for
unmapped entities; the integration never sends entity ids, friendly names, areas or any HA metadata
(payload is exactly the table in section 2). The API is the only validation of the water type
(for example salinity on a freshwater tank is `ignored`); the options flow only warns about it.

## 5. Runtime behaviour

### 5.1 Collection
- Subscribe to `state_changed` of the mapped entities only.
- States `unknown`, `unavailable`, non-numeric: skipped, never sent.
- For numeric types keep the **latest** valid value per mapping with its `last_updated` as
  `measuredAt` (UTC with `+00:00`). One reading per type per flush, not every change.
- For events: every transition is queued (it matters when it happened); consecutive duplicates of the
  same state are collapsed.

### 5.2 Flush and queue
- At most one flush per server window: after a `200` wait for the next 5-minute boundary (plus a few seconds of
  margin for clock skew); on a `429` wait `Retry-After`. The 5 minutes is a constant, not read from the server.
- An event transition to 1 triggers a flush as soon as the window allows, not at the next tick.
- Batch: oldest first, up to 60 readings, with unique `(type, name, measuredAt)`.
- The queue is persisted (`homeassistant.helpers.storage.Store`) so a restart or an outage loses nothing;
  readings older than 6 days 23 hours are dropped (server limit is 7 days); readings not yet sent are
  kept up to a cap of 2000 entries, dropping the oldest numeric ones first, **never** events before numerics.
- Backlog larger than 60: sent over consecutive windows.

### 5.3 Handling `400`
The server gives no detail, so: (1) validate locally with the same rules before sending (finite number,
timestamp window, unit, event name, uniqueness) and drop what fails with a log line; (2) if a `400` still
happens, bisect the batch over the next windows to isolate the offending reading, drop it and raise a
repair issue naming the mapping (never the value of the key). A batch of one reading that returns `400` is dropped.

### 5.4 Diagnostics and privacy
- Diagnostics redact the key. Logs never contain the key or the `Authorization` header.
- The integration sends nothing but the readings of the user's mappings. The TankTutor privacy policy
  already covers device readings; the README states what is sent.

## 6. Testing
- `pytest-homeassistant-custom-component`: config flow (success, bad key format, reauth), options flow
  (each type, unit refusal, invert), queue (persistence, expiry, cap), sender (200, 400 bisect, 401, 403, 429
  with `Retry-After`, 5xx backoff, restart mid-backlog).
- A fake TankTutor server in the tests mirrors the table in section 2.
- Manual check on a real Home Assistant instance before every release: one temperature and one event.

## 7. Plan
1. **Prototype** (issue step 3): config flow with key, options flow with a single `temperature` mapping,
   sender with queue and `429`/`401` handling, against a real instance.
2. All types, `400` bisect, diagnostics, tests, README, `v0.1.0`.
3. HACS custom-repository check (structure, `hacs.json`, brand icon, validation Actions), docs page in
   TankTutor, only then the public Home Assistant page and SEO (issue step 5).

## 8. Open points
1. ~~`GET /devices/me`~~ — done in TankTutor 4.5.0 (issue #69) and used by the config flow.
2. Brand icon (`brand/icon.png`) for HACS: no HA or Nabu Casa logo; TankTutor logo only.
3. Minimum HA version (decide when the prototype runs on a real instance).
4. Whether the options flow also offers an optional "send interval" (default 5 min, never below the server limit).
