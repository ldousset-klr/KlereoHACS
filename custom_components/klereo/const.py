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
# Units marked (*) are inferred from the params bounds rather than observed on a
# live probe; the ones with no unit have a known quantity but no confirmed unit,
# so they are published as plain numbers rather than mislabelled. GENERIC and
# UNKNOWN are unitless by design: the firmware itself does not know the quantity.
PROBE_TYPES = {
    0:  ("plant room temperature", "temperature", "°C",   "measurement"),
    1:  ("air temperature",        "temperature", "°C",   "measurement"),
    2:  ("water level",            None,          None,   "measurement"),
    3:  ("pH",                     "ph",          None,   "measurement"),
    4:  ("redox",                  None,          "mV",   "measurement"),
    5:  ("water temperature",      "temperature", "°C",   "measurement"),
    6:  ("filter pressure",        "pressure",    "mbar", "measurement"),  # (*) params PressureMin/Max 200..1200
    7:  ("total alkalinity",       None,          None,   "measurement"),
    8:  ("salinity",               None,          None,   "measurement"),
    9:  ("turbidity",              None,          None,   "measurement"),
    10: ("generic",                None,          None,   "measurement"),
    11: ("flow",                   None,          None,   "measurement"),
    12: ("canister level",         None,          None,   "measurement"),
    13: ("cover",                  None,          None,   "measurement"),
    14: ("chlorine",               None,          "mg/L", "measurement"),  # (*) params ConsigneChlore 1.5, ChlMin/Max 0.1..5
    15: ("unknown",                None,          None,   "measurement"),
}
PROBE_TYPE_DEFAULT = ("unsupported", None, None, "measurement")
