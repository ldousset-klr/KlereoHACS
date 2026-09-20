from collections import namedtuple

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
    2: _MODE_NAMES_DOSING,   # pH corrector
    8: _MODE_NAMES_DOSING,   # flocculant
    15: _MODE_NAMES_DOSING,  # hybrid chlorine
}

# What newState may carry, per out index and per mode. The permitted lists come
# from the codeowner, one output family at a time, and each family has its own:
# the same mode number does not take the same states everywhere.
#
# A rule says three things about one mode on one output, and the last two
# cannot be inferred from the first. On the filtration, newState 2 is the
# *keep* sentinel in Plages horaires and Régulé, **speed 2** in Manuel, and not
# permitted at all in Maintenance — one number, three meanings, and only the
# mode tells them apart. So each rule spells out what its states mean:
#
#   states  the newState values the firmware accepts in this mode
#   keep    the one that applies the mode and leaves the output alone, or None
#   speed   True where the states are pump speed indexes rather than on/off
ModeRule = namedtuple("ModeRule", ("states", "keep", "speed"))


def _rule(states, keep=None, speed=False):
    return ModeRule(tuple(states), keep, speed)
_SWITCHED_BOTH = (OUT_STATUS_OFF, OUT_STATUS_ON, OUT_STATE_KEEP)
_MODE_STATES_SWITCHED = {  # lighting (0) and the auxiliaries (5-7, 9-14)
    0: _rule(_SWITCHED_BOTH, OUT_STATE_KEEP),       # Manuel
    1: _rule((OUT_STATE_KEEP,), OUT_STATE_KEEP),    # Plages horaires
    2: _rule(_SWITCHED_BOTH, OUT_STATE_KEEP),       # Minuterie
    4: _rule((OUT_STATE_KEEP,), OUT_STATE_KEEP),    # Synchronisé
    6: _rule(_SWITCHED_BOTH, OUT_STATE_KEEP),       # Maintenance
    8: _rule(_SWITCHED_BOTH, OUT_STATE_KEEP),       # Impulsion
}

# The pH corrector (2). Note Manuel here takes **only** OUT_STATUS_OFF: a dosing
# pump put back under manual control is stopped, it cannot be commanded on and
# it cannot keep its state. So selecting Manuel on this output does stop the
# dosing — the one place where changing a mode also changes what the output is
# doing, and deliberately so.
_MODE_STATES_PH = {
    0: _rule((OUT_STATUS_OFF,)),                    # Manuel — no keep
    2: _rule(_SWITCHED_BOTH, OUT_STATE_KEEP),       # Volume fixe
    3: _rule((OUT_STATE_KEEP,), OUT_STATE_KEEP),    # Régulé
}

# The flocculant (8), the same dosing pump without the regulation: Manuel and
# Volume fixe, and no Régulé at all. Worth noting against the (0, 3) it had
# been given before its real rules arrived — that list was wrong in both
# directions, missing mode 2 and inventing mode 3.
_MODE_STATES_FLOC = {
    0: _rule((OUT_STATUS_OFF,)),                    # Manuel — no keep
    2: _rule(_SWITCHED_BOTH, OUT_STATE_KEEP),       # Volume fixe
}

