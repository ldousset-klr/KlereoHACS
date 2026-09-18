from homeassistant.components.number import NumberEntity
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, FILTRATION_OUT_INDEX, MAX_PUMP_SPEED
from .entity import IO_TYPE_OUT, klereo_device_info, klereo_io_names

import logging
LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Expose the filtration speed, on pools whose pump has more than one."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][config_entry.entry_id]["api"]
    pool_data = coordinator.data
    poolid = pool_data['idSystem']

    outs = pool_data["outs"]
    if not any(out['index'] == FILTRATION_OUT_INDEX for out in outs):
        LOGGER.info("Pool #%s has no out %s, no speed entity",
                    poolid, FILTRATION_OUT_INDEX)
        return

    max_speed = pool_data.get('PumpMaxSpeed')
    if not isinstance(max_speed, int):
        # Only a missing or malformed value is a reason to guess; 0 is a real
        # answer, meaning the pool drives no pump speed.
        LOGGER.warning("Pool #%s declares no usable PumpMaxSpeed (%r), allowing %s",
                       poolid, max_speed, MAX_PUMP_SPEED)
        max_speed = MAX_PUMP_SPEED
    max_speed = min(max_speed, MAX_PUMP_SPEED)
    if max_speed < 2:
        # 0 = no speed control, 1 = single speed: the switch says it all.
        LOGGER.info("Pool #%s drives no pump speed (PumpMaxSpeed=%s), no speed entity",
                    poolid, max_speed)
        return

    LOGGER.info("Adding filtration speed 0-%s for #%s", max_speed, poolid)
    device_info = klereo_device_info(pool_data, poolid)
    klereo_name = klereo_io_names(pool_data, IO_TYPE_OUT).get(FILTRATION_OUT_INDEX)
    async_add_entities(
        [KlereoFiltrationSpeed(api, coordinator, poolid, device_info,
                               max_speed, klereo_name)]
    )


class KlereoFiltrationSpeed(CoordinatorEntity, NumberEntity):
    """The filtration out's status read and written as a speed index."""

    _attr_native_min_value = 0
    _attr_native_step = 1

    def __init__(self, api, coordinator, poolid, device_info, max_speed, klereo_name):
        super().__init__(coordinator)
        self._api = api
        self._poolid = poolid
        self._attr_device_info = device_info
        self._attr_native_max_value = max_speed
        # Same rule as the other platforms: unique_id follows _key, not the name.
        self._key = f"klereo{poolid}out{FILTRATION_OUT_INDEX}speed"
        base = klereo_name or f"klereo{poolid}out{FILTRATION_OUT_INDEX}"
        self._name = f"{base} speed"
        self._optimistic_speed = None

    @callback
    def _handle_coordinator_update(self) -> None:
        self._optimistic_speed = None
        super()._handle_coordinator_update()

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return f"id_{self._key}"

    @property
    def native_value(self):
        if self._optimistic_speed is not None:
            return self._optimistic_speed
        for out in self.coordinator.data['outs']:
            if out['index'] == FILTRATION_OUT_INDEX:
                return out['status']
        return None

    async def async_set_native_value(self, value: float) -> None:
        speed = int(value)
        LOGGER.debug(f"Setting filtration speed of #{self._poolid} to {speed}")
        await self.hass.async_add_executor_job(
            self._api.set_out, FILTRATION_OUT_INDEX, speed
        )
        self._optimistic_speed = speed
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
