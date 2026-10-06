from collections import namedtuple

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (CHLORINE_FLOW_PARAM, DOMAIN, FLOCCULANT_OUT_INDEX,
                    HYBRID_CHLORINE_OUT_INDEX, HYBRID_CHLORINE_TIME_KEY,
                    ICON_INFO, ICON_WATER_VOLUME, ML_PER_FLOW_UNIT,
                    OUT_TOTAL_TIME_KEY, PH_FLOW_PARAM, PROBE_ICONS,
                    PROBE_INVALID, PROBE_LABELS, PROBE_TYPES,
                    PROBE_TYPE_DEFAULT, PUMP_DOSED_TREATMENTS,
                    SECONDS_PER_HOUR)
from .entity import IO_TYPE_PROBE, klereo_device_info, klereo_io_names

import logging
LOGGER = logging.getLogger(__name__)

# Pieces of the pool's identity and setup that DeviceInfo has no field for.
# They are published as diagnostic sensors, which is how Home Assistant
# surfaces extra device metadata on the device page.
#
# All are read-only: they describe how the pool is registered and built, not
# anything Home Assistant may command, and none has a SetOut equivalent.
#
# `enabled` is the entity registry's enabled-by-default flag. False still
# creates the entity, so it is one click away on the device page, but it
# records no history until someone asks for it. Note this only applies when an
# entity is first registered: flipping it later leaves existing installs alone.
InfoSensor = namedtuple(
    "InfoSensor",
    ("key", "label", "getter", "icon", "unit", "enabled",
     "device_class", "state_class"),
)
InfoSensor.__new__.__defaults__ = (ICON_INFO, None, True, None, None)


def _params_hours(key):
    """Read a params counter given in seconds and publish it in hours.

    The controller counts seconds, which no one reads: a pool that has run
    since spring reports something like 3283200. Hours are what a pool owner
    actually thinks in, and what a graph of running time should be drawn
    against, so the conversion happens here rather than being left to a
    template in every dashboard.

    A missing or non-numeric counter yields None, which creates no entity at
    all — the same rule the other rows follow.
    """
    def getter(data):
        seconds = (data.get("params") or {}).get(key)
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
            return None
        return round(seconds / 3600, 1)
    return getter


def _seconds_param(key):
    """Running seconds from a `params` counter — the pH corrector's and the
    disinfectant's."""
    return lambda data: (data.get("params") or {}).get(key)


def _seconds_out(index):
    """Running seconds from an out's own entry — the flocculant's, which has no
    `params` counter of its own."""
    def source(data):
        for out in data.get("outs") or ():
            if out.get("index") == index:
                return out.get(OUT_TOTAL_TIME_KEY)
        return None
    return source


def _seconds_extra(key):
    """Running seconds from `ExtraParams` — hybrid chlorine's, which lives
    neither in `params` nor on the out. Whole pools carry no `ExtraParams` at
    all, which simply yields no sensor."""
    return lambda data: (data.get("ExtraParams") or {}).get(key)


def _pump_dosed_treatment(data):
    """Whether out 3 drives a dosing pump, from `params.TraitMode`.

    Only chlorine and oxygen do. Bromine feeds a brominator and an electrolyser
    runs a cell, so on those the counter is running time and nothing else —
    multiplying it by a pump's flow would state a volume of product that never
    went in. A TraitMode that is absent, reserved or outside the enum reads the
    same way: the kind is not established, so no volume is claimed.
    """
    return (data.get("params") or {}).get("TraitMode") in PUMP_DOSED_TREATMENTS


def _params_ml(seconds_source, flow_key, gate=None):
    """Turn a dosing pump's running time into the volume it actually dosed.

    The controller counts the pump's running seconds and, separately, declares
    that pump's flow rate in **tenths of a litre per hour** — so a 1.5 L/h
    peristaltic pump reports 15. Multiplying the two is the only way to answer
    the question a pool owner actually has: how much product went in. Hours of
    pump time are a proxy nobody can act on, since two pools with the same
    hours and different pumps have dosed different amounts.

    `seconds_source` reads the counter, which lives in a different place on
    each out — see the three helpers above. `gate`, where a row has one, says
    whether that out drives a pump at all on this pool.

    Four things yield None, and therefore no entity at all, the same rule the
    other rows follow: a gate that answers no, a missing or non-numeric
    counter, a missing or non-numeric flow, and a flow of zero or less. That
    last one is the normal case rather than a defensive check — a pool whose
    controller declares no pump has nothing to multiply, and a volume sensor
    pinned at 0 mL forever would be noise rather than an answer.
    """
    def getter(data):
        if gate is not None and not gate(data):
            return None
        seconds = seconds_source(data)
        flow = (data.get("params") or {}).get(flow_key)
        for value in (seconds, flow):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return None
        if flow <= 0:
            # No dosing pump on this output: see above.
            return None
        return round(seconds * flow * ML_PER_FLOW_UNIT / SECONDS_PER_HOUR)
    return getter


