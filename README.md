# TankTutor for Home Assistant

Custom integration that sends the aquarium sensors you already have in Home Assistant
(temperature, pH, salinity, ammonia, air, leak and level events) to
[TankTutor](https://tanktutor.org).

> **Status: in development.** Not installable yet. Progress is tracked in the
> TankTutor project; the first release will be announced on <https://tanktutor.org>.

## Prototype (0.1.0, unreleased)

Water temperature only: one sensor, sent to TankTutor with a persistent queue, the
5-minute rate limit, `429`/`401`/`5xx` handling and reauth. The other types are described
in [docs/spec.md](docs/spec.md).

- API address: `https://tanktutor.org/api` (staging: `https://tanktutor-stag.bitsofdream.it/api`).
- The device key comes from the tank page in TankTutor ("Device keys"). It is stored in the
  config entry and never logged.
- Only the mapped sensor is sent: type, value, unit and time. No entity id, name or other metadata.

### Tests

```
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/python -m pytest
```

## Planned

- Config flow: paste the per-tank device key, then map your Home Assistant entities to
  TankTutor measurement types.
- Batching and offline queue, within the TankTutor limit of one request every 5 minutes per user.
- Distribution through HACS as a custom repository.

## Disclaimer

This project is not affiliated with, endorsed by or sponsored by Nabu Casa or the
Home Assistant project. "Home Assistant" is a trademark of Nabu Casa, Inc., used here
only to describe compatibility.

## License

[MIT](LICENSE)
