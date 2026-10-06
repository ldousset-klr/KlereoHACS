"""Commands through Home Assistant's services: what reaches Klereo, and what comes back."""
import pytest

from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.klereo.const import DOMAIN


async def _call(hass, domain, service, entity_id, **data):
    await hass.services.async_call(domain, service, {"entity_id": entity_id, **data},
                                   blocking=True)
    # The confirmation runs as a background task of the entry.
    await hass.async_block_till_done(wait_background_tasks=True)


def _writes(api):
    return [c for c in api.calls if c[0] in ("set_out", "set_param")]


async def test_switch_round_trip(hass, api, loaded):
    await _call(hass, "switch", "turn_on", "switch.test_pool_spots")
    # Mode carried through (Manuel), state 1, then the command followed up.
    assert _writes(api) == [("set_out", 0, 1, 0)]
    assert ("command_status", 1) in api.calls
    assert hass.states.get("switch.test_pool_spots").state == "on"
    await _call(hass, "switch", "turn_off", "switch.test_pool_spots")
    assert _writes(api)[-1] == ("set_out", 0, 0, 0)
    assert hass.states.get("switch.test_pool_spots").state == "off"


async def test_regulated_output_refuses_a_switch(hass, api, loaded):
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "switch", "turn_on", "switch.test_pool_chauffage")
    assert err.value.translation_key == "out_mode_no_switching"
    assert _writes(api) == []
    # Home Assistant renders the message from translations/, not the raw key.
    assert "out_mode_no_switching" not in str(err.value)
    assert "Régulé" in str(err.value)


async def test_mode_select_keeps_the_state(hass, api, loaded):
    await _call(hass, "select", "select_option", "select.test_pool_spots_mode", option="Minuterie")
    assert _writes(api) == [("set_out", 0, 2, 2)]      # newState 2: keep
    assert hass.states.get("select.test_pool_spots_mode").state == "Minuterie"
    assert hass.states.get("switch.test_pool_spots").state == "off"


async def test_setpoint(hass, api, loaded):
    await _call(hass, "number", "set_value", "number.test_pool_water_setpoint", value=28.34)
    assert _writes(api) == [("set_param", "ConsigneEau", 28.3)]
    assert hass.states.get("number.test_pool_water_setpoint").state == "28.3"


async def test_filtration_speed(hass, api, loaded):
    await _call(hass, "number", "set_value", "number.test_pool_filtration_speed", value=3)
    assert _writes(api) == [("set_out", 1, 3, 0)]
    assert hass.states.get("number.test_pool_filtration_speed").state == "3"
    assert hass.states.get("switch.test_pool_filtration").state == "on"


async def test_read_only_account(hass, api, entry):
    api.pool["access"] = 5
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    for domain, service, entity_id, data in [
        ("number", "set_value", "number.test_pool_water_setpoint", {"value": 28}),
        ("switch", "turn_on", "switch.test_pool_spots", {}),
        ("select", "select_option", "select.test_pool_spots_mode", {"option": "Minuterie"}),
    ]:
        with pytest.raises(ServiceValidationError) as err:
            await _call(hass, domain, service, entity_id, **data)
        assert err.value.translation_key == "account_read_only", entity_id
    assert _writes(api) == []


async def test_treatment_output_needs_full_access(hass, api, loaded):
    """Enabled by the user, the pH corrector still refuses below level 16."""
    api.pool["access"] = 10
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("select", DOMAIN, "id_klereo115out2mode")
    registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(loaded.entry_id)
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "select", "select_option", entity_id, option="Manuel")
    assert err.value.translation_key == "out_needs_full_access"
    assert _writes(api) == []
