"""Setting an entry up in a real Home Assistant: what it registers, and how it runs."""
from datetime import timedelta

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.klereo.const import DOMAIN, HEATER_NONE, HEATER_PAC_KLINK
from custom_components.klereo.klereo_api import KlereoAuthError, KlereoError

from pool import DATA, PASSWORD, PASSWORD_HASH, POOLID

# Every entity the synthetic pool gives, by unique_id. A change here is a
# change to what existing installs are keyed on — deliberate or not, it shows.
UNIQUE_IDS = {
    # one sensor per probe
    "id_klereo115probe13", "id_klereo115probe16", "id_klereo115probe17",
    "id_klereo115probe18",
    # diagnostics
    "id_klereo115pin", "id_klereo115device", "id_klereo115volume",
    "id_klereo115filtrationtime", "id_klereo115phtime",
    "id_klereo115disinfectanttime", "id_klereo115heatingtime",
    "id_klereo115phvolume", "id_klereo115disinfectantvolume",
    # one switch and one mode select per out
    *(f"id_klereo115out{i}" for i in range(5)),
    *(f"id_klereo115out{i}mode" for i in range(5)),
    # the filtration speed and the water setpoint
    "id_klereo115out1speed", "id_klereo115watersetpoint",
}


def _entities(hass, entry):
    return er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)


async def _jump(hass, seconds):
    """Move the clock on, and let the poll it triggers finish.

    The coordinator runs a scheduled refresh as a background task of the
    entry, which a plain async_block_till_done() does not wait for. The clock
    is jumped from now, while the timer was armed at setup, so the jumps keep
    a wide margin either side of the interval rather than a second.
    """
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done(wait_background_tasks=True)


def _coordinator(hass, entry):
    return entry.runtime_data


async def test_device(hass, loaded):
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, str(POOLID))})
    assert device is not None
    assert device.name == "Test pool"
    assert device.manufacturer == "Klereo"
    assert device.sw_version == "212D"
    assert device.hw_version == "3"
    assert device.serial_number == "TEST0000"
    assert device.configuration_url == "https://connect.klereo.fr"
    # Every entity hangs off that one device.
    assert {e.device_id for e in _entities(hass, loaded)} == {device.id}


async def test_entities(hass, loaded):
    assert loaded.state is ConfigEntryState.LOADED
    assert {e.unique_id for e in _entities(hass, loaded)} == UNIQUE_IDS


async def test_states(hass, loaded):
    state = hass.states.get("sensor.test_pool_eau_bassin")          # named by IORename
    assert state.state == "26.5"
    assert state.attributes["unit_of_measurement"] == "°C"
    assert state.attributes["device_class"] == "temperature"
    assert hass.states.get("sensor.test_pool_capteur_ph").state == "7.2"      # PROBE_LABELS
    assert hass.states.get("sensor.test_pool_capteur_redox").attributes["unit_of_measurement"] == "mV"
    # -1000 is an absent probe: unknown, not a reading of -1000 mbar.
    assert hass.states.get("sensor.test_pool_pression_gen2_a").state == "unknown"

    assert hass.states.get("switch.test_pool_spots").state == "off"
    assert hass.states.get("switch.test_pool_filtration").state == "on"        # speed 2
    assert hass.states.get("number.test_pool_filtration_speed").state == "2"
    assert hass.states.get("number.test_pool_water_setpoint").state == "27.5"
    heating = hass.states.get("select.test_pool_chauffage_mode")
    assert heating.state == "Régulé"
    assert heating.attributes["options"] == ["Manuel", "Régulé"]

    volume = hass.states.get("sensor.test_pool_ph_corrector_volume")
    assert volume.state == "1500"            # 3600 s x 1.5 L/h
    assert volume.attributes["unit_of_measurement"] == "mL"
    assert volume.attributes["state_class"] == "total_increasing"
    assert hass.states.get("sensor.test_pool_filtration_runtime").state == "10.0"


async def test_registry_flags(hass, loaded):
    by_uid = {e.unique_id: e for e in _entities(hass, loaded)}
    disabled = {uid for uid, e in by_uid.items() if e.disabled_by is not None}
    # The treatment outs and the water volume, nothing else.
    assert disabled == {"id_klereo115out2", "id_klereo115out2mode",
                        "id_klereo115out3", "id_klereo115out3mode",
                        "id_klereo115volume"}
    assert all(by_uid[uid].disabled_by is er.RegistryEntryDisabler.INTEGRATION
               for uid in disabled)
    diagnostic = {uid for uid, e in by_uid.items() if e.entity_category is not None}
    assert diagnostic == {"id_klereo115pin", "id_klereo115device", "id_klereo115volume",
                          "id_klereo115filtrationtime", "id_klereo115phtime",
                          "id_klereo115disinfectanttime", "id_klereo115heatingtime",
                          "id_klereo115phvolume", "id_klereo115disinfectantvolume"}


