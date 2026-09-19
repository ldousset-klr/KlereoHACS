from homeassistant.components.number import NumberEntity
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (DOMAIN, FILTRATION_OUT_INDEX, ICON_FILTRATION_SPEED,
                    MAX_PUMP_SPEED, OUT_LABELS)
from .entity import (IO_TYPE_OUT, klereo_device_info, klereo_io_names,
                     klereo_out_mode_name, klereo_out_mode_states,
                     klereo_pump_max_speed)

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

    if not isinstance(pool_data.get('PumpMaxSpeed'), int):
        # Only a missing or malformed value is a reason to guess; 0 is a real
        # answer, meaning the pool drives no pump speed.
        LOGGER.warning("Pool #%s declares no usable PumpMaxSpeed (%r), allowing %s",
                       poolid, pool_data.get('PumpMaxSpeed'), MAX_PUMP_SPEED)
    max_speed = klereo_pump_max_speed(pool_data)
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

    _attr_icon = ICON_FILTRATION_SPEED
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
        base = (klereo_name or OUT_LABELS.get(FILTRATION_OUT_INDEX)
                or f"klereo{poolid}out{FILTRATION_OUT_INDEX}")
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
        pool_data = self.coordinator.data
        states = klereo_out_mode_states(pool_data, FILTRATION_OUT_INDEX)
        if states is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="out_read_only",
                translation_placeholders={"name": self._name},
            )
        mode = None
        for out in pool_data['outs']:
            if out['index'] == FILTRATION_OUT_INDEX:
                mode = out['mode']
                break
        speed = int(value)
        rule = states.get(mode)
        if rule is None or not rule.speed or speed not in rule.states:
            # Only Manuel takes a speed index, which is why rule.speed decides
            # rather than the states alone: in Plages horaires and Régulé the
            # single permitted 2 is the keep sentinel, and Maintenance's 0 and
            # 1 are off and on — writing either from a speed control would send
            # a number the controller reads as something else entirely.
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="out_speed_not_settable",
                translation_placeholders={
                    "name": self._name,
                    "mode": klereo_out_mode_name(pool_data, FILTRATION_OUT_INDEX,
                                                 mode) or str(mode),
                },
            )
        LOGGER.debug("Setting filtration speed of #%s to %s (mode %s)",
                     self._poolid, speed, mode)
        await self.hass.async_add_executor_job(
            self._api.set_out, FILTRATION_OUT_INDEX, speed, mode
        )
        self._optimistic_speed = speed
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
