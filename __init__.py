# Klereo integration

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from datetime import timedelta

from .const import DOMAIN,UPDATE_INTERVAL
from .klereo_api import KlereoAPI

import logging
LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "switch"]

async def async_setup(hass: HomeAssistant, config: dict):
    LOGGER.info("Initializing %s integration...",DOMAIN)
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    
    async def async_update_data():
        return await hass.async_add_executor_job(api.get_pool)

    # Initialize the API
    LOGGER.info(f"Initializing {DOMAIN} for pool #{entry.data.get('poolid')}...")
    api = KlereoAPI(entry.data.get('username'), entry.data.get('password'), entry.data.get('poolid'))
    
    # Create a DataUpdateCoordinator
    coordinator = DataUpdateCoordinator(
        hass,
        LOGGER,
        name="klereo_data_coordinator",
        update_method=async_update_data,
        update_interval=timedelta(seconds=UPDATE_INTERVAL),
    )
    
    # Perform the first refresh to populate data
    await coordinator.async_config_entry_first_refresh()
    
    # Store coordinator and API instance in hass.data for use in platforms
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "api": api
    }

    # Forward the entry setup to supported platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    LOGGER.info("Successfully set up %s integration",DOMAIN)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    LOGGER.info("Unloading %s integration",DOMAIN)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
