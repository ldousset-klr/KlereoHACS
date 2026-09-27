# Klereo integration

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from datetime import timedelta
from requests import RequestException

from .const import DOMAIN, scan_interval
from .klereo_api import KlereoAPI, KlereoAuthError, KlereoError

import logging
LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "switch", "number", "select"]

# There is nothing to set up from YAML: the integration is config-entry only.
# Declaring it makes Home Assistant reject a klereo: block with a clear message,
# and replaces the async_setup stub that only logged.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    
    async def async_update_data():
        try:
            return await hass.async_add_executor_job(api.get_pool)
        except KlereoAuthError as err:
            # Hands the entry over to the reauth flow instead of retrying forever.
            raise ConfigEntryAuthFailed(str(err)) from err
        except (KlereoError, RequestException) as err:
            raise UpdateFailed(str(err)) from err

    # Entries created before the flow set one have no unique_id, which would
    # let the same pool be added a second time. Backfill it here.
    if entry.unique_id is None:
        hass.config_entries.async_update_entry(
            entry, unique_id=str(entry.data.get('poolid'))
        )

    # Initialize the API
    LOGGER.info(f"Initializing {DOMAIN} for pool #{entry.data.get('poolid')}...")
    api = KlereoAPI(entry.data.get('username'), entry.data.get('password'),
                    entry.data.get('poolid'), entry.data.get('server'))
    
    # Create a DataUpdateCoordinator
    coordinator = DataUpdateCoordinator(
        hass,
        LOGGER,
        config_entry=entry,
        name="klereo_data_coordinator",
        update_method=async_update_data,
        update_interval=timedelta(seconds=scan_interval(entry.options)),
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

    # The options flow only writes entry.options; this is what applies them.
    entry.async_on_unload(entry.add_update_listener(async_entry_updated))

    LOGGER.info("Successfully set up %s integration",DOMAIN)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    LOGGER.info("Unloading %s integration",DOMAIN)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

async def async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when the poll interval changed, and ignore every other update.

    Home Assistant calls this on any async_update_entry, the reauth and
    reconfigure steps included — and those reload on their own, so reacting to
    them as well would reload the entry twice. Comparing with the interval the
    coordinator runs at singles out an options change.
    """
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if runtime is None:
        return      # already unloading, or reloading from another step
    wanted = timedelta(seconds=scan_interval(entry.options))
    if runtime["coordinator"].update_interval != wanted:
        LOGGER.info("Poll interval changed to %s, reloading", wanted)
        await hass.config_entries.async_reload(entry.entry_id)
