"""Entities named after their pool: "<pool> <entity>", and an entity_id to match."""
import copy

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.klereo.const import DOMAIN

from pool import DATA, POOL


async def _setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_new_install(hass, loaded):
    registry = er.async_get(hass)
    for platform, uid, entity_id, name in [
        ("sensor", "id_klereo115probe16", "sensor.test_pool_eau_bassin", "Eau bassin"),
        ("sensor", "id_klereo115pin", "sensor.test_pool_pin", "PIN"),
        ("switch", "id_klereo115out0", "switch.test_pool_spots", "Spots"),
        ("select", "id_klereo115out0mode", "select.test_pool_spots_mode", "Spots mode"),
        ("number", "id_klereo115watersetpoint", "number.test_pool_water_setpoint",
         "Water setpoint"),
    ]:
        assert registry.async_get_entity_id(platform, DOMAIN, uid) == entity_id
        entry = registry.async_get(entity_id)
        assert entry.has_entity_name
        assert entry.original_name == name            # the pool is not in it twice
        assert hass.states.get(entity_id).attributes["friendly_name"] == f"Test pool {name}"


async def test_upgrade_keeps_entity_ids(hass, api, entry):
    """An install from before keeps its entity_ids, and so its history and automations."""
    registry = er.async_get(hass)
    for platform, uid, object_id in [("sensor", "id_klereo115probe16", "eau_bassin"),
                                     ("sensor", "id_klereo115pin", "pin"),
                                     ("switch", "id_klereo115out0", "spots")]:
        registry.async_get_or_create(platform, DOMAIN, uid, config_entry=entry,
                                     suggested_object_id=object_id)
    await _setup(hass, entry)
    assert registry.async_get_entity_id("sensor", DOMAIN, "id_klereo115probe16") == "sensor.eau_bassin"
    assert registry.async_get_entity_id("sensor", DOMAIN, "id_klereo115pin") == "sensor.pin"
    assert registry.async_get_entity_id("switch", DOMAIN, "id_klereo115out0") == "switch.spots"
    # Only the displayed name changes.
    assert hass.states.get("sensor.eau_bassin").attributes["friendly_name"] == "Test pool Eau bassin"
    assert hass.states.get("switch.spots").state == "off"


async def test_two_pools_do_not_collide(hass, api, entry):
    other = copy.deepcopy(POOL)
    other.update(idSystem=116, poolNickname="Other pool")
    api.others[116] = other
    second = MockConfigEntry(domain=DOMAIN, unique_id="116", title="Other pool", version=2,
                             data={**DATA, "poolid": 116})
    second.add_to_hass(hass)
    await _setup(hass, entry)          # sets up every entry of the domain
    assert second.state is ConfigEntryState.LOADED
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("sensor", DOMAIN, "id_klereo115pin") == "sensor.test_pool_pin"
    assert registry.async_get_entity_id("sensor", DOMAIN, "id_klereo116pin") == "sensor.other_pool_pin"
    assert hass.states.get("sensor.other_pool_pin").attributes["friendly_name"] == "Other pool PIN"
    assert not any(e.entity_id.endswith("_2") for e in registry.entities.values())


async def test_names_follow_the_language(hass, api, entry):
    """Fixed names come from the translations, in Home Assistant's language.

    So does a new install's entity_id, French being one of the languages Home
    Assistant builds native entity_ids in. An existing install keeps its own:
    see test_upgrade_keeps_entity_ids.
    """
    hass.config.language = "fr"
    await _setup(hass, entry)
    registry = er.async_get(hass)
    for platform, uid, entity_id, name in [
        ("number", "id_klereo115watersetpoint", "number.test_pool_consigne_eau",
         "Consigne eau"),
        ("number", "id_klereo115out1speed", "number.test_pool_vitesse_filtration",
         "Vitesse Filtration"),
        ("select", "id_klereo115out0mode", "select.test_pool_mode_spots", "Mode Spots"),
        ("sensor", "id_klereo115filtrationtime", "sensor.test_pool_duree_de_filtration",
         "Durée de filtration"),
        ("sensor", "id_klereo115phvolume", "sensor.test_pool_volume_de_correcteur_ph",
         "Volume de correcteur pH"),
        ("sensor", "id_klereo115pin", "sensor.test_pool_pin", "PIN"),
        # The user's and the controller's own names are not translated.
        ("sensor", "id_klereo115probe16", "sensor.test_pool_eau_bassin", "Eau bassin"),
        ("switch", "id_klereo115out0", "switch.test_pool_spots", "Spots"),
    ]:
        assert registry.async_get_entity_id(platform, DOMAIN, uid) == entity_id
        assert hass.states.get(entity_id).attributes["friendly_name"] == f"Test pool {name}"


async def test_translated_names_keep_existing_entity_ids(hass, api, entry):
    """An install from 1.5 keeps the English entity_ids it was given."""
    registry = er.async_get(hass)
    for platform, uid, object_id in [
            ("number", "id_klereo115watersetpoint", "test_pool_water_setpoint"),
            ("select", "id_klereo115out0mode", "test_pool_spots_mode")]:
        registry.async_get_or_create(platform, DOMAIN, uid, config_entry=entry,
                                     suggested_object_id=object_id)
    hass.config.language = "fr"
    await _setup(hass, entry)
    assert hass.states.get("number.test_pool_water_setpoint").attributes[
        "friendly_name"] == "Test pool Consigne eau"
    assert hass.states.get("select.test_pool_spots_mode").attributes[
        "friendly_name"] == "Test pool Mode Spots"