def _dosed(key, label, seconds_source, flow_key, gate=None):
    """A cumulative dosed volume, in millilitres.

    Same shape as _runtime and for the same reasons: total_increasing absorbs
    a counter reset without charting a negative spike, and the device_class
    supplies a better icon than any we would pick. Sub-millilitre precision
    would be inventing accuracy a peristaltic pump does not have, so the value
    is rounded to whole millilitres.
    """
    return InfoSensor(key, label, _params_ml(seconds_source, flow_key, gate),
                      icon=None, unit="mL", device_class="volume",
                      state_class="total_increasing")


def _runtime(key, label, params_key):
    """A cumulative running-time counter, seconds in the payload, hours here.

    total_increasing rather than total: the controller only ever counts up,
    and that class also absorbs a reset — a pod swap, a counter cleared on the
    front panel — without charting a negative spike. No icon, the device_class
    supplying a better one. Enabled, unlike the water volume: these move, and
    their history is the point.
    """
    return InfoSensor(key, label, _params_hours(params_key),
                      icon=None, unit="h", device_class="duration",
                      state_class="total_increasing")


INFO_SENSORS = (
    InfoSensor("pin", "PIN",
               lambda data: (data.get("register") or {}).get("pin")),
    InfoSensor("device", "Device",
               lambda data: data.get("device")),
    # A pool's volume is a fixed property of the installation: useful to have
    # to hand, not worth a recorder row every poll, so it ships disabled.
    InfoSensor("volume", "Water volume",
               lambda data: (data.get("params") or {}).get("VolumeEau"),
               icon=ICON_WATER_VOLUME, unit="m³", enabled=False),

    # One counter per driven output, the four whose totalTime the captured
    # payloads showed these params keys tracking: outs 1, 2, 3 and 4.
    #
    # The labels follow the output's role rather than the key's wording.
    # ElectroChlore_ in particular counts out 3 whatever the pool is treated
    # with — chlorine, bromine, oxygen or an electrolyser — so naming the
    # sensor after electro-chlorination would be wrong on most pools.
    #
    # A key that turns out to be spelled differently on some firmware costs
    # nothing: the getter returns None and no entity is created.
    _runtime("filtrationtime", "Filtration runtime", "Filtration_TotalTime"),
    _runtime("phtime", "pH corrector runtime", "PHMinus_TotalTime"),
    _runtime("disinfectanttime", "Disinfectant runtime", "ElectroChlore_TotalTime"),
    _runtime("heatingtime", "Heating runtime", "Chauff_TotalTime"),

    # What each dosing pump has actually put in the water, rather than how long
    # it ran. The counters above stay alongside, being the raw figure and
    # already carrying history.
    #
    # One flow per pump, not per output: PHMinus_Debit drives the pH corrector,
    # and Chlore_Debit the other three — the disinfectant, the flocculant and
    # hybrid chlorine all meter from it.
    #
    # The counters, though, are in three different places. Only the pH
    # corrector and the disinfectant have a params counter; the flocculant's
    # running time is on its own out, and hybrid chlorine's is in ExtraParams.
    _dosed("phvolume", "pH corrector volume",
           _seconds_param("PHMinus_TotalTime"), PH_FLOW_PARAM),
    # The only row with a gate: out 3 drives a pump on a chlorine or oxygen
    # pool and nothing of the sort on a bromine or electrolyser one, where the
    # running time in hours above remains the whole answer.
    _dosed("disinfectantvolume", "Disinfectant volume",
           _seconds_param("ElectroChlore_TotalTime"), CHLORINE_FLOW_PARAM,
           gate=_pump_dosed_treatment),
    _dosed("flocculantvolume", "Flocculant volume",
           _seconds_out(FLOCCULANT_OUT_INDEX), CHLORINE_FLOW_PARAM),
    _dosed("hybridchlorinevolume", "Hybrid chlorine volume",
           _seconds_extra(HYBRID_CHLORINE_TIME_KEY), CHLORINE_FLOW_PARAM),
)

