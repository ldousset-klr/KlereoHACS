"""Setting an entry up in a real Home Assistant: what it registers, and how it runs."""
from datetime import timedelta

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.klereo.const import DOMAIN
from custom_components.klereo.klereo_api import KlereoAuthError, KlereoError

from pool import DATA, POOLID

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
    return hass.data[DOMAIN][entry.entry_id]["coordinator"]


async def test_device(hass, loaded):
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, str(POOLID))})
    assert device is not None
    assert device.name == "Test pool"
    assert device.manufacturer == "Klereo"
    assert device.sw_version == "212D"
    assert device.hw_version == "3"
    assert device.serial_number == "TEST0000"
    # Every entity hangs off that one device.
    assert {e.device_id for e in _entities(hass, loaded)} == {device.id}


async def test_entities(hass, loaded):
    assert loaded.state is ConfigEntryState.LOADED
    assert {e.unique_id for e in _entities(hass, loaded)} == UNIQUE_IDS


async def test_states(hass, loaded):
    state = hass.states.get("sensor.eau_bassin")          # named by IORename
    assert state.state == "26.5"
    assert state.attributes["unit_of_measurement"] == "°C"
    assert state.attributes["device_class"] == "temperature"
    assert hass.states.get("sensor.capteur_ph").state == "7.2"      # PROBE_LABELS
    assert hass.states.get("sensor.capteur_redox").attributes["unit_of_measurement"] == "mV"
    # -1000 is an absent probe: unknown, not a reading of -1000 mbar.
    assert hass.states.get("sensor.pression_gen2_a").state == "unknown"

    assert hass.states.get("switch.spots").state == "off"
    assert hass.states.get("switch.filtration").state == "on"        # speed 2
    assert hass.states.get("number.filtration_speed").state == "2"
    assert hass.states.get("number.water_setpoint").state == "27.5"
    heating = hass.states.get("select.chauffage_mode")
    assert heating.state == "Régulé"
    assert heating.attributes["options"] == ["Manuel", "Régulé"]

    volume = hass.states.get("sensor.ph_corrector_volume")
    assert volume.state == "1500"            # 3600 s x 1.5 L/h
    assert volume.attributes["unit_of_measurement"] == "mL"
    assert volume.attributes["state_class"] == "total_increasing"
    assert hass.states.get("sensor.filtration_runtime").state == "10.0"


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
    assert hass.states.get("sensor.eau_bassin").state == "26.5"
    await _jump(hass, 330)
    assert hass.states.get("sensor.eau_bassin").state == "27.0"


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
    assert hass.states.get("sensor.eau_bassin").state == "26.5"
    await _jump(hass, 930)
    assert hass.states.get("sensor.eau_bassin").state == "27.0"


async def test_data_update_does_not_reload(hass, loaded):
    """Reauth and reconfigure reload on their own; the listener must not add one."""
    before = _coordinator(hass, loaded)
    hass.config_entries.async_update_entry(loaded, data={**loaded.data, "password": "new"})
    await hass.async_block_till_done()
    assert _coordinator(hass, loaded) is before


async def test_unload(hass, loaded):
    assert await hass.config_entries.async_unload(loaded.entry_id)
    await hass.async_block_till_done()
    assert loaded.state is ConfigEntryState.NOT_LOADED
    assert loaded.entry_id not in hass.data[DOMAIN]
    assert hass.states.get("switch.spots").state == "unavailable"


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
    entry = MockConfigEntry(domain=DOMAIN, title="Old", data=dict(DATA))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.unique_id == str(POOLID)
