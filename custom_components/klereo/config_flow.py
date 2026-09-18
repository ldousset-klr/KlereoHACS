import voluptuous as vol
from homeassistant import config_entries
from requests import RequestException

from .const import DOMAIN,CONF_USERNAME,CONF_PASSWORD,CONF_POOLID,DEF_POOLID
from .klereo_api import KlereoAPI, KlereoAuthError, KlereoError

import logging
LOGGER = logging.getLogger(__name__)

class KlereoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._reauth_entry = None
        self._username = None
        self._password = None
        self._pools = []

    async def async_step_user(self, user_input=None):
        """Collect the credentials, then list the account's pools."""
        errors = {}
        LOGGER.info(f"Configuration {DOMAIN}")
        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]
            try:
                self._pools = await self._list_pools()
            except KlereoAuthError as err:
                LOGGER.warning(f"Klereo rejected the credentials: {err}")
                errors = {"base": "invalid_auth"}
            except (KlereoError, RequestException) as err:
                # The credentials may well be fine and only GetIndex be
                # unavailable, so fall back to typing the poolID rather than
                # blocking setup entirely.
                LOGGER.warning(f"Could not list the pools ({err}), asking for the poolID")
                return await self.async_step_manual()
            else:
                if not self._pools:
                    return self.async_abort(reason="no_pools")
                return await self.async_step_pool()
        data_schema = {
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
        }
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(data_schema),
            errors=errors,
        )

    async def async_step_pool(self, user_input=None):
        """Pick one of the pools GetIndex reported."""
        errors = {}
        names = {str(pool_id): name for pool_id, name in self._pools}
        if user_input is not None:
            poolid = int(user_input[CONF_POOLID])
            await self.async_set_unique_id(str(poolid))
            self._abort_if_unique_id_configured()
            data = self._entry_data(poolid)
            errors = await self._validate(data)
            if not errors:
                return self.async_create_entry(
                    title=names.get(str(poolid), f"Klereo pool #{poolid}"),
                    data=data,
                )
        # Drop what is already set up: the unique_id would reject it anyway,
        # but only after the user picked it.
        configured = {entry.unique_id for entry in self._async_current_entries()}
        choices = {key: name for key, name in sorted(names.items(), key=lambda kv: kv[1])
                   if key not in configured}
        if not choices:
            return self.async_abort(reason="already_configured")
        return self.async_show_form(
            step_id="pool",
            data_schema=vol.Schema({vol.Required(CONF_POOLID): vol.In(choices)}),
            errors=errors,
        )

    async def async_step_manual(self, user_input=None):
        """Fallback when GetIndex is unreachable: type the poolID."""
        errors = {}
        if user_input is not None:
            poolid = user_input[CONF_POOLID]
            await self.async_set_unique_id(str(poolid))
            self._abort_if_unique_id_configured()
            data = self._entry_data(poolid)
            errors = await self._validate(data)
            if not errors:
                return self.async_create_entry(
                    title=f"Klereo pool #{poolid}",
                    data=data,
                )
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({
                vol.Required(CONF_POOLID, default=DEF_POOLID): vol.Coerce(int),
            }),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data):
        """Entered when the coordinator raises ConfigEntryAuthFailed."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            data = {**self._reauth_entry.data, **user_input}
            errors = await self._validate(data)
            if not errors:
                self.hass.config_entries.async_update_entry(self._reauth_entry, data=data)
                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")
        data_schema = {
            vol.Required(
                CONF_USERNAME, default=self._reauth_entry.data.get(CONF_USERNAME)
            ): str,
            vol.Required(CONF_PASSWORD): str,
        }
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(data_schema),
            errors=errors,
        )

    def _entry_data(self, poolid):
        return {
            CONF_USERNAME: self._username,
            CONF_PASSWORD: self._password,
            CONF_POOLID: poolid,
        }

    async def _list_pools(self):
        """[(idSystem, name)] for the credentials being entered."""
        api = KlereoAPI(self._username, self._password)
        return await self.hass.async_add_executor_job(api.list_pools)

    async def _validate(self, data):
        """Return the form errors for these credentials, empty if they work."""
        try:
            await self._test_credentials(
                data[CONF_USERNAME], data[CONF_PASSWORD], data[CONF_POOLID]
            )
        except KlereoAuthError as err:
            LOGGER.warning(f"Klereo rejected the credentials: {err}")
            return {"base": "invalid_auth"}
        except (KlereoError, RequestException) as err:
            LOGGER.warning(f"Could not reach Klereo: {err}")
            return {"base": "cannot_connect"}
        return {}

    async def _test_credentials(self, username, password, poolid):
        """Log in and read the pool, so a bad login or a bad poolID is caught here."""
        LOGGER.info(f"Verifying credentials for user '{username}' for pool #{poolid}")
        api = KlereoAPI(username, password, poolid)
        await self.hass.async_add_executor_job(api.get_pool)
