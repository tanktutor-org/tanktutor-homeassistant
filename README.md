# TankTutor for Home Assistant

Custom integration that sends the aquarium sensors you already have in Home Assistant
(temperature, pH, salinity, ammonia, air, leak and level events) to
[TankTutor](https://tanktutor.org).

> **Status: in development.** Not installable yet. Progress is tracked in the
> TankTutor project; the first release will be announced on <https://tanktutor.org>.

## Prototype (0.1.0, unreleased)

All the types the TankTutor API accepts, each mapped explicitly in the integration options:
water and air temperature, air humidity, pH, conductivity, salinity (ppt or SG), ammonia (free or
total) and on/off events (leak, level, your own names, optional inversion). It sends with a
persistent queue, the 5-minute rate limit, `429`/`401`/`403`/`5xx` handling and reauth.
Details and rules: [docs/spec.md](docs/spec.md).

- API address: `https://tanktutor.org/api`.
- The device key comes from the tank page in TankTutor ("Device keys"). It is stored in the
  config entry and never logged.
- Only the mapped sensors are sent: type, value, unit and time. No entity id, name or other metadata.
- An unusable state (unknown, unavailable, not a number, a unit that cannot be trusted) is never sent.
- The key is checked when you add it (`GET /devices/me`, no side effects): a wrong or revoked key is refused on the spot and the entry is titled with the tank name.
- Tested with a fake server and, by hand, on a real Home Assistant (2026.10) against TankTutor's staging.

### Tests

```
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/python -m pytest
```

## Planned

- Distribution through HACS as a custom repository (first tagged release).

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
