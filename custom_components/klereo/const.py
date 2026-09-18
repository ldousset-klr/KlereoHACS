DOMAIN = "klereo"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_POOLID = "poolid"
CONF_SERVER = "server"
DEF_POOLID = 0
# Base URL of the Klereo Connect server, overridable per config entry so a dev
# or staging server can be pointed at. KLEREO_PATH is appended by the API, and
# accepted if the user already typed it.
DEF_SERVER = "https://connect.klereo.fr"
KLEREO_PATH = "/php"
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

# outs[].status, and the newState SetOut takes.
#
# On the filtration output the field is a variable-speed index, 0 (stopped) to 7.
# On every other output it is a state: 0 off, 1 on, 2 unknown.
OUT_STATUS_OFF = 0
OUT_STATUS_ON = 1
OUT_STATUS_UNKNOWN = 2

# Which out carries the filtration, and so which one reads as a speed index.
#
# Output roles look fixed by index, not declared in the payload: across two
# captured pools, outs 1/2/3/4 totalTime matches params Filtration_, PHMinus_,
# ElectroChlore_ and Chauff_TotalTime respectively (exactly for 2/3/4, within a
# poll for the filtration). Note outs[].type does NOT give the role: it read 0
# on all of them in one pool and 8 on the disinfectant and the heater in the
# other. The codeowner confirmed it is not the firmware's e_OutTypes; what it
# actually encodes is still to be determined, so do not build on it.
FILTRATION_OUT_INDEX = 1

# Highest speed index SetOut accepts on the filtration output. A pool advertises
# its own ceiling in PumpMaxSpeed (0, 1 and 3 seen, 0 meaning no speed control),
# which is what the speed entity uses; this is only the protocol limit, and the
# fallback for a payload that omits the field entirely.
MAX_PUMP_SPEED = 7

# probes[].index -> the name the controller gives that slot, from the firmware.
#
# Keyed on the probe INDEX, not its type: the two disagree on a few installs
# (a type 10 generic sitting at index 20, whose label reads "Température air 3"),
# so this is only a fallback, applied after IORename and never over it. On the
# captured pools every such slot carried a user name, so the mismatch stays
# hidden; a probe with an odd index and no IORename entry may be mislabelled.
#
# French on purpose: these are the controller's own wording, and the IORename
# names they sit beside are French too.
PROBE_LABELS = {
    0: "Température coffret",
    1: "Température air",
    2: "Température eau gen1",
    3: "pH gen1",
    4: "Redox gen1",
    5: "Pression gen1",
    6: "Niveau bidon pH",
    7: "Niveau bidon désinfectant",
    8: "Couverture",
    9: "pH Gen2",
    10: "Redox gen2",
    11: "Chlore gen2",
    12: "Température eau gen2",
    13: "Pression gen2-A",
    14: "Pression gen2-B",
    15: "Debit1",
    16: "Température Eau",
    17: "Capteur pH",
    18: "Capteur Redox",
    19: "Température air 2",
    20: "Température air 3",
    21: "Pression",
    22: "Chlore",
    23: "Bidon Floculant",
    24: "Debit2",
    25: "Température air 4",
    26: "Température air 5",
    27: "Température air 6",
    28: "Température air 7",
    29: "Température air 8",
    30: "Température air 9",
    31: "Température air 10",
}
