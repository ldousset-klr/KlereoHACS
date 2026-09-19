from homeassistant.components.select import SelectEntity
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ICON_OUT_MODE, OUT_LABELS
from .entity import (IO_TYPE_OUT, klereo_device_info, klereo_io_names,
                     klereo_out_mode_name, klereo_out_mode_states)

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
        # A mode is offered exactly where the out's permitted states are known:
        # that is both what makes it writable and what says which modes to list.
        if klereo_out_mode_states(pool_data, index) is None:
            continue
        LOGGER.info("Adding mode select for #%s out%s", poolid, index)
        selects.append(KlereoOutMode(api, coordinator, out, poolid,
                                     device_info, names.get(index)))
    async_add_entities(selects)


class KlereoOutMode(CoordinatorEntity, SelectEntity):
    """An out's drive mode, read from `mode` and written as SetOut's newMode.

    The write carries OUT_STATE_KEEP as newState wherever the target mode
    accepts it, so changing the mode leaves the output driving whatever the
    controller had it driving. Where it does not — the pH corrector's Manuel,
    which takes nothing but "off" — the mode change necessarily stops the
    output, which is the firmware's own rule and not this entity's choice.
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
        # Offered in the firmware's own order, under this out's own wording.
        # Resolved once here: the heating output's list depends on the payload,
        # and HeaterMode is a rewiring, not something that changes under a poll.
        pool_data = coordinator.data
        self._states = klereo_out_mode_states(pool_data, self._index)
        self._modes = {
            klereo_out_mode_name(pool_data, self._index, mode): mode
            for mode in self._states
            if klereo_out_mode_name(pool_data, self._index, mode) is not None
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
        option = klereo_out_mode_name(self.coordinator.data, self._index,
                                      out['mode'])
        if option not in self._attr_options:
            # A reserved or unexpected mode: report unknown rather than a value
            # Home Assistant would reject, and leave it alone.
            LOGGER.debug("#%s out%s carries mode %r, outside %s",
                         self._poolid, self._index, out['mode'],
                         tuple(self._states))
            return None
        return option

    def _state_for(self, mode):
        """The newState to send alongside a change to `mode`.

        Leaving the output's state alone is what a mode change should do, and
        `rule.keep` says how — never the bare presence of a 2 in the permitted
        list, which on the filtration's Manuel means speed 2 and would start
        the pump.

        Where the mode has no keep value, three cases in order. It may permit
        exactly one state, as the dosing pumps' and the heating's Manuel do,
        stopping the output: that is the only thing the firmware takes, so it
        is what goes. It may permit several, as the filtration's Manuel does —
        then the out's current status already *is* the state to hold, and it
        goes back unchanged. Otherwise there is nothing to send that would not
        be a guess, so refuse.
        """
        rule = self._states[mode]
        if rule.keep is not None:
            return rule.keep
        if len(rule.states) == 1:
            return rule.states[0]
        out = self._out()
        status = out['status'] if out else None
        if status in rule.states:
            return status
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="out_mode_ambiguous_state",
            translation_placeholders={
                "name": self._name,
                "mode": klereo_out_mode_name(self.coordinator.data,
                                             self._index, mode) or str(mode),
            },
        )

    async def async_select_option(self, option: str) -> None:
        mode = self._modes[option]
        state = self._state_for(mode)
        LOGGER.debug("Setting mode of #%s out%s to %s (%s), state=%s",
                     self._poolid, self._index, mode, option, state)
        await self.hass.async_add_executor_job(
            self._api.set_out, self._index, state, mode
        )
        self._optimistic_mode = option
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
