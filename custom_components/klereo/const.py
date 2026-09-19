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
# Confirmed by the firmware: output roles are fixed by index, and index 1 is the
# filtration (see OUT_LABELS below). That matches what the payloads already
# showed, outs 1/2/3/4 totalTime tracking params Filtration_, PHMinus_,
# ElectroChlore_ and Chauff_TotalTime. Note outs[].type does NOT give the role:
# it read 0 on all of them in one pool and 8 on the disinfectant and the heater
# in the other. The codeowner confirmed it is not the firmware's e_OutTypes;
# what it actually encodes is still to be determined, so do not build on it.
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
    9: "pH gen2",
    10: "Redox gen2",
    11: "Chlore gen2",
    12: "Température eau gen2",
    13: "Pression gen2-A",
    14: "Pression gen2-B",
    15: "Débit1",
    16: "Température eau",
    17: "Capteur pH",
    18: "Capteur redox",
    19: "Température air 2",
    20: "Température air 3",
    21: "Pression",
    22: "Chlore",
    23: "Bidon floculant",
    24: "Débit2",
    25: "Température air 4",
    26: "Température air 5",
    27: "Température air 6",
    28: "Température air 7",
    29: "Température air 8",
    30: "Température air 9",
    31: "Température air 10",
}

# outs[].index -> the name the controller gives that slot, from the firmware.
#
# Same rule as PROBE_LABELS: a fallback applied only when IORename has nothing,
# never over it. Installations that are not pools reuse the slots for other
# purposes — a boiler names out 0 "Circulateur" where the table reads
# "Éclairage" — and auxiliaries almost always carry a user name, so the generic
# "Auxiliaire N" rarely surfaces.
OUT_LABELS = {
    0: "Éclairage",
    1: "Filtration",
    2: "Correcteur pH",
    3: "Désinfectant",
    4: "Chauffage",
    5: "Auxiliaire 1",
    6: "Auxiliaire 2",
    7: "Auxiliaire 3",
    8: "Floculant",
    9: "Auxiliaire 4",
    10: "Auxiliaire 5",
    11: "Auxiliaire 6",
    12: "Auxiliaire 7",
    13: "Auxiliaire 8",
    14: "Auxiliaire 9",
    15: "Chlore hybride",
}

# outs[].mode, and the newMode SetOut takes.
OUT_MODES = {
    0: "Manuel",
    1: "Plages horaires",
    2: "Minuterie",
    3: "Régulé",
    4: "Synchronisé",
    6: "Maintenance",
    8: "Impulsion",
}

# Which modes may be offered for an out, by index — roles being fixed by index.
# Anything outside these lists is reserved: if an out already carries such a
# value, leave it untouched rather than writing one of these over it.
#
# Filtration (1) and hybrid chlorine (15) are deliberately absent: the firmware's
# allowed list for them has not been supplied. Modes 0/1/3 and 2/3 have merely
# been *observed* on them, which is not the same as being permitted, so nothing
# offers a mode change on those two.
_MODES_SWITCHED = (0, 1, 2, 4, 6, 8)  # lighting and auxiliaries
_MODES_REGULATED = (0, 3)             # pH, disinfectant, flocculant, heating
OUT_MODE_CHOICES = {
    0: _MODES_SWITCHED,
    2: _MODES_REGULATED,
    3: _MODES_REGULATED,
    4: _MODES_REGULATED,
    5: _MODES_SWITCHED,
    6: _MODES_SWITCHED,
    7: _MODES_SWITCHED,
    8: _MODES_REGULATED,
    9: _MODES_SWITCHED,
    10: _MODES_SWITCHED,
    11: _MODES_SWITCHED,
    12: _MODES_SWITCHED,
    13: _MODES_SWITCHED,
    14: _MODES_SWITCHED,
}

# Outs Home Assistant may write to, for now: lighting and the auxiliaries —
# exactly the group that takes the _MODES_SWITCHED list above. Everything else
# (filtration, pH, disinfectant, heating, flocculant, hybrid chlorine) is
# read-only until the codeowner specifies how SetOut should be called on them;
# their entities still exist and still report state.
WRITABLE_OUT_INDEXES = frozenset({0, 5, 6, 7, 9, 10, 11, 12, 13, 14})

# Icons, only where Home Assistant has no default of its own. Probe types that
# carry a device_class (temperature, ph, pressure) are left alone: HA already
# picks a fitting icon and changing it would also lose the state-aware variants.
# Every name below was checked against the Material Design Icons set.
PROBE_ICONS = {
    2: "mdi:water-percent",       # water level
    4: "mdi:flash",               # redox
    7: "mdi:beaker-outline",      # alkalinity / hardness
    8: "mdi:shaker-outline",      # salinity
    9: "mdi:blur",                # turbidity
    11: "mdi:waves-arrow-right",  # flow
    12: "mdi:car-coolant-level",  # canister level
    13: "mdi:window-shutter",     # cover
    14: "mdi:flask",              # chlorine
}

# Switch icons follow the out's role, which is its index.
_ICON_AUX = "mdi:power-plug"
OUT_ICONS = {
    0: "mdi:lightbulb",
    1: "mdi:water-pump",
    2: "mdi:test-tube",
    3: "mdi:spray-bottle",
    4: "mdi:radiator",
    5: _ICON_AUX,
    6: _ICON_AUX,
    7: _ICON_AUX,
    8: "mdi:beaker",
    9: _ICON_AUX,
    10: _ICON_AUX,
    11: _ICON_AUX,
    12: _ICON_AUX,
    13: _ICON_AUX,
    14: _ICON_AUX,
    15: "mdi:flask",
}

ICON_FILTRATION_SPEED = "mdi:speedometer"
ICON_INFO = "mdi:identifier"
