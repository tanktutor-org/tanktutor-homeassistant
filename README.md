# TankTutor for Home Assistant

Custom integration that sends the aquarium sensors you already have in Home Assistant
(temperature, pH, salinity, ammonia, air, leak and level events) to
[TankTutor](https://tanktutor.org).

> **Status: in development.** Not installable yet. Progress is tracked in the
> TankTutor project; the first release will be announced on <https://tanktutor.org>.

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
