import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN,CONF_USERNAME,CONF_PASSWORD,CONF_POOLID,DEF_POOLID

import logging
LOGGER = logging.getLogger(__name__)

@config_entries.HANDLERS.register(DOMAIN)
class KlereoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        LOGGER.info(f"Configuration {DOMAIN}")
        if user_input is not None:
            try:
                await self._test_credentials(user_input[CONF_USERNAME], user_input[CONF_PASSWORD],user_input[CONF_POOLID])
                return self.async_create_entry(
                    title=f"Klereo pool #{user_input[CONF_POOLID]}", 
                    data=user_input
                )
            except Exception:
                errors["base"] = "auth"
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

    async def _test_credentials(self, username, password, poolid):
        LOGGER.info(f"Todo: Verifying credentials for user '{username}' for pool #{poolid}")
        pass
