"""Constants for the TankTutor integration."""

import re

DOMAIN = "tanktutor"

CONF_URL = "url"
CONF_KEY = "key"
CONF_TEMPERATURE_ENTITY = "temperature_entity"
CONF_EVENTS = "events"

# Mirrors the TankTutor API (apps/api/src/sensorEvents/builtinEvents.ts, devices/ingestRoutes.ts).
BUILTIN_EVENTS = ("leak", "level_low", "level_high")
MAX_CUSTOM_EVENTS = 10
EVENT_NAME_RE = re.compile(r"^[a-z0-9_]{1,40}$")
SALINITY_UNITS = ("ppt", "SG")
AMMONIA_BASES = ("free", "total")

# The web app proxies the API under /api.
DEFAULT_URL = "https://tanktutor.org/api"

STORAGE_VERSION = 1
TICK_INTERVAL_SECONDS = 60
