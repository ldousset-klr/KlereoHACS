from homeassistant.components.select import SelectEntity
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (DOMAIN, ICON_OUT_MODE, OUT_LABELS, OUT_MODE_CHOICES,
                    OUT_MODES, OUT_STATE_KEEP, WRITABLE_OUT_INDEXES)
from .entity import IO_TYPE_OUT, klereo_device_info, klereo_io_names

import logging
LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Expose each writable out's drive mode as a select."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][config_entry.entry_id]["api"]
    pool_data = coordinator.data
    poolid = pool_data['idSystem']
    device_info = klereo_device_info(pool_data, poolid)
    names = klereo_io_names(pool_data, IO_TYPE_OUT)

    selects = []
    for out in pool_data["outs"]:
        index = out['index']
        # A mode is offered only where both are known: that Home Assistant may
        # write this out at all, and which modes the firmware permits on it.
        if index not in WRITABLE_OUT_INDEXES or index not in OUT_MODE_CHOICES:
            continue
        LOGGER.info("Adding mode select for #%s out%s", poolid, index)
        selects.append(KlereoOutMode(api, coordinator, out, poolid,
                                     device_info, names.get(index)))
    async_add_entities(selects)


class KlereoOutMode(CoordinatorEntity, SelectEntity):
    """An out's drive mode, read from `mode` and written as SetOut's newMode.

    The write always carries OUT_STATE_KEEP as newState, so changing the mode
    leaves the output driving whatever the controller had it driving.
    """

    _attr_icon = ICON_OUT_MODE

    def __init__(self, api, coordinator, out, poolid, device_info, klereo_name=None):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._api = api
        self._index = out['index']
        self._poolid = poolid
        # Same rule as the other platforms: unique_id follows _key, never the
        # name, so renaming the out in Klereo cannot orphan the entity.
        self._key = f"klereo{poolid}out{self._index}mode"
        base = (klereo_name or OUT_LABELS.get(self._index)
                or f"klereo{poolid}out{self._index}")
        self._name = f"{base} mode"
        # Offered in the firmware's own order, named from OUT_MODES.
        self._modes = {
            OUT_MODES[mode]: mode
            for mode in OUT_MODE_CHOICES[self._index] if mode in OUT_MODES
        }
        self._attr_options = list(self._modes)
        # Optimistic value held between a write and the next successful poll.
        self._optimistic_mode = None

    @callback
    def _out(self):
        """Return this out in the freshest payload, or None if it vanished."""
        for out in self.coordinator.data['outs']:
            if out['index'] == self._index:
                return out
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        # Fresh data won: drop the optimistic value so a change made elsewhere
        # (mobile app, controller front panel) shows again.
        self._optimistic_mode = None
        super()._handle_coordinator_update()

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return f"id_{self._key}"

    @property
    def current_option(self):
        if self._optimistic_mode is not None:
            return self._optimistic_mode
        out = self._out()
        if out is None:
            return None
        option = OUT_MODES.get(out['mode'])
        if option not in self._attr_options:
            # A reserved or unexpected mode: report unknown rather than a value
            # Home Assistant would reject, and leave it alone.
            LOGGER.debug("#%s out%s carries mode %r, outside %s",
                         self._poolid, self._index, out['mode'],
                         OUT_MODE_CHOICES[self._index])
            return None
        return option

    async def async_select_option(self, option: str) -> None:
        mode = self._modes[option]
        LOGGER.debug("Setting mode of #%s out%s to %s (%s)",
                     self._poolid, self._index, mode, option)
        await self.hass.async_add_executor_job(
            self._api.set_out, self._index, OUT_STATE_KEEP, mode
        )
        self._optimistic_mode = option
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