async def async_setup_entry(hass, config_entry, async_add_entities):

    LOGGER.info(f"Setting up sensors...")
    # Get infos from coordinator
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    pool_data=coordinator.data;
    probes = pool_data["probes"]
    poolid = pool_data['idSystem']
    device_info = klereo_device_info(pool_data, poolid)
    names = klereo_io_names(pool_data, IO_TYPE_PROBE)
    # Add sensors
    sensors = []
    for probe in probes:
        LOGGER.info(f"Adding sensor for #{poolid}: {probe}")
        sensors.append(KlereoSensor(coordinator,probe,poolid,device_info,
                                    names.get(probe['index'])))
    # Identity values, only when the payload carries them
    for info in INFO_SENSORS:
        if info.getter(pool_data) is None:
            LOGGER.debug("No %s on pool #%s, no diagnostic sensor",
                         info.key, poolid)
            continue
        sensors.append(KlereoInfoSensor(coordinator, poolid, device_info, info))
    #add sensor enitities
    async_add_entities(sensors)


class KlereoSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True   # "<pool> <name>": see klereo_device_info()

    def __init__(self, coordinator, probe, poolid, device_info, klereo_name=None):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        # _key backs unique_id and must never change: it is what ties an entity
        # to its history. The displayed name is free to follow Klereo.
        self._key = f"klereo{poolid}probe{probe['index']}"
        # The user's own name wins; the controller's name for that slot comes
        # next; the raw key is the last resort.
        self._name = klereo_name or PROBE_LABELS.get(probe['index']) or self._key
        self._index = probe['index']
        self._type = probe['type']
        self._poolid = poolid
        if self._type not in PROBE_TYPES:
            # Outside e_TypeCapteurs: the firmware gained a type this table
            # predates. GENERIC and UNKNOWN are expected and do not warn.
            LOGGER.warning(
                "Klereo probe type %s on probe %s of pool #%s is outside the known "
                "sensor types; publishing it without a unit",
                self._type, self._index, poolid,
            )
        self._label, device_class, unit, state_class = PROBE_TYPES.get(
            self._type, PROBE_TYPE_DEFAULT
        )
        self._attr_device_class = device_class
        # Only where there is no device_class: HA's own icon is better informed.
        if device_class is None:
            self._attr_icon = PROBE_ICONS.get(self._type)
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class

    def _probe(self):
        """Return this probe in the freshest payload, or None if it disappeared."""
        for probe in self.coordinator.data['probes']:
            if probe['index'] == self._index:
                return probe
        return None

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return f"id_{self._key}"

    @property
    def native_value(self):
        probe = self._probe()
        if probe is None:
            return None
        try:
            value = float(probe['filteredValue'])
        except (KeyError, TypeError, ValueError):
            LOGGER.debug(f"{self._name} has no usable value: {probe.get('filteredValue')!r}")
            return None
        if value <= PROBE_INVALID:
            # Absent or unreadable probe: report unknown rather than -1000.
            LOGGER.debug(f"{self._name} reports no measurement ({value})")
            return None
        LOGGER.debug(f"{self._name}={value}")
        return value

    @property
    def extra_state_attributes(self):
        probe = self._probe()
        if probe is None:
            return None
        # filteredValue is what the state reports, and it freezes when the
        # filtration stops — a water reading without circulation is meaningless.
        # It can then sit hours behind directValue, so both are exposed: compare
        # Time and DirectTime to tell a settled reading from a stale one.
        return {
            'Time': probe['filteredTime'],
            'Direct': probe.get('directValue'),
            'DirectTime': probe.get('directTime'),
            'Type': int(probe['type']),
            'TypeName': self._label
        }


class KlereoInfoSensor(CoordinatorEntity, SensorEntity):
    """A read-only piece of the pool's identity or setup, under Diagnostic.

    Everything that varies between them lives in the InfoSensor row rather
    than in subclasses: label, getter, icon, unit, device and state class, and
    whether the entity is enabled when first registered.
    """

    _attr_has_entity_name = True   # "<pool> <name>": see klereo_device_info()
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, poolid, device_info, info):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        # Same rule as everywhere else: unique_id follows the key, not the name.
        self._key = f"klereo{poolid}{info.key}"
        self._name = info.label
        self._getter = info.getter
        self._attr_device_class = info.device_class
        # Only where there is no device_class: HA's own icon is better
        # informed, and overriding it loses the state-aware variants. Same
        # rule as KlereoSensor.
        if info.device_class is None:
            self._attr_icon = info.icon
        self._attr_native_unit_of_measurement = info.unit
        self._attr_state_class = info.state_class
        self._attr_entity_registry_enabled_default = info.enabled

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return f"id_{self._key}"

    @property
    def native_value(self):
        return self._getter(self.coordinator.data)
