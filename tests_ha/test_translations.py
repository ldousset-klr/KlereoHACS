"""Every key the integration shows, as Home Assistant's own loader reads it."""
import pytest

from homeassistant.helpers.translation import async_get_translations

from custom_components.klereo.const import DOMAIN

KEYS = {
    "config": [
        *(f"step.{step}.title" for step in
          ("user", "pool", "manual", "reauth_confirm", "reconfigure")),
        "step.user.data.server", "step.reconfigure.data.password",
        "error.invalid_auth", "error.cannot_connect",
        "abort.reauth_successful", "abort.reconfigure_successful",
        "abort.already_configured", "abort.no_pools",
    ],
    "options": ["step.init.title", "step.init.data.scan_interval"],
    "exceptions": [
        f"{key}.message" for key in (
            "out_read_only", "out_mode_no_switching", "out_mode_ambiguous_state",
            "out_speed_not_settable", "account_read_only", "out_needs_full_access")
    ],
}


@pytest.mark.parametrize("language", ["en", "fr"])
async def test_translations(hass, language):
    for category, keys in KEYS.items():
        loaded = await async_get_translations(hass, language, category, [DOMAIN])
        missing = [k for k in keys if f"component.{DOMAIN}.{category}.{k}" not in loaded]
        assert missing == [], f"{language}/{category}"