async def test_polls_on_the_default_interval(hass, api, loaded):
    assert _coordinator(hass, loaded).update_interval == timedelta(seconds=300)
    api.pool["probes"][0]["filteredValue"] = 27.0
    await _jump(hass, 240)
    assert hass.states.get("sensor.test_pool_eau_bassin").state == "26.5"
    await _jump(hass, 330)
    assert hass.states.get("sensor.test_pool_eau_bassin").state == "27.0"


async def test_options_change_reloads_on_the_new_interval(hass, api, loaded):
    before = _coordinator(hass, loaded)
    result = await hass.config_entries.options.async_init(loaded.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 900})
    await hass.async_block_till_done()
    after = _coordinator(hass, loaded)
    assert after is not before                       # reloaded
    assert after.update_interval == timedelta(seconds=900)
    assert loaded.state is ConfigEntryState.LOADED

    # And the new interval is the one Home Assistant schedules.
    api.pool["probes"][0]["filteredValue"] = 27.0
    await _jump(hass, 330)
    assert hass.states.get("sensor.test_pool_eau_bassin").state == "26.5"
    await _jump(hass, 930)
    assert hass.states.get("sensor.test_pool_eau_bassin").state == "27.0"


async def test_data_update_does_not_reload(hass, loaded):
    """Reauth and reconfigure reload on their own; the listener must not add one."""
    before = _coordinator(hass, loaded)
    hass.config_entries.async_update_entry(loaded, data={**loaded.data,
                                                         "password_hash": "new"})
    await hass.async_block_till_done()
    assert _coordinator(hass, loaded) is before


async def test_unload(hass, loaded):
    assert await hass.config_entries.async_unload(loaded.entry_id)
    await hass.async_block_till_done()
    assert loaded.state is ConfigEntryState.NOT_LOADED
    assert not hasattr(loaded, "runtime_data")       # Home Assistant drops it
    assert DOMAIN not in hass.data                    # and nothing else was kept
    assert hass.states.get("switch.test_pool_spots").state == "unavailable"


async def test_bad_credentials_start_reauth(hass, api, entry):
    api.error = KlereoAuthError("refused")
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = [f for f in hass.config_entries.flow.async_progress()
             if f["handler"] == DOMAIN and f["context"]["source"] == SOURCE_REAUTH]
    assert len(flows) == 1


async def test_server_down_retries(hass, api, entry):
    api.error = KlereoError("down")
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unique_id_backfilled(hass, api):
    entry = MockConfigEntry(domain=DOMAIN, title="Old", version=2, data=dict(DATA))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.unique_id == str(POOLID)


async def test_device_links_to_the_entry_server(hass, api):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=str(POOLID), title="Dev", version=2,
                            data={**DATA, "server": "https://dev.example/php"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, str(POOLID))})
    assert device.configuration_url == "https://dev.example"


async def test_missing_sections(hass, api, entry):
    """A payload without probes nor outs sets up, with what it does carry."""
    del api.pool["probes"]
    api.pool["outs"] = None
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    uids = {e.unique_id for e in _entities(hass, entry)}
    assert not any("probe" in uid or "out" in uid for uid in uids)
    assert "id_klereo115pin" in uids


async def test_runtime_data(hass, api, loaded):
    """The coordinator is the entry's runtime_data, and carries the API."""
    coordinator = loaded.runtime_data
    assert type(coordinator).__name__ == "KlereoCoordinator"
    assert coordinator.api.poolid == POOLID
    assert coordinator.config_entry is loaded
    assert DOMAIN not in hass.data


async def test_migration_hashes_the_password(hass, api):
    """A version 1 entry stored the password: it is replaced by its hash."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=str(POOLID), title="Old", version=1,
                            data={"username": "user@example.com", "password": PASSWORD,
                                  "poolid": POOLID, "server": DATA["server"]})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.version == 2
    assert entry.data == DATA
    assert "password" not in entry.data
    # Logged in with the very hash GetJWT was always sent.
    assert api.made[-1] == ("user@example.com", PASSWORD_HASH, POOLID, DATA["server"])


async def test_newer_entry_is_refused(hass, api):
    """An entry from a later release is left alone rather than misread."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=str(POOLID), title="New", version=3,
                            data=dict(DATA))
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.MIGRATION_ERROR
    assert entry.data == DATA