# Hybrid chlorine (15) takes **one mode and no other**: Volume fixe, which
# doses on a timer exactly as it does on the pH corrector and the flocculant.
# Its select therefore offers a single option — it reports the mode and can
# only re-assert it — but the switch it shares the out with becomes writable,
# which is the point.
_MODE_STATES_HYBRID = {
    2: _rule(_SWITCHED_BOTH, OUT_STATE_KEEP),       # Volume fixe
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
    0: _rule((OUT_STATUS_OFF,)),                    # Manuel — stop only
    3: _rule((OUT_STATE_KEEP,), OUT_STATE_KEEP),    # Régulé
}
_MODE_STATES_HEATER_PAC = {       # HEATER_PAC_KLINK, HEATER_PAC_MODBUS
    0: _rule((OUT_STATUS_OFF,)),                    # Manuel — stop only
    1: _rule((OUT_STATE_KEEP,), OUT_STATE_KEEP),    # Auto
    2: _rule((OUT_STATE_KEEP,), OUT_STATE_KEEP),    # Refroidit
    3: _rule((OUT_STATE_KEEP,), OUT_STATE_KEEP),    # Réchauffe
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
# The disinfectant (3). params.TraitMode says what the pool is treated with,
# and the families barely resemble each other: chlorine and bromine dose on a
# timer, oxygen too, and an electrolyser has no dosing mode at all but four
# regulation modes instead. Mode 2 is "Volume fixe" on chlorine and oxygen,
# "Temps fixe" on bromine and **"Régulé température"** on an electrolyser,
# where it takes the keep sentinel alone rather than on/off.
DISINFECTANT_OUT_INDEX = 3

# params.TraitMode, from the firmware's e_Traitements enum.
TRAIT_NONE = 0
TRAIT_CHLORE = 1
TRAIT_ELECTRO_X = 2
TRAIT_ELECTRO_COR = 3
TRAIT_OXYGEN = 4
TRAIT_BROME = 5
TRAIT_ELECTRO_BSV = 6
TRAIT_IGNORE = 7
TRAIT_ELECTRO_KLR = 8

_MODE_STATES_TRAIT_CHLORE = {
    0: _rule((OUT_STATUS_OFF,)),                    # Manuel — stop only
    2: _rule(_SWITCHED_BOTH, OUT_STATE_KEEP),       # Volume fixe
    3: _rule((OUT_STATE_KEEP,), OUT_STATE_KEEP),    # Régulé
}
_MODE_NAMES_TRAIT_CHLORE = {2: "Volume fixe"}

# The electrolysers, whatever they are driven over. No dosing mode: every mode
# but Manuel hands the cell to a regulator and takes the keep sentinel alone.
# Mode 5 (Choc) exists nowhere else, which is why OUT_MODES does not name it.
_MODE_STATES_TRAIT_ELECTRO = {
    0: _rule((OUT_STATUS_OFF,)),                    # Manuel — stop only
    2: _rule((OUT_STATE_KEEP,), OUT_STATE_KEEP),    # Régulé température
    3: _rule((OUT_STATE_KEEP,), OUT_STATE_KEEP),    # Régulé redox
    4: _rule((OUT_STATE_KEEP,), OUT_STATE_KEEP),    # Synchronisé filtration
    5: _rule((OUT_STATE_KEEP,), OUT_STATE_KEEP),    # Choc
}
_MODE_NAMES_TRAIT_ELECTRO = {
    2: "Régulé température",
    3: "Régulé redox",
    4: "Synchronisé filtration",
    5: "Choc",
}

_MODE_STATES_TRAIT_OXYGEN = {
    0: _rule((OUT_STATUS_OFF,)),                    # Manuel — stop only
    2: _rule(_SWITCHED_BOTH, OUT_STATE_KEEP),       # Volume fixe
    3: _rule((OUT_STATE_KEEP,), OUT_STATE_KEEP),    # Régulé température
}
_MODE_NAMES_TRAIT_OXYGEN = {2: "Volume fixe", 3: "Régulé température"}

_MODE_STATES_TRAIT_BROME = {
    0: _rule((OUT_STATUS_OFF,)),                    # Manuel — stop only
    2: _rule(_SWITCHED_BOTH, OUT_STATE_KEEP),       # Temps fixe
    3: _rule((OUT_STATE_KEEP,), OUT_STATE_KEEP),    # Régulé
    4: _rule((OUT_STATE_KEEP,), OUT_STATE_KEEP),    # Synchronisé filtration
}
_MODE_NAMES_TRAIT_BROME = {2: "Temps fixe", 4: "Synchronisé filtration"}

_ELECTRO = (_MODE_STATES_TRAIT_ELECTRO, _MODE_NAMES_TRAIT_ELECTRO)

# TraitMode -> (states by mode, name overrides). TRAIT_NONE and TRAIT_IGNORE
# are absent on purpose, as is any value outside the enum: nothing is written
# to a disinfectant whose treatment is not established.
TRAIT_VARIANTS = {
    TRAIT_CHLORE:      (_MODE_STATES_TRAIT_CHLORE, _MODE_NAMES_TRAIT_CHLORE),
    TRAIT_ELECTRO_X:   _ELECTRO,
    TRAIT_ELECTRO_COR: _ELECTRO,
    TRAIT_ELECTRO_BSV: _ELECTRO,
    TRAIT_ELECTRO_KLR: _ELECTRO,
    TRAIT_OXYGEN:      (_MODE_STATES_TRAIT_OXYGEN, _MODE_NAMES_TRAIT_OXYGEN),
    TRAIT_BROME:       (_MODE_STATES_TRAIT_BROME, _MODE_NAMES_TRAIT_BROME),
}

# The filtration (1), the second output whose rules come from the payload: its
# Manuel takes a *speed index*, 0 (stopped) to the pool's own PumpMaxSpeed, so
# the permitted list is as long as the pump has speeds.
#
# This is where the keep sentinel has to be stated rather than inferred. In
# Plages horaires and Régulé, newState 2 means "leave it as it is"; in Manuel
# the very same 2 means **speed 2**, and in Maintenance it is not permitted at
# all. Preferring 2 blindly, as every other output allows, would start the pump
# on a mode change.
def filtration_mode_states(max_speed):
    """The filtration's rules on a pool whose pump has `max_speed` speeds."""
    return {
        0: _rule(range(0, max_speed + 1), speed=True),  # Manuel — a speed
        1: _rule((OUT_STATE_KEEP,), OUT_STATE_KEEP),    # Plages horaires
        3: _rule((OUT_STATE_KEEP,), OUT_STATE_KEEP),    # Régulé
        6: _rule((OUT_STATUS_OFF, OUT_STATUS_ON)),      # Maintenance — on/off
    }


# The outs whose rules are not a property of their index: the params key that
# decides, and the variants it selects. entity.klereo_out_mode_states() reads
# this, so a third such output is a line here rather than another special case.
PAYLOAD_VARIANTS = {
    HEATER_OUT_INDEX: ("HeaterMode", HEATER_VARIANTS),
    DISINFECTANT_OUT_INDEX: ("TraitMode", TRAIT_VARIANTS),
}

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
    15: _MODE_STATES_HYBRID,
}

# Every output now carries its rules. What a pool actually exposes still
# depends on it: the heating and the disinfectant need their params key to name
# a kind, and an out absent from the payload has no entities at all.

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
