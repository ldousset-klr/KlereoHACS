from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

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
    # Add switches
    switches = []
    for out in outs:
        LOGGER.info(f"Adding out for #{poolid}: {out}")
        switches.append(KlereoOut(api,coordinator,out,poolid))
    #add switch enitities
    async_add_entities(switches, update_before_add=True)


class KlereoOut(CoordinatorEntity, SwitchEntity):

    def __init__(self, api, coordinator, out, poolid):
        super().__init__(coordinator)
        self._api = api
        self._name = f"klereo{poolid}out{out['index']}"
        self._index = out['index']
        self._type = out['type']
        self._mode = out['mode']
        self._state = out['status']
        self._realstate = out['realStatus']
        self._poolid = poolid

    @property
    def name(self):
        return self._name

    @property
    def is_on(self):
        outs = self.coordinator.data['outs']
        for out in outs:
            if out['index'] == self._index:
                LOGGER.debug(f"{self._name}={out['status']}, state={self._state}")
                if self._state == "on":
                    return True
                if self._state == "off":
                    return False
                return out['status']==1
        return None

    @property
    def mode(self):
        return self._mode


    @property
    def unique_id(self):
        return f"id_{self._name}"

    @property
    def extra_state_attributes(self):
        outs = self.coordinator.data['outs']
        for out in outs:
            if out['index'] == self._index:
                return {
                    'Time': out['updateTime'],
                    'Type': out['type'],
                    'Mode': out['mode'],
                    'RealStatus': out['realStatus'],
                }
        return None

    async def async_turn_on(self, **kwargs):
        await self.hass.async_add_executor_job(self._api.turn_on_device, self._index)
        LOGGER.debug(f"update HA state {self._state} (before)")
        LOGGER.debug(f"Todo: update coordinator data !")
        self._state = "on"
        self.async_write_ha_state()
        LOGGER.debug(f"HA state={self._state}")

    async def async_turn_off(self, **kwargs):
        await self.hass.async_add_executor_job(self._api.turn_off_device, self._index)
        LOGGER.debug(f"update HA state {self._state} (before)")
        LOGGER.debug(f"Todo: update coordinator data !")
        self._state = "off"
        self.async_write_ha_state()
        LOGGER.debug(f"HA state={self._state}")

    async def async_set_mode(self, mode):
        #if mode not in ["manual", "timer", "schedule"]:
        #    raise ValueError(f"Invalid mode: {mode}")
        LOGGER.debug(f"Change mode #{self._poolid} {mode}")
        await self.hass.async_add_executor_job(self._api.set_device_mode, self._index, mode)
        self._mode = mode
        self.async_write_ha_state()
