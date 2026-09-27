"""The config, reauth, reconfigure and options flows, driven through Home Assistant."""
import pytest
import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    SOURCE_USER,
)
from homeassistant.data_entry_flow import FlowResultType

from custom_components.klereo.const import DEF_SERVER, DOMAIN
from custom_components.klereo.klereo_api import KlereoAuthError, KlereoError

from pool import DATA, POOLID

LOGIN = {"username": "user@example.com", "password": "secret", "server": DEF_SERVER}


async def _start(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})


async def test_user_picks_a_pool(hass, api):
    result = await _start(hass)
    assert (result["type"], result["step_id"]) == (FlowResultType.FORM, "user")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOGIN)
    assert (result["type"], result["step_id"]) == (FlowResultType.FORM, "pool")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"poolid": str(POOLID)})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test pool"
    assert result["data"] == DATA
    assert result["result"].unique_id == str(POOLID)
    # The pool was read before the entry was created, on the server typed in.
    assert api.made[-1] == ("user@example.com", "secret", POOLID, DEF_SERVER)


async def test_configured_pool_is_not_offered_again(hass, api, entry):
    api.pools = [(POOLID, "Test pool")]
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOGIN)
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "already_configured")


async def test_bad_credentials(hass, api):
    api.error = KlereoAuthError("refused")
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOGIN)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_account_without_pools(hass, api):
    api.pools = []
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOGIN)
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "no_pools")


async def test_pool_list_down_falls_back_to_manual(hass, api):
    api.list_error = KlereoError("GetIndex down")
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOGIN)
    assert (result["type"], result["step_id"]) == (FlowResultType.FORM, "manual")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"poolid": POOLID})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Klereo pool #{POOLID}"


async def test_pool_unreachable_after_listing(hass, api):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], LOGIN)
    api.error = KlereoError("down")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"poolid": str(POOLID)})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth(hass, api, loaded):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_REAUTH, "entry_id": loaded.entry_id},
        data=loaded.data)
    assert (result["type"], result["step_id"]) == (FlowResultType.FORM, "reauth_confirm")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "user@example.com", "password": "renewed"})
    await hass.async_block_till_done()
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "reauth_successful")
    assert loaded.data["password"] == "renewed"


async def _reconfigure(hass, entry):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id})


async def test_reconfigure(hass, api, loaded):
    result = await _reconfigure(hass, loaded)
    assert (result["type"], result["step_id"]) == (FlowResultType.FORM, "reconfigure")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "username": "other@example.com", "password": "p2",
        "server": "https://dev.example"})
    await hass.async_block_till_done()
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT,
                                                  "reconfigure_successful")
    assert loaded.data == {"username": "other@example.com", "password": "p2",
                           "poolid": POOLID, "server": "https://dev.example"}
    # Validated against the new server, on the same pool, and running on it.
    assert ("other@example.com", "p2", POOLID, "https://dev.example") in api.made
    assert api.made[-1][3] == "https://dev.example"


async def test_reconfigure_refused_leaves_the_entry(hass, api, loaded):
    result = await _reconfigure(hass, loaded)
    api.error = KlereoAuthError("refused")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "username": "user@example.com", "password": "wrong", "server": DEF_SERVER})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert loaded.data == DATA


async def test_reconfigure_requires_the_password(hass, api, loaded):
    result = await _reconfigure(hass, loaded)
    with pytest.raises(vol.Invalid):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {"username": "user@example.com", "server": DEF_SERVER})


async def test_options(hass, api, loaded):
    result = await hass.config_entries.options.async_init(loaded.entry_id)
    assert (result["type"], result["step_id"]) == (FlowResultType.FORM, "init")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 1800})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert loaded.options == {"scan_interval": 1800}


@pytest.mark.parametrize("value", [299, 3601])
async def test_options_out_of_bounds(hass, api, loaded, value):
    result = await hass.config_entries.options.async_init(loaded.entry_id)
    with pytest.raises(vol.Invalid):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {"scan_interval": value})
    assert loaded.options == {}
