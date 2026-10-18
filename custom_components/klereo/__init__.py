# Klereo integration

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from datetime import timedelta

from .const import (CONF_PASSWORD, CONF_PASSWORD_HASH, CONF_POOLID, CONF_SERVER,
                    CONF_USERNAME, DOMAIN, scan_interval)
from .coordinator import KlereoCoordinator
from .klereo_api import KlereoAPI, hash_password

import logging
LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "switch", "number", "select"]

# There is nothing to set up from YAML: the integration is config-entry only.
# Declaring it makes Home Assistant reject a klereo: block with a clear message,
# and replaces the async_setup stub that only logged.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Version 1 stored the password itself; version 2 stores its hash.

    The hash is what GetJWT.php is sent anyway, so nothing changes on the wire
    and nobody has to type anything again. Going back to a release before 1.6.0
    is the one thing this costs: Home Assistant refuses an entry newer than the
    integration, and the entry has to be added again.
    """
    if entry.version > 2:
        LOGGER.error("Entry for pool #%s is version %s, newer than this release "
                     "knows", entry.data.get(CONF_POOLID), entry.version)
        return False
    if entry.version == 1:
        data = dict(entry.data)
        password = data.pop(CONF_PASSWORD, None)
        if password is not None:
            data[CONF_PASSWORD_HASH] = hash_password(password)
        hass.config_entries.async_update_entry(entry, data=data, version=2)
        LOGGER.debug("Migrated pool #%s to version 2: password replaced by its hash",
                     data.get(CONF_POOLID))
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Entries created before the flow set one have no unique_id, which would
    # let the same pool be added a second time. Backfill it here.
    if entry.unique_id is None:
        hass.config_entries.async_update_entry(
            entry, unique_id=str(entry.data.get(CONF_POOLID))
        )

    LOGGER.debug("Initializing %s for pool #%s", DOMAIN, entry.data.get(CONF_POOLID))
    api = KlereoAPI(entry.data.get(CONF_USERNAME), entry.data.get(CONF_PASSWORD_HASH),
                    entry.data.get(CONF_POOLID), entry.data.get(CONF_SERVER))
    coordinator = KlereoCoordinator(hass, entry, api)

    # Perform the first refresh to populate data
    await coordinator.async_config_entry_first_refresh()

    # The platforms, the update listener and the diagnostics read it from here;
    # Home Assistant drops it when the entry unloads.
    entry.runtime_data = coordinator

    # Forward the entry setup to supported platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # The options flow only writes entry.options; this is what applies them.
    entry.async_on_unload(entry.add_update_listener(async_entry_updated))

    LOGGER.debug("Set up %s for pool #%s", DOMAIN, entry.data.get(CONF_POOLID))
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    LOGGER.debug("Unloading %s for pool #%s", DOMAIN, entry.data.get(CONF_POOLID))
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

async def async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when the poll interval changed, and ignore every other update.

    Home Assistant calls this on any async_update_entry, the reauth and
    reconfigure steps included — and those reload on their own, so reacting to
    them as well would reload the entry twice. Comparing with the interval the
    coordinator runs at singles out an options change.
    """
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is None:
        return      # already unloading, or reloading from another step
    wanted = timedelta(seconds=scan_interval(entry.options))
    if coordinator.update_interval != wanted:
        LOGGER.info("Poll interval changed to %s, reloading", wanted)
        await hass.config_entries.async_reload(entry.entry_id)
