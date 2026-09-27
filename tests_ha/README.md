# Tests against a real Home Assistant

```bash
pip install -r tests_ha/requirements.txt       # the newest Home Assistant
python -m pytest -c tests_ha/pytest.ini tests_ha
```

from the repository root. `tests_ha/requirements-min.txt` installs Home Assistant
2024.11.0 instead — the minimum `hacs.json` declares — and wants Python 3.12. Use a
separate virtualenv for each: the harness pins `homeassistant` itself.

**The `-c` is required.** The root `pytest.ini` belongs to [`tests/`](../tests/), whose
stub replaces `homeassistant.*` in `sys.modules` — the two suites cannot share a process,
and this one needs `asyncio_mode = auto` besides.

## How it works

[pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)
brings up Home Assistant itself: the loader, config entries, the entity and device
registries, the state machine, the scheduler, the translation loader. Only Klereo
Connect is faked — `pool.py`'s `FakeKlereoAPI`, patched in wherever the component builds
a `KlereoAPI`, answering from a **synthetic** payload (no capture, so no one's address,
serial or PIN) and applying the writes it receives, so a command's full loop — write,
confirmation, refresh, new state — runs as it does against a pod.

`conftest.py` imports `custom_components.klereo` before the `hass` fixture mounts the
harness's own config directory on `sys.path`; without that the loader finds the
harness's `custom_components` instead of this one. `custom_components/` deliberately has
no `__init__.py`, HACS copying `custom_components/klereo` alone.

Two things to know when writing a test. The coordinator's scheduled refresh and every
write's confirmation run as **background tasks of the entry**, which
`hass.async_block_till_done()` does not wait for — pass `wait_background_tasks=True`.
And a jump of the clock is taken from now while the poll timer was armed at setup, so
keep a wide margin either side of an interval rather than a second.

These are ordinary pytest tests with plain `assert`, one scenario each — the `check`
fixture of `tests/` is for tables, which this suite does not hold.

| Suite | What it pins |
|---|---|
| `test_setup.py` | the device and its fields; every entity by `unique_id`; states, units and classes; which entities ship disabled or diagnostic; polling on the default interval; an options change reloading onto the new one, which Home Assistant then schedules; a data update not reloading; unload; bad credentials starting reauth; a server down retrying; the `unique_id` backfill |
| `test_config_flow.py` | the user → pool path, a configured pool not offered again, bad credentials, no pools, the fallback to the manual poolID, a pool unreachable after listing; reauth; reconfigure, refused and missing its password; the options flow and its bounds |
| `test_services.py` | a switch's full round trip; a regulated output refusing with its translated message; a mode change keeping the state; the setpoint rounded to a tenth; the filtration speed; a read-only account and the level-16 treatment outputs refused before anything is sent |
| `test_translations.py` | every step, error, abort, option and exception key, in English and French, through Home Assistant's own translation loader |

## What it caught first

Run against 2024.11.0, the options flow of 1.4.0 raised `AttributeError`: it read
`self.config_entry`, which Home Assistant only provides from 2024.12. The stubbed suite
had set that attribute itself and so could not see it; the stub now refuses it, and
the flow reads the entry through its `handler`.
