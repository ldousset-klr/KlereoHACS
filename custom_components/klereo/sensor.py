from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (DOMAIN, ICON_INFO, PROBE_ICONS, PROBE_INVALID, PROBE_LABELS,
                    PROBE_TYPES, PROBE_TYPE_DEFAULT)
from .entity import IO_TYPE_PROBE, klereo_device_info, klereo_io_names

import logging
LOGGER = logging.getLogger(__name__)

# Pieces of the pool's identity that DeviceInfo has no field for. They are
# published as diagnostic sensors, which is how Home Assistant surfaces extra
# device metadata on the device page.
INFO_SENSORS = (
    ("pin", "PIN", lambda data: (data.get("register") or {}).get("pin")),
    ("device", "Device", lambda data: data.get("device")),
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
    for key, label, getter in INFO_SENSORS:
        if getter(pool_data) is None:
            LOGGER.debug(f"No {key} on pool #{poolid}, no diagnostic sensor")
            continue
        sensors.append(KlereoInfoSensor(coordinator, poolid, device_info,
                                        key, label, getter))
    #add sensor enitities
    async_add_entities(sensors)


class KlereoSensor(CoordinatorEntity, SensorEntity):

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
    """A read-only piece of the pool's identity, shown under Diagnostic."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = ICON_INFO

    def __init__(self, coordinator, poolid, device_info, key, label, getter):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        # Same rule as everywhere else: unique_id follows the key, not the name.
        self._key = f"klereo{poolid}{key}"
        self._name = label
        self._getter = getter

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return f"id_{self._key}"

    @property
    def native_value(self):
        return self._getter(self.coordinator.data)
