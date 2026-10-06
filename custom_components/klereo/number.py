from homeassistant.components.number import NumberEntity
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (DOMAIN, FILTRATION_OUT_INDEX, ICON_FILTRATION_SPEED,
                    MAX_PUMP_SPEED, OUT_LABELS, SETPOINT_MAX, SETPOINT_MIN,
                    SETPOINT_PARAM, SETPOINT_STEP)
from .entity import (IO_TYPE_OUT, KlereoCommandMixin, klereo_access,
                     klereo_device_info,
                     klereo_io_names, klereo_may_command, klereo_out_mode_name,
                     klereo_out_mode_states, klereo_out_refusal,
                     klereo_pump_max_speed)

import logging
LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Expose the filtration speed and the water setpoint, where the pool has them."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][config_entry.entry_id]["api"]
    pool_data = coordinator.data
    poolid = pool_data['idSystem']
    device_info = klereo_device_info(pool_data, poolid)

    numbers = []

    speed = _filtration_speed(api, coordinator, pool_data, poolid, device_info)
    if speed is not None:
        numbers.append(speed)

    # The water temperature setpoint, params.ConsigneEau. Absent on a pool with
    # no heating, and on anything that is not a pool at all.
    setpoint = (pool_data.get("params") or {}).get(SETPOINT_PARAM)
    if isinstance(setpoint, (int, float)) and not isinstance(setpoint, bool):
        LOGGER.info("Adding water setpoint for #%s (currently %s)", poolid, setpoint)
        numbers.append(KlereoWaterSetpoint(api, coordinator, poolid, device_info))
    else:
        LOGGER.debug("Pool #%s declares no ConsigneEau (%r), no setpoint entity",
                     poolid, setpoint)

    async_add_entities(numbers)


def _filtration_speed(api, coordinator, pool_data, poolid, device_info):
    """The speed entity, or None on a pool whose pump has at most one speed."""
    if not any(out['index'] == FILTRATION_OUT_INDEX for out in pool_data["outs"]):
        LOGGER.info("Pool #%s has no out %s, no speed entity",
                    poolid, FILTRATION_OUT_INDEX)
        return None

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
        return None

    LOGGER.info("Adding filtration speed 0-%s for #%s", max_speed, poolid)
    klereo_name = klereo_io_names(pool_data, IO_TYPE_OUT).get(FILTRATION_OUT_INDEX)
    return KlereoFiltrationSpeed(api, coordinator, poolid, device_info,
                                 max_speed, klereo_name)


class KlereoFiltrationSpeed(KlereoCommandMixin, CoordinatorEntity, NumberEntity):
    """The filtration out's status read and written as a speed index."""

    _attr_has_entity_name = True   # "<pool> <name>": see klereo_device_info()
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

    def _clear_optimistic(self):
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
        refusal = klereo_out_refusal(pool_data, FILTRATION_OUT_INDEX)
        if refusal is not None:
            # The speed writes out 1, which is not privileged, so in practice
            # this is the level-10 gate.
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key=refusal,
                translation_placeholders={
                    "name": self._name,
                    "access": str(klereo_access(pool_data)),
                },
            )
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
        reply = await self.hass.async_add_executor_job(
            self._api.set_out, FILTRATION_OUT_INDEX, speed, mode
        )
        self._optimistic_speed = speed
        self.async_write_ha_state()
        self._follow_command(reply, f"{self._name} = {speed}")


class KlereoWaterSetpoint(KlereoCommandMixin, CoordinatorEntity, NumberEntity):
    """params.ConsigneEau — the water temperature the controller aims for.

    A `number` from the start, not a sensor, even though it refuses to be set
    for now: a setpoint is something you adjust, and publishing it as a sensor
    first would mean changing the entity's domain later, orphaning its history.
    The filtration speed took the same route and it worked.

    Writing goes through SetParam, which **queues** the change for the pod
    rather than applying it: the payload keeps reporting the old value until
    the pod has fetched the command. The optimistic value bridges that gap the
    way KlereoOut does, and is dropped on the next poll, so a setpoint that has
    not reached the pod yet may show the old value again for a moment.
    """

    _attr_has_entity_name = True   # "<pool> <name>": see klereo_device_info()
    _attr_device_class = "temperature"
    _attr_native_unit_of_measurement = "°C"
    _attr_native_min_value = SETPOINT_MIN
    _attr_native_max_value = SETPOINT_MAX
    _attr_native_step = SETPOINT_STEP

    def __init__(self, api, coordinator, poolid, device_info):
        super().__init__(coordinator)
        self._api = api
        self._poolid = poolid
        self._attr_device_info = device_info
        # Named for the role, as everything else here is, and keyed on it too:
        # unique_id follows _key and must outlive any relabelling.
        self._key = f"klereo{poolid}watersetpoint"
        self._name = "Water setpoint"
        # Held between a write and the next successful poll.
        self._optimistic_value = None

    def _clear_optimistic(self):
        self._optimistic_value = None

    @callback
    def _handle_coordinator_update(self) -> None:
        # Fresh data won, whether or not it yet carries our value: a change
        # made on the front panel or in the mobile app must show through.
        self._optimistic_value = None
        super()._handle_coordinator_update()

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return f"id_{self._key}"

    @property
    def native_value(self):
        # Published exactly as the payload gives it, and written back on the
        # same scale, so the round trip holds whatever units the controller's
        # parameter table is on.
        if self._optimistic_value is not None:
            return self._optimistic_value
        return (self.coordinator.data.get("params") or {}).get(SETPOINT_PARAM)

    async def async_set_native_value(self, value: float) -> None:
        pool_data = self.coordinator.data
        if not klereo_may_command(pool_data):
            # The server would refuse this, and says so in French with no hint
            # that the account is the reason. Say it here instead.
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="account_read_only",
                translation_placeholders={
                    "name": self._name,
                    "access": str(klereo_access(pool_data)),
                },
            )
        # The controller keeps a tenth of a degree, so round before sending and
        # hold the rounded value: a service call can pass any float, bypassing
        # the entity's step, and showing 26.35 while the pool holds 26.4 would
        # be a discrepancy this entity invented.
        value = round(value, 1)
        LOGGER.debug("Setting water setpoint of #%s to %s", self._poolid, value)
        reply = await self.hass.async_add_executor_job(
            self._api.set_param, SETPOINT_PARAM, value
        )
        self._optimistic_value = value
        self.async_write_ha_state()
        self._follow_command(reply, f"{self._name} = {value}")
