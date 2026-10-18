"""The coordinator: one GetPoolDetails per poll, shared by every entity of a pool."""
from datetime import timedelta
import logging

from requests import RequestException

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import scan_interval
from .klereo_api import KlereoAuthError, KlereoError

LOGGER = logging.getLogger(__name__)


class KlereoCoordinator(DataUpdateCoordinator):
    """Polls one pool, and carries the API its entities write through.

    It is the entry's runtime_data: the platforms take the payload and the API
    from it, and nothing lives in hass.data any more.
    """

    def __init__(self, hass, entry, api):
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name="klereo_data_coordinator",
            update_interval=timedelta(seconds=scan_interval(entry.options)),
        )
        self.api = api

    async def _async_update_data(self):
        try:
            # requests is blocking: it runs in the executor, never on the loop.
            return await self.hass.async_add_executor_job(self.api.get_pool)
        except KlereoAuthError as err:
            # Hands the entry over to the reauth flow instead of retrying forever.
            raise ConfigEntryAuthFailed(str(err)) from err
        except (KlereoError, RequestException) as err:
            raise UpdateFailed(str(err)) from err
