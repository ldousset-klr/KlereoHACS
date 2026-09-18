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

# probe['type'] -> (device_class, unit, state_class)
#
# Established from a live GetPoolDetails capture, by cross-checking each probe
# against the params block that points at it:
#   1  air temperature   seuilMin/Max mirror params AirMin/AirMax (-5..50)
#   3  pH                seuilMin/Max mirror pHMin/pHMax (6.6..8), ConsignePH 7.3
#   4  redox / ORP (mV)  seuilMin/Max mirror OrpMin/OrpMax (470..850)
#   5  water temperature params EauCapteur holds this probe's index; 0..40 = EauMin/Max
#
# Types 10 and 12 also occur but nothing in the payload pins down their unit, so
# they are published as plain numbers rather than mislabelled. Extend the table
# once a capture identifies them.
#
# device_class and state_class are plain strings on purpose: the SensorDeviceClass
# enum members vary by Home Assistant version, and an unknown member would raise
# at import time on the older versions hacs.json still allows.
PROBE_TYPES = {
    1: ("temperature", "°C", "measurement"),
    3: ("ph", None, "measurement"),
    4: (None, "mV", "measurement"),
    5: ("temperature", "°C", "measurement"),
}
PROBE_TYPE_DEFAULT = (None, None, "measurement")
