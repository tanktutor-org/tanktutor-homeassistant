# TankTutor for Home Assistant

Custom integration that sends the aquarium sensors you already have in Home Assistant
(temperature, pH, salinity, ammonia, air, leak and level events) to
[TankTutor](https://tanktutor.org).

> **Status: first release (0.1.0).** Installable through HACS as a custom repository (see below).
> Early version: report problems in the issue tracker.

## Install

1. In HACS, add this repository as a custom repository (type **Integration**):
   `https://github.com/tanktutor-org/tanktutor-homeassistant`. Then install **TankTutor**.
2. In TankTutor, on the tank page, open "Device keys" and generate a key (shown only once).
3. In Home Assistant, add the **TankTutor** integration and paste the key. It is checked
   straight away; a wrong or revoked key is refused.
4. In the integration options, pick the sensor to use for each measurement type and add the events.

Repeat steps 2 to 4 for every other tank: each tank has its own key.

## What it does

All the types the TankTutor API accepts, each mapped explicitly in the integration options:
water and air temperature, air humidity, pH, conductivity, salinity (ppt or SG), ammonia (free or
total) and on/off events (leak, level, your own names, optional inversion). It sends with a
persistent queue, the 5-minute rate limit, `429`/`401`/`403`/`5xx` handling and reauth.
Details and rules: [docs/spec.md](docs/spec.md).

- Requires Home Assistant 2026.3.0 or later (`hacs.json`; the integration ships its icon in `brand/`).
- API address: `https://tanktutor.org/api`.
- The device key comes from the tank page in TankTutor ("Device keys"). It is stored in the
  config entry and never logged.
- Only the mapped sensors are sent: type, value, unit and time. No entity id, name or other metadata.
- An unusable state (unknown, unavailable, not a number, a unit that cannot be trusted) is never sent.
- The key is checked when you add it (`GET /devices/me`, no side effects): a wrong or revoked key is refused on the spot and the entry is titled with the tank name.
- Tested with a fake server (automated tests) and, by hand, on a real Home Assistant (2026.10)
  against a TankTutor instance: temperature, pH, conductivity, ammonia, salinity, air and a leak
  event; a wrong key, a second tank, a duplicate key, a revoked key (reauth), salinity on a freshwater
  tank (ignored) and the icon.
- **Not tried by hand:** the offline queue (sending after a network outage) and installing from HACS
  on a real instance. Both are covered by the automated tests only.
- After a restart, an event whose state did not change (e.g. "leak off") is not sent again.

### Tests

```
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/python -m pytest
```

## Not yet

- Listing in the default HACS store.
- Trying the offline queue and the HACS install by hand on a real instance.

## Icon

`custom_components/tanktutor/brand/icon.png` (256 px) and `icon@2x.png` (512 px) are the TankTutor
mark from the website header; the vector source is `assets/icon.svg`. Home Assistant 2026.3 and later
reads brand images from the integration's own `brand/` folder. No Home Assistant artwork is used.

## Disclaimer

This project is not affiliated with, endorsed by or sponsored by Nabu Casa or the
Home Assistant project. "Home Assistant" is a trademark of Nabu Casa, Inc., used here
only to describe compatibility.

## License

[MIT](LICENSE)
