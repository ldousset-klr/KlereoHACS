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

# The same 2, written rather than read, means "apply the mode and leave the
# output's state as the controller has it". It is the only way to change an
# out's mode without also commanding it on or off, which is why a mode change
# always sends this. On the filtration out it is not a sentinel at all but
# speed 2, so it must never be written there.
OUT_STATE_KEEP = 2

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

# A mode's name can depend on the output it is on. Mode 2 reads "Minuterie" on
# the switched outs and "Volume fixe" on the pH corrector; the codeowner
# confirmed the two are functionally identical and only the label differs.
# Read through entity.klereo_out_mode_name(), never OUT_MODES directly.
# The dosing pumps — the pH corrector (2) and the flocculant (8) — call mode 2
# "Volume fixe" where the switched outs call it "Minuterie".
_MODE_NAMES_DOSING = {2: "Volume fixe"}
OUT_MODE_NAME_OVERRIDES = {
    2: _MODE_NAMES_DOSING,  # pH corrector
    8: _MODE_NAMES_DOSING,  # flocculant
}

# What newState may carry, per out index and per mode. The permitted lists come
# from the codeowner, one output family at a time, and each family has its own:
# the same mode number does not take the same states everywhere.
#
# Where OUT_STATE_KEEP appears, a mode change can leave the output's state
# alone, and that is what select.py sends. Where it does not, the mode change
# necessarily commands the output too — see _MODE_STATES_PH below.
_MODE_STATES_SWITCHED = {  # lighting (0) and the auxiliaries (5-7, 9-14)
    0: (OUT_STATUS_OFF, OUT_STATUS_ON, OUT_STATE_KEEP),  # Manuel
    1: (OUT_STATE_KEEP,),                                # Plages horaires
    2: (OUT_STATUS_OFF, OUT_STATUS_ON, OUT_STATE_KEEP),  # Minuterie
    4: (OUT_STATE_KEEP,),                                # Synchronisé
    6: (OUT_STATUS_OFF, OUT_STATUS_ON, OUT_STATE_KEEP),  # Maintenance
    8: (OUT_STATUS_OFF, OUT_STATUS_ON, OUT_STATE_KEEP),  # Impulsion
}

# The pH corrector (2). Note Manuel here takes **only** OUT_STATUS_OFF: a dosing
# pump put back under manual control is stopped, it cannot be commanded on and
# it cannot keep its state. So selecting Manuel on this output does stop the
# dosing — the one place where changing a mode also changes what the output is
# doing, and deliberately so.
_MODE_STATES_PH = {
    0: (OUT_STATUS_OFF,),                                # Manuel
    2: (OUT_STATUS_OFF, OUT_STATUS_ON, OUT_STATE_KEEP),  # Volume fixe
    3: (OUT_STATE_KEEP,),                                # Régulé
}

# The flocculant (8), the same dosing pump without the regulation: Manuel and
# Volume fixe, and no Régulé at all. Worth noting against the (0, 3) it had
# been given before its real rules arrived — that list was wrong in both
# directions, missing mode 2 and inventing mode 3.
_MODE_STATES_FLOC = {
    0: (OUT_STATUS_OFF,),                                # Manuel
    2: (OUT_STATUS_OFF, OUT_STATUS_ON, OUT_STATE_KEEP),  # Volume fixe
}

# The heating output (4) is the one whose rules come from the payload rather
# than from its index: params.HeaterMode says what it actually drives, and a
# heat pump takes four modes where a dry-contact heater takes two — mode 3
# reading "Réchauffe" on the one and "Régulé" on the other.
HEATER_OUT_INDEX = 4

# params.HeaterMode, from the firmware's own enum.
HEATER_NONE = 0          # no heating at all
HEATER_NORMAL = 1        # dry-contact heater
HEATER_PAC_KLINK = 2     # Klereo heat pump driven over K-LINK
HEATER_NOTARGET = 3
HEATER_PAC_MODBUS = 4    # Klereo heat pump driven over ModBus

_MODE_STATES_HEATER_CONTACT = {   # HEATER_NORMAL, HEATER_NOTARGET
    0: (OUT_STATUS_OFF,),   # Manuel — stop only, as on the pH corrector
    3: (OUT_STATE_KEEP,),   # Régulé
}
_MODE_STATES_HEATER_PAC = {       # HEATER_PAC_KLINK, HEATER_PAC_MODBUS
    0: (OUT_STATUS_OFF,),   # Manuel — stop only
    1: (OUT_STATE_KEEP,),   # Auto
    2: (OUT_STATE_KEEP,),   # Refroidit
    3: (OUT_STATE_KEEP,),   # Réchauffe
}
# A heat pump renames three modes, mode 3 included: the same number reads
# "Régulé" on a dry-contact heater and "Réchauffe" here.
_MODE_NAMES_HEATER_PAC = {1: "Auto", 2: "Refroidit", 3: "Réchauffe"}

# HeaterMode -> (states by mode, name overrides). HEATER_NONE and any value
# outside the enum are absent on purpose: nothing is written to a heating
# output whose kind is not established, and a missing HeaterMode reads the
# same way.
HEATER_VARIANTS = {
    HEATER_NORMAL:     (_MODE_STATES_HEATER_CONTACT, {}),
    HEATER_NOTARGET:   (_MODE_STATES_HEATER_CONTACT, {}),
    HEATER_PAC_KLINK:  (_MODE_STATES_HEATER_PAC, _MODE_NAMES_HEATER_PAC),
    HEATER_PAC_MODBUS: (_MODE_STATES_HEATER_PAC, _MODE_NAMES_HEATER_PAC),
}

# {out index: {mode: permitted newState values}} for the outs whose rules do not
# depend on the payload. The heating output is resolved separately, through
# HEATER_VARIANTS — read every out through entity.klereo_out_mode_states(),
# never this table directly, or the heating output will be missed.
#
# A mode's keys are also the modes that may be *offered* on that out, in the
# firmware's own order. Anything outside them is reserved: where an out already
# carries such a value, leave it untouched rather than writing one of these over
# it.
OUT_MODE_STATES = {
    0: _MODE_STATES_SWITCHED,
    2: _MODE_STATES_PH,
    5: _MODE_STATES_SWITCHED,
    6: _MODE_STATES_SWITCHED,
    7: _MODE_STATES_SWITCHED,
    8: _MODE_STATES_FLOC,
    9: _MODE_STATES_SWITCHED,
    10: _MODE_STATES_SWITCHED,
    11: _MODE_STATES_SWITCHED,
    12: _MODE_STATES_SWITCHED,
    13: _MODE_STATES_SWITCHED,
    14: _MODE_STATES_SWITCHED,
}

# Modes seen on the outs nothing may write yet, kept for reference only: no
# code reads this. The disinfectant was given (0, 3) before the per-output
# tables existed, by a list that also covered the pH corrector and the
# flocculant — and both turned out to differ from it, taking (0, 2, 3) and
# (0, 2). So this is not merely unconfirmed, it has been wrong twice, in both
# directions. Filtration (1) and hybrid chlorine (15) never had a list at all:
# 0/1/3 and 2/3 have merely been *observed* on them, which is not the same as
# being permitted.
OUT_MODES_UNCONFIRMED = {
    3: (0, 3),   # disinfectant
}

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
ICON_OUT_MODE = "mdi:tune"
ICON_INFO = "mdi:identifier"
