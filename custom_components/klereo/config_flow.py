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

    async def async_step_user(self, user_input=None):
        errors = {}
        LOGGER.info(f"Configuration {DOMAIN}")
        if user_input is not None:
            # One config entry per pool: adding the same poolID twice would
            # collide on every entity unique_id.
            await self.async_set_unique_id(str(user_input[CONF_POOLID]))
            self._abort_if_unique_id_configured()
            errors = await self._validate(user_input)
            if not errors:
                return self.async_create_entry(
                    title=f"Klereo pool #{user_input[CONF_POOLID]}", 
                    data=user_input
                )
        data_schema = {
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Required(CONF_POOLID, default=DEF_POOLID): vol.Coerce(int),
        }
        return self.async_show_form(
            step_id="user", 
            data_schema=vol.Schema(data_schema), 
            errors=errors,
            description_placeholders={
                "username_help": "Entrez votre identifiant Klereo",
                "password_help": "Entrez votre mot de passe Klereo",
                "poolid_help": "Entrez le numéro de votre piscine"
            }
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