async def test_new_items_get_their_entities(hass, api, loaded):
    """A probe, an out or a setting that appears after setup, at the next poll."""
    before = {e.unique_id for e in _entities(hass, loaded)}
    api.pool["probes"].append({"index": 19, "type": 10, "filteredValue": 12,
                               "filteredTime": 60, "directValue": 12, "directTime": 30})
    api.pool["outs"].append({"index": 5, "type": 0, "mode": 0, "status": 1,
                             "realStatus": 1, "updateTime": 0})
    # A flocculant, with the running time its dosed volume is computed from.
    api.pool["outs"].append({"index": 8, "type": 0, "mode": 0, "status": 0,
                             "realStatus": 0, "updateTime": 0, "totalTime": 600})
    await _coordinator(hass, loaded).async_refresh()
    await hass.async_block_till_done()
    added = {e.unique_id for e in _entities(hass, loaded)} - before
    assert added == {"id_klereo115probe19", "id_klereo115out5", "id_klereo115out5mode",
                     "id_klereo115out8", "id_klereo115out8mode",
                     "id_klereo115flocculantvolume"}
    assert hass.states.get("switch.test_pool_auxiliaire_1").state == "on"
    # Nothing is added twice, and the device is still the one device.
    await _coordinator(hass, loaded).async_refresh()
    await hass.async_block_till_done()
    assert {e.unique_id for e in _entities(hass, loaded)} == before | added
    assert len({e.device_id for e in _entities(hass, loaded)}) == 1


async def test_entities_follow_a_reload(hass, api, loaded):
    """The listener goes with the entry: a reload starts from a clean slate."""
    api.pool["outs"].append({"index": 5, "type": 0, "mode": 0, "status": 0,
                             "realStatus": 0, "updateTime": 0})
    assert await hass.config_entries.async_reload(loaded.entry_id)
    await hass.async_block_till_done()
    coordinator = _coordinator(hass, loaded)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    ids = [e.unique_id for e in _entities(hass, loaded)]
    assert len(ids) == len(set(ids))
    assert "id_klereo115out5" in ids


async def test_gone_equipment_is_unavailable(hass, api, loaded):
    """An item the payload stops carrying reads unavailable, and comes back."""
    spots = api.pool["outs"].pop(0)
    probe = api.pool["probes"].pop(0)
    del api.pool["register"]
    await _coordinator(hass, loaded).async_refresh()
    await hass.async_block_till_done()
    for entity_id in ("switch.test_pool_spots", "select.test_pool_spots_mode",
                      "sensor.test_pool_eau_bassin", "sensor.test_pool_pin"):
        assert hass.states.get(entity_id).state == "unavailable", entity_id
    # Something still reported stays available.
    assert hass.states.get("number.test_pool_water_setpoint").state == "27.5"
    api.pool["outs"].insert(0, spots)
    api.pool["probes"].insert(0, probe)
    api.pool["register"] = {"pin": 1234}
    await _coordinator(hass, loaded).async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("switch.test_pool_spots").state == "off"
    assert hass.states.get("sensor.test_pool_eau_bassin").state == "26.5"
    assert hass.states.get("sensor.test_pool_pin").state == "1234"


async def test_mode_options_follow_the_payload(hass, api, loaded):
    """A heater swapped for a heat pump shows its modes at the next poll."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("select", DOMAIN, "id_klereo115out4mode")
    assert hass.states.get(entity_id).attributes["options"] == ["Manuel", "Régulé"]
    api.pool["params"]["HeaterMode"] = HEATER_PAC_KLINK
    await _coordinator(hass, loaded).async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).attributes["options"] == [
        "Manuel", "Auto", "Refroidit", "Réchauffe"]
    api.pool["params"]["HeaterMode"] = HEATER_NONE
    await _coordinator(hass, loaded).async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unavailable"


async def test_probe_precision(hass, api, loaded):
    """Each probe is shown to its unit's resolution; the pressure to the ten."""
    registry = er.async_get(hass)
    for entity_id, digits in (("sensor.test_pool_eau_bassin", 1),
                              ("sensor.test_pool_capteur_ph", 1),
                              ("sensor.test_pool_capteur_redox", 0),
                              ("sensor.test_pool_pression_gen2_a", 0)):
        options = registry.async_get(entity_id).options["sensor"]
        assert options["suggested_display_precision"] == digits, entity_id
    pressure = next(p for p in api.pool["probes"] if p["type"] == 6)
    pressure["filteredValue"] = 1234
    await _coordinator(hass, loaded).async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_pool_pression_gen2_a").state == "1230.0"
