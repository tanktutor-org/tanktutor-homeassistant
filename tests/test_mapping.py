"""Turning a Home Assistant state into a TankTutor reading, per type (docs/spec.md, section 4.2)."""

from datetime import datetime, timezone

import pytest
from homeassistant.core import State

from custom_components.tanktutor.mapping import Mapping, build_mappings, reading_for

T = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def state(value, unit=None, entity="sensor.x"):
    attrs = {"unit_of_measurement": unit} if unit is not None else {}
    return State(entity, str(value), attrs, last_updated=T, last_changed=T)


def read(mapping, value, unit=None):
    return reading_for(mapping, state(value, unit))


# --- temperature, air temperature -------------------------------------------------

@pytest.mark.parametrize("kind", ["temperature", "ambient_temperature"])
@pytest.mark.parametrize(("unit", "sent"), [("°C", "C"), ("°F", "F")])
def test_temperatures_keep_their_celsius_or_fahrenheit_unit(kind, unit, sent):
    reading = read(Mapping(kind, "sensor.x"), "24.5", unit)
    assert (reading.type, reading.value, reading.unit) == (kind, 24.5, sent)
    assert reading.measured_at == T


def test_kelvin_is_refused():
    assert read(Mapping("temperature", "sensor.x"), "297", "K") is None


# --- humidity -------------------------------------------------------------------------

def test_humidity_in_percent_is_sent_without_unit():
    reading = read(Mapping("ambient_humidity", "sensor.x"), "55", "%")
    assert (reading.type, reading.value, reading.unit) == ("ambient_humidity", 55.0, None)


@pytest.mark.parametrize("value", ["-1", "101"])
def test_humidity_outside_0_100_is_refused(value):
    assert read(Mapping("ambient_humidity", "sensor.x"), value, "%") is None


def test_humidity_with_another_unit_is_refused():
    assert read(Mapping("ambient_humidity", "sensor.x"), "0.5", "ratio") is None


# --- pH -------------------------------------------------------------------------------

def test_ph_is_sent_without_unit():
    reading = read(Mapping("ph", "sensor.x"), "7.4")
    assert (reading.type, reading.value, reading.unit) == ("ph", 7.4, None)


def test_ph_ignores_whatever_unit_the_entity_declares():
    assert read(Mapping("ph", "sensor.x"), "7.4", "pH").unit is None


# --- conductivity ----------------------------------------------------------------------

@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        ("500", "µS/cm", 500.0),
        ("500", "μS/cm", 500.0),  # Greek mu, not the micro sign
        ("1.5", "mS/cm", 1500.0),
        ("0.0015", "S/cm", 1500.0),
    ],
)
def test_conductivity_is_converted_to_microsiemens(value, unit, expected):
    reading = read(Mapping("conductivity", "sensor.x"), value, unit)
    assert reading.value == pytest.approx(expected)
    assert reading.unit is None


def test_conductivity_without_a_known_unit_is_refused():
    assert read(Mapping("conductivity", "sensor.x"), "500", "ppm") is None
    assert read(Mapping("conductivity", "sensor.x"), "500") is None


# --- salinity ----------------------------------------------------------------------------

@pytest.mark.parametrize(("choice", "value"), [("ppt", "35"), ("SG", "1.024")])
def test_salinity_uses_the_unit_the_user_chose(choice, value):
    reading = read(Mapping("salinity", "sensor.x", salinity_unit=choice), value, "whatever")
    assert reading.unit == choice
    assert reading.value == float(value)


def test_salinity_without_a_chosen_unit_is_refused():
    assert read(Mapping("salinity", "sensor.x"), "35") is None


# --- ammonia -------------------------------------------------------------------------------

@pytest.mark.parametrize("unit", ["mg/L", "ppm"])
@pytest.mark.parametrize("basis", ["free", "total"])
def test_ammonia_carries_the_chosen_basis(unit, basis):
    reading = read(Mapping("ammonia", "sensor.x", basis=basis), "0.25", unit)
    assert (reading.value, reading.basis, reading.unit) == (0.25, basis, None)


@pytest.mark.parametrize("unit", ["µg/L", "mol/L", None])
def test_ammonia_in_other_units_is_refused(unit):
    assert read(Mapping("ammonia", "sensor.x", basis="free"), "0.25", unit) is None


def test_ammonia_without_a_chosen_basis_is_refused():
    assert read(Mapping("ammonia", "sensor.x"), "0.25", "mg/L") is None


# --- events ---------------------------------------------------------------------------------

def test_event_on_is_1_and_off_is_0():
    mapping = Mapping("event", "binary_sensor.x", name="leak")
    assert (read(mapping, "on").value, read(mapping, "on").name) == (1.0, "leak")
    assert read(mapping, "off").value == 0.0


def test_event_can_be_inverted():
    mapping = Mapping("event", "binary_sensor.x", name="level_low", invert=True)
    assert read(mapping, "on").value == 0.0
    assert read(mapping, "off").value == 1.0


def test_event_has_no_unit():
    assert read(Mapping("event", "binary_sensor.x", name="leak"), "on").unit is None


# --- states that never produce a reading ---------------------------------------------------------

@pytest.mark.parametrize("value", ["unknown", "unavailable", "abc", "nan", "inf"])
@pytest.mark.parametrize("kind", ["temperature", "ph", "ambient_humidity"])
def test_unusable_states_give_nothing(kind, value):
    assert read(Mapping(kind, "sensor.x"), value, "°C") is None


def test_a_missing_state_gives_nothing():
    assert reading_for(Mapping("ph", "sensor.x"), None) is None


def test_event_in_unusable_state_gives_nothing():
    mapping = Mapping("event", "binary_sensor.x", name="leak")
    assert read(mapping, "unavailable") is None
    assert read(mapping, "unknown") is None


# --- from the stored options --------------------------------------------------------------------

def test_build_mappings_reads_every_configured_type():
    options = {
        "temperature_entity": "sensor.water",
        "ambient_temperature_entity": "sensor.air",
        "ambient_humidity_entity": "sensor.hum",
        "ph_entity": "sensor.ph",
        "conductivity_entity": "sensor.ec",
        "salinity_entity": "sensor.sal",
        "salinity_unit": "ppt",
        "ammonia_entity": "sensor.nh3",
        "ammonia_basis": "total",
        "events": [{"entity": "binary_sensor.leak", "name": "leak", "invert": False}],
    }
    mappings = build_mappings(options)
    assert {m.type for m in mappings} == {
        "temperature", "ambient_temperature", "ambient_humidity", "ph",
        "conductivity", "salinity", "ammonia", "event",
    }
    by_type = {m.type: m for m in mappings}
    assert by_type["salinity"].salinity_unit == "ppt"
    assert by_type["ammonia"].basis == "total"
    assert by_type["event"].name == "leak"


def test_build_mappings_skips_what_is_not_configured():
    assert build_mappings({}) == []
    assert build_mappings({"temperature_entity": None}) == []


def test_build_mappings_ignores_malformed_events():
    assert build_mappings({"events": [{"entity": "binary_sensor.x"}, "junk"]}) == []
