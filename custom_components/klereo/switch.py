from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    FILTRATION_OUT_INDEX,
    OUT_ICONS,
    OUT_LABELS,
    OUT_MODES,
    WRITABLE_OUT_INDEXES,
    OUT_STATUS_OFF,
    OUT_STATUS_ON,
    OUT_STATUS_UNKNOWN,
)
from .entity import IO_TYPE_OUT, klereo_device_info, klereo_io_names

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


class KlereoOut(CoordinatorEntity, SwitchEntity):

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
                return {
                    'Time': out['updateTime'],
                    'Type': out['type'],
                    'Mode': out['mode'],
                    # Reserved values have no name; the raw number stays above.
                    'ModeName': OUT_MODES.get(out['mode']),
                    'RealStatus': out['realStatus'],
                }
        return None

    def _writable_mode(self):
        """The mode to write back, or raise if this out is not writable."""
        if self._index not in WRITABLE_OUT_INDEXES:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="out_read_only",
                translation_placeholders={"name": self._name},
            )
        out = self._out()
        return out['mode'] if out else None

    async def async_turn_on(self, **kwargs):
        # Carry the out's current mode through, by the codeowner's decision:
        # writing 0 (Manuel) would pull a regulated output out of regulation.
        # The cost is that toggling such an output may look inert, the
        # regulator still owning its state.
        mode = self._writable_mode()
        await self.hass.async_add_executor_job(
            self._api.turn_on_device, self._index, mode
        )
        self._optimistic_state = True
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        mode = self._writable_mode()
        await self.hass.async_add_executor_job(
            self._api.turn_off_device, self._index, mode
        )
        self._optimistic_state = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
