# Tests

```bash
pip install -r requirements-test.txt
python -m pytest
```

from the repository root. That file is **pytest, `requests` and `voluptuous`** — no Home
Assistant, no network, no pool. The suite against a real Home Assistant lives apart, in
[`tests_ha/`](../tests_ha/).

## How it works

`klereo_stub.py` installs fake `homeassistant.*` modules into `sys.modules`, and
`conftest.py` imports it before any suite, so `custom_components/klereo/`'s own imports
resolve against the stub. The stub also carries the doubles the suites drive the code
with:

- `Api` — records every `set_out` / `set_param` / `command_status` call, and can be told
  what `command_status` should answer (`wait_status`, `wait_sequence`, `wait_missing`,
  `wait_raises`).
- `Coordinator` — holds a payload as `data` and a `config_entry`.
- `Hass` — `async_add_executor_job` calls straight through; `keep_tasks` / `run_tasks`
  let a test hold a background confirmation and step through it.
- `FakeEntry` — keeps the background tasks it is handed, and cancels them on unload.
- `ConfigEntries` / `ConfigEntryData` — `hass.config_entries` recording every update and
  reload, and an entry with its data, options and update listeners. The `ConfigFlow` and
  `OptionsFlow` bases return their steps as plain dicts, and the selectors keep their
  config so a test can read a form's bounds. `OptionsFlow.config_entry` raises, as it
  does on Home Assistant 2024.11: the flow must find its entry through `handler`.

`conftest.py` patches `asyncio.sleep` to a no-op, so the seven `COMMAND_POLL_DELAYS`
waits cost nothing.

`requests` is **not** stubbed. It is the integration's own runtime dependency —
Home Assistant ships it, hence no `requirements` in `manifest.json`, and four modules import
it at module scope — and
`test_setparam.py` and `test_wait.py` drive the real library with a monkeypatched
session, which a fake exception hierarchy would not exercise. `voluptuous` is real too:
`test_options.py` fills the flows' forms in, which checks their defaults and required
fields rather than only that a schema exists.

Assertions go through the `check` fixture, not bare `assert`: it records every failure
and reports them together at the end, so one run tells you everything that broke rather
than only the first thing. A suite is one function taking `check` and ending on
`check.assert_ok()`.

The suites assert the firmware's rules as the codeowner supplied them, not what a
captured payload was seen doing — **no observed mode list ever matched the supplied
one**, so a test written from a capture would pin the wrong rule. When a rule genuinely
changes, the failing suite is the record of the old one: update it and say so, rather
than reading it as a regression.

What this does *not* cover: Home Assistant itself. Entity registration, the config
flow's UI, the coordinator's real scheduling and every HTTP call are stubbed. Before a
release, still install the component in a running Home Assistant and read the logs.

## The suites

| Suite | Covers |
| --- | --- |
| `test_access.py` | `access` thresholds from `SetOut.php`/`SetParam.php`: an absent level means unknown, never refused; the setpoint, switch, mode select and filtration speed all refuse locally below 10 with no round trip |
| `test_counters.py` | the four `_TotalTime` runtime sensors, each reading its own `params` key; a missing or misspelled key creates no entity |
| `test_dosed.py` | the four dosed volumes: running seconds x the pump's flow in tenths of a litre per hour, the counter coming from `params`, `outs[].totalTime` or `ExtraParams` depending on the out; the disinfectant's gate on `TraitMode`, which keeps bromine and electrolysis in hours; no entity without both figures, or on a flow of zero |
| `test_device.py` | `DeviceInfo` from `tabSW` / `tabHW` / `podSerial`; an absent field stays absent rather than the string `"None"` |
| `test_enabled.py` | `OUTS_DISABLED_BY_DEFAULT` on the switch and the mode select; the filtration speed and the sensors are untouched; disabled still means controllable |
| `test_filt.py` | the filtration's speed encoding — `2` is speed 2 in Manuel and the keep sentinel elsewhere; Manuel's range follows `PumpMaxSpeed`; the speed entity writes in Manuel only |
| `test_floc.py` | the flocculant's two modes, its Manuel that stops the pump, and its "Volume fixe" wording |
| `test_heat.py` | `params.HeaterMode` selecting the heating's modes and their names — mode 3 is "Régulé" on a heater and "Réchauffe" on a heat pump; no `HeaterMode` means read-only |
| `test_hybrid.py` | hybrid chlorine's single permitted mode, and the switch that is the real gain over it |
| `test_naming.py` | every entity class sets `has_entity_name`, so each is named after its pool |
| `test_modes.py` | the mode select in general: options offered, a reserved mode reported as `None`, `newState` = keep on a write, and the switch's refusals |
| `test_options.py` | the poll interval — default, clamping, junk in storage; the options form's bounds and the whole seconds it stores; reconfigure validating the new server on the same poolID, requiring the password again, and leaving the entry alone on a refusal; the update listener reloading on an interval change only; every new step and abort translated in both languages |
| `test_ph.py` | the pH corrector's modes, the `newState` each one sends, and the error text naming the entity as the user sees it |
| `test_resume.py` | the filtration's last-known speed: learned from polls, sent back on `turn_on`, restored after a restart, ignored when out of range |
| `test_robust.py` | 1.5.1: a write Klereo or the network refuses becomes a `HomeAssistantError` with `command_failed` and the server's reason, leaving no optimistic value and no confirmation; absent or null `probes`/`outs` and missing fields set up and read as `None`; the device's link following the entry's server |
| `test_runtime.py` | `_params_hours()` — seconds to hours, `duration` / `total_increasing`, and no entity on an absurd value |
| `test_setparam.py` | `set_param()`'s POST body against the PHP, the values refused before the round trip, the tenth-of-a-degree rounding, and that no `SetParam`/`SetOut` error message matches `AUTH_HINTS` |
| `test_setpoint.py` | the water setpoint entity: created only where `ConsigneEau` is a number, display not clamped by `SETPOINT_MIN`/`MAX` |
| `test_tasklife.py` | the confirmation task's life: owned by the config entry, cancelled on unload and on entity removal, and a second write abandoning the first |
| `test_trait.py` | `params.TraitMode` and the disinfectant's five families — mode 2 carries four labels and two state sets across them |
| `test_volume.py` | the water-volume sensor: disabled by default, read-only, absent when the payload has no `VolumeEau` |
| `test_wait.py` | `CommandStatus` polling: the `CommandSender.h` enum, `command_id()`, success keeping the optimistic value until the refresh, failure and timeout dropping it, and the cadence never exceeding `COMMAND_POLL_DELAYS` |
