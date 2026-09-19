from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    FILTRATION_OUT_INDEX,
    OUT_ICONS,
    OUT_LABELS,
    OUT_STATUS_OFF,
    OUT_STATUS_ON,
    OUT_STATUS_UNKNOWN,
)
from .entity import (IO_TYPE_OUT, klereo_device_info, klereo_io_names,
                     klereo_out_mode_name, klereo_out_mode_states)

import logging
LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    
    LOGGER.info(f"Setting up switches...")
    # Get infos from coordinator
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][config_entry.entry_id]["api"]
    pool_data=coordinator.data;
    outs = pool_data["outs"]
    poolid = pool_data['idSystem']
    device_info = klereo_device_info(pool_data, poolid)
    names = klereo_io_names(pool_data, IO_TYPE_OUT)
    # Add switches
    switches = []
    for out in outs:
        LOGGER.info(f"Adding out for #{poolid}: {out}")
        switches.append(KlereoOut(api,coordinator,out,poolid,device_info,
                                  names.get(out['index'])))
    #add switch enitities
    async_add_entities(switches)


class KlereoOut(CoordinatorEntity, RestoreEntity, SwitchEntity):
    """An out as a switch.

    RestoreEntity is here for the filtration alone: turning it on has to pick a
    speed, and the speed it was last seen running at is not in the payload once
    it has stopped. It is remembered from the polls and published as LastSpeed,
    which is also how it survives a Home Assistant restart.
    """


    def __init__(self, api, coordinator, out, poolid, device_info, klereo_name=None):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._api = api
        # _key backs unique_id and must never change: it is what ties an entity
        # to its history. The displayed name is free to follow Klereo.
        self._key = f"klereo{poolid}out{out['index']}"
        # The user's own name wins; the controller's name for that slot comes
        # next; the raw key is the last resort.
        self._name = klereo_name or OUT_LABELS.get(out['index']) or self._key
        self._attr_icon = OUT_ICONS.get(out['index'])
        self._index = out['index']
        self._poolid = poolid
        # Optimistic state held between a write and the next successful poll.
        self._optimistic_state = None
        # Filtration only: the last speed it was seen running at, so turning it
        # on resumes it rather than dropping the pump to its slowest.
        self._last_speed = None
        self._learn_speed(out)

    @callback
    def _learn_speed(self, out):
        """Remember a running speed. 0 is "stopped", not a speed to resume."""
        if self._index != FILTRATION_OUT_INDEX or out is None:
            return
        status = out.get('status')
        if isinstance(status, int) and status > OUT_STATUS_OFF:
            self._last_speed = status

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self._index != FILTRATION_OUT_INDEX or self._last_speed is not None:
            return
        # Stopped when Home Assistant started, so the payload says nothing about
        # the speed: take it from the state we published before the restart.
        last = await self.async_get_last_state()
        if last is None:
            return
        speed = last.attributes.get('LastSpeed')
        if isinstance(speed, int) and speed > OUT_STATUS_OFF:
            self._last_speed = speed

    @callback
    def _out(self):
        """Return this out in the freshest payload, or None if it vanished."""
        for out in self.coordinator.data['outs']:
            if out['index'] == self._index:
                return out
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        # Fresh data won: drop the optimistic value so external changes
        # (schedule, mobile app, manual override) are reflected again.
        self._optimistic_state = None
        self._learn_speed(self._out())
        super()._handle_coordinator_update()

    @property
    def name(self):
        return self._name

    @property
    def is_on(self):
        if self._optimistic_state is not None:
            return self._optimistic_state
        outs = self.coordinator.data['outs']
        for out in outs:
            if out['index'] == self._index:
                status = out['status']
                LOGGER.debug(f"{self._name}={status}")
                if self._index == FILTRATION_OUT_INDEX:
                    # Speed index 0-7: any speed means the pump runs.
                    return status != OUT_STATUS_OFF
                if status == OUT_STATUS_UNKNOWN:
                    # The controller does not know: report unknown, not off.
                    return None
                return status == OUT_STATUS_ON
        return None

    @property
    def unique_id(self):
        return f"id_{self._key}"

    @property
    def extra_state_attributes(self):
        outs = self.coordinator.data['outs']
        for out in outs:
            if out['index'] == self._index:
                attrs = {
                    'Time': out['updateTime'],
                    'Type': out['type'],
                    'Mode': out['mode'],
                    # Reserved values have no name; the raw number stays above.
                    'ModeName': klereo_out_mode_name(self.coordinator.data,
                                                     self._index, out['mode']),
                    'RealStatus': out['realStatus'],
                }
                if self._index == FILTRATION_OUT_INDEX:
                    # Published so a restart can read it back, and so the speed
                    # the switch would resume is visible rather than implied.
                    attrs['LastSpeed'] = self._last_speed
                return attrs
        return None

    def _mode_and_rule(self):
        """This out's current mode and its rule, or raise if it is read-only."""
        states = klereo_out_mode_states(self.coordinator.data, self._index)
        if states is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="out_read_only",
                translation_placeholders={"name": self._name},
            )
        out = self._out()
        mode = out['mode'] if out else None
        return mode, states.get(mode)

    def _writable_mode(self, state, mode=None, rule=None):
        """The mode to write back, or raise if this write is not allowed.

        Two separate refusals. The out may be read-only altogether; or it may
        sit in a mode that does not take the state being written — Plages
        horaires and Synchronisé accept nothing but "leave the state alone",
        the schedule owning the output — and sending 0/1 there would be a
        combination the firmware does not define.
        """
        if rule is None:
            mode, rule = self._mode_and_rule()
        if rule is None or state not in rule.states:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="out_mode_no_switching",
                translation_placeholders={
                    "name": self._name,
                    # Reserved modes have no name; show the raw number then.
                    "mode": klereo_out_mode_name(self.coordinator.data,
                                                 self._index, mode) or str(mode),
                },
            )
        return mode

    def _on_state(self, rule):
        """What "on" means for this out, in the mode it currently sits in.

        Everywhere but the filtration that is OUT_STATUS_ON. On the filtration
        in Manuel it is a speed, and 1 would be the pump's slowest — so the
        speed it was last seen running at goes instead, and the switch resumes
        the filtration rather than quietly slowing it. Modes whose states are
        not speeds, Maintenance among them, keep plain "on".
        """
        if rule is not None and rule.speed and self._last_speed in rule.states:
            return self._last_speed
        return OUT_STATUS_ON

    async def async_turn_on(self, **kwargs):
        # Carry the out's current mode through, by the codeowner's decision:
        # writing 0 (Manuel) would pull a regulated output out of regulation.
        # The cost is that toggling such an output may look inert, the
        # regulator still owning its state. The mode select changes the mode.
        mode, rule = self._mode_and_rule()
        state = self._on_state(rule)
        self._writable_mode(state, mode, rule)
        await self.hass.async_add_executor_job(
            self._api.set_out, self._index, state, mode
        )
        self._optimistic_state = True
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        mode = self._writable_mode(OUT_STATUS_OFF)
        await self.hass.async_add_executor_job(
            self._api.turn_off_device, self._index, mode
        )
        self._optimistic_state = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
