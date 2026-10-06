"""The downloadable diagnostics, fetched the way the frontend does: over HTTP."""
import json
from http import HTTPStatus

from homeassistant.setup import async_setup_component

from pool import POOL

REDACTED = "**REDACTED**"


async def _download(hass, hass_client, entry):
    assert await async_setup_component(hass, "diagnostics", {})
    await hass.async_block_till_done()
    client = await hass_client()
    response = await client.get(f"/api/diagnostics/config_entry/{entry.entry_id}")
    assert response.status == HTTPStatus.OK
    return await response.json()


async def test_content(hass, hass_client, loaded):
    data = (await _download(hass, hass_client, loaded))["data"]
    assert data["entry"]["data"] == {"username": REDACTED, "password": REDACTED,
                                     "poolid": 115, "server": "https://connect.klereo.fr"}
    assert data["entry"]["title"] == REDACTED
    assert data["entry"]["options"] == {}
    assert data["coordinator"] == {"update_interval": 300.0, "last_update_success": True,
                                   "last_exception": None}
    pool = data["pool"]
    # What the integration reads, as it read it.
    for key in ("probes", "outs", "IORename", "params", "idSystem", "tabSW", "access"):
        assert pool[key] == POOL[key], key
    # Present, but identifying.
    for key in ("poolNickname", "podSerial", "register"):
        assert pool[key] == REDACTED, key
    assert data["pool_other_keys"] == []


async def test_nothing_personal_leaks(hass, hass_client, api, entry):
    """Keys the integration never reads are named, never shown."""
    api.pool.update({
        "address": "12 rue des Lilas", "city": "Ville-Témoin",
        "email": "owner@example.com", "phone": "0600000000",
        "compta": {"iban": "FR7600000000000000000000000"},
    })
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    payload = await _download(hass, hass_client, entry)
    assert payload["data"]["pool_other_keys"] == ["address", "city", "compta", "email", "phone"]
    text = json.dumps(payload, ensure_ascii=False)
    for secret in ("12 rue des Lilas", "Ville-Témoin", "owner@example.com", "0600000000",
                   "FR7600000000000000000000000",            # unread keys
                   "user@example.com", "secret",              # credentials
                   "TEST0000", "1234", "Test pool"):          # serial, PIN, nickname
        assert secret not in text, secret
