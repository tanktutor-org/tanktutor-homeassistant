"""Turns a Home Assistant state into a TankTutor reading (rules: docs/spec.md, section 4.2).

Pure Python apart from the State type, so it is easy to test. Every function returns None
for a state that must not be sent: unknown, unavailable, not a number, a unit that cannot be
trusted. A wrong number in an aquarium log is worse than a missing one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import State

from .const import AMMONIA_BASES, SALINITY_UNITS
from .queue import Reading

TEMPERATURE_UNITS = {"°C": "C", "°F": "F"}
# Home Assistant writes the micro sign (U+00B5); some integrations use the Greek mu (U+03BC).
CONDUCTIVITY_TO_MICROSIEMENS = {
    "µS/cm": 1.0,
    "μS/cm": 1.0,
    "mS/cm": 1_000.0,
    "S/cm": 1_000_000.0,
}
AMMONIA_UNITS = {"mg/L", "ppm"}  # equal in water


@dataclass(frozen=True)
class Mapping:
    type: str
    entity_id: str
    name: str | None = None  # events only
    invert: bool = False  # events only
    salinity_unit: str | None = None
    basis: str | None = None  # ammonia only


def _number(state: State) -> float | None:
    if state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    try:
        value = float(state.state)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def reading_for(mapping: Mapping, state: State | None) -> Reading | None:
    if state is None:
        return None
    at = state.last_updated
    unit = state.attributes.get("unit_of_measurement")

    if mapping.type == "event":
        if state.state not in ("on", "off") or mapping.name is None:
            return None
        active = (state.state == "on") != mapping.invert
        return Reading(type="event", name=mapping.name, value=1.0 if active else 0.0, measured_at=at)

    value = _number(state)
    if value is None:
        return None

    if mapping.type in ("temperature", "ambient_temperature"):
        sent = TEMPERATURE_UNITS.get(unit)
        if sent is None:
            return None
        return Reading(type=mapping.type, value=value, unit=sent, measured_at=at)

    if mapping.type == "ambient_humidity":
        if unit != "%" or not 0 <= value <= 100:
            return None
        return Reading(type="ambient_humidity", value=value, measured_at=at)

    if mapping.type == "ph":
        return Reading(type="ph", value=value, measured_at=at)

    if mapping.type == "conductivity":
        factor = CONDUCTIVITY_TO_MICROSIEMENS.get(unit)
        if factor is None:
            return None
        return Reading(type="conductivity", value=value * factor, measured_at=at)

    if mapping.type == "salinity":
        # The unit is the user's explicit choice: a density and a salinity cannot be told apart by value.
        if mapping.salinity_unit not in SALINITY_UNITS:
            return None
        return Reading(type="salinity", value=value, unit=mapping.salinity_unit, measured_at=at)

    if mapping.type == "ammonia":
        if unit not in AMMONIA_UNITS or mapping.basis not in AMMONIA_BASES:
            return None
        return Reading(type="ammonia", value=value, basis=mapping.basis, measured_at=at)

    return None


SENSOR_OPTION_KEYS = {
    "temperature": "temperature_entity",
    "ambient_temperature": "ambient_temperature_entity",
    "ambient_humidity": "ambient_humidity_entity",
    "ph": "ph_entity",
    "conductivity": "conductivity_entity",
    "salinity": "salinity_entity",
    "ammonia": "ammonia_entity",
}


def build_mappings(options: dict[str, Any]) -> list[Mapping]:
    mappings: list[Mapping] = []
    for kind, key in SENSOR_OPTION_KEYS.items():
        entity_id = options.get(key)
        if not entity_id:
            continue
        mappings.append(
            Mapping(
                kind,
                entity_id,
                salinity_unit=options.get("salinity_unit") if kind == "salinity" else None,
                basis=options.get("ammonia_basis") if kind == "ammonia" else None,
            )
        )
    for item in options.get("events") or []:
        if not isinstance(item, dict) or not item.get("entity") or not item.get("name"):
            continue
        mappings.append(
            Mapping("event", item["entity"], name=item["name"], invert=bool(item.get("invert", False)))
        )
    return mappings
