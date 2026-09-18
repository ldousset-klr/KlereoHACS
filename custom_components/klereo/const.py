DOMAIN = "klereo"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_POOLID = "poolid"
DEF_POOLID = 0
KLEREOSERVER = "https://connect.klereo.fr/php"
UPDATE_INTERVAL = 300
HA_VERSION = "100-HA"
HTTP_TIMEOUT = 30

# Value reported by a probe that is absent or unreadable (seen on an air probe
# whose filteredTime is null). Thresholds use -2000 as the same kind of marker.
PROBE_INVALID = -1000

# probe['type'] -> (label, device_class, unit, state_class)
#
# Keys are the firmware's e_TypeCapteurs enum, taken from the board sources.
# Every unit here is confirmed. GENERIC, UNKNOWN and TURBIDITE carry no unit on
# purpose; for the first two the firmware does not know the quantity.
#
# Type 7 covers both TAC (alkalinity) and TH (hardness) — the firmware does not
# distinguish them and both are in French degrees, so a probe of this type
# cannot be told apart from the payload alone.
#
# "°f" is the French degree of alkalinity/hardness, not Fahrenheit: keep it
# lowercase and never give it a temperature device_class, or Home Assistant
# would convert it.
#
# No device_class is set for the percentage and flow entries: Home Assistant has
# no generic percentage class, and volume_flow_rate does not exist on the older
# versions hacs.json still allows.
PROBE_TYPES = {
    0:  ("plant room temperature", "temperature", "°C",   "measurement"),
    1:  ("air temperature",        "temperature", "°C",   "measurement"),
    2:  ("water level",            None,          "%",    "measurement"),
    3:  ("pH",                     "ph",          None,   "measurement"),
    4:  ("redox",                  None,          "mV",   "measurement"),
    5:  ("water temperature",      "temperature", "°C",   "measurement"),
    6:  ("filter pressure",        "pressure",    "mbar", "measurement"),
    7:  ("alkalinity or hardness", None,          "°f",   "measurement"),
    8:  ("salinity",               None,          "g/L",  "measurement"),
    9:  ("turbidity",              None,          None,   "measurement"),
    10: ("generic",                None,          None,   "measurement"),
    11: ("flow",                   None,          "m³/h", "measurement"),
    12: ("canister level",         None,          "%",    "measurement"),
    13: ("cover",                  None,          "%",    "measurement"),
    14: ("chlorine",               None,          "mg/L", "measurement"),
    15: ("unknown",                None,          None,   "measurement"),
}
PROBE_TYPE_DEFAULT = ("unsupported", None, None, "measurement")
