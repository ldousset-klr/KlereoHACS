"""A real Home Assistant, a fake Klereo server.

pytest-homeassistant-custom-component brings up Home Assistant itself — the
loader, the config entries, the entity and device registries, the state
machine, the scheduler. What it cannot bring up is Klereo Connect: `pool.py`
stands in for it.
"""
import copy

import pytest

# Imported before the hass fixture mounts its own config directory on
# sys.path, so the loader finds this repository's integration. The package has
# no __init__.py on purpose — HACS copies custom_components/klereo alone — and
# a namespace package also lets the harness's own testing_config share it.
import custom_components.klereo  # noqa: F401
from custom_components.klereo import const

from pytest_homeassistant_custom_component.common import MockConfigEntry

from pool import DATA, POOL, POOLID, FakeKlereoAPI


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Home Assistant ignores custom_components/ in tests unless told not to."""
    yield


@pytest.fixture
def api(monkeypatch):
    """The fake server, patched in wherever the component builds a KlereoAPI."""
    FakeKlereoAPI.pool = copy.deepcopy(POOL)
    FakeKlereoAPI.pools = [(POOLID, "Test pool"), (116, "Other pool")]
    FakeKlereoAPI.others = {}
    FakeKlereoAPI.error = FakeKlereoAPI.list_error = None
    FakeKlereoAPI.made = []
    FakeKlereoAPI.calls = []
    monkeypatch.setattr("custom_components.klereo.KlereoAPI", FakeKlereoAPI)
    monkeypatch.setattr("custom_components.klereo.config_flow.KlereoAPI", FakeKlereoAPI)
    # A write is confirmed on COMMAND_POLL_DELAYS, seven sleeps over 26 s;
    # one immediate ask is enough to see the confirmation land.
    monkeypatch.setattr("custom_components.klereo.entity.COMMAND_POLL_DELAYS", (0,))
    return FakeKlereoAPI


@pytest.fixture
def entry(hass):
    """The pool's config entry, added to Home Assistant but not set up."""
    entry = MockConfigEntry(domain=const.DOMAIN, unique_id=str(POOLID),
                            title="Test pool", data=dict(DATA))
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def loaded(hass, api, entry):
    """The entry, set up against the fake server."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
