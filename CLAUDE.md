# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant custom integration (distributed via HACS) for Klereo swimming pool
controllers. The repository root **is** the component directory: files are installed to
`config/custom_components/klereo/` on the Home Assistant host. There is no package
subdirectory, no build system, no test suite, and no lint/CI configuration — the relative
imports (`from .const import ...`) only resolve once the files sit inside
`custom_components/klereo/`.

## Testing changes

There is no local test harness. The only way to exercise the code is to copy the repo
contents into a running Home Assistant's `config/custom_components/klereo/`, restart HA,
add the integration via the UI config flow (username / password / poolID), and read the
logs. Everything logs through `logging.getLogger(__name__)` at INFO/DEBUG, so raise the
`custom_components.klereo` logger to `debug` in `configuration.yaml` when debugging.

Bump `version` in `manifest.json` when publishing a release that HACS should pick up.

## Architecture

Cloud polling against the Klereo Connect PHP endpoints (`https://connect.klereo.fr/php`,
set in `const.py` as `KLEREOSERVER`).

- `klereo_api.py` — `KlereoAPI`, the only networking layer. Plain **synchronous**
  `requests`; it must never be called directly from the event loop. Auth is lazy: every
  authenticated call goes through `_post()`, which lazily calls `get_jwt()` (SHA-1 of the
  password POSTed to `GetJWT.php`), sends `Authorization: Bearer <jwt>`, and on a 401/403
  clears the token and replays the request **once** before `raise_for_status()`. Every
  request carries `timeout=HTTP_TIMEOUT` (30 s) so a hung server cannot pin an executor
  thread. `turn_on_device`/`turn_off_device` are thin wrappers over `set_out()`.
- `__init__.py` — `async_setup_entry` builds the `KlereoAPI`, wraps `api.get_pool` in
  `hass.async_add_executor_job` (this is the bridge between HA's async world and the
  blocking `requests` calls), and drives a `DataUpdateCoordinator` polling every
  `UPDATE_INTERVAL` (300 s). Coordinator + api are stashed in
  `hass.data[DOMAIN][entry.entry_id]` for the platforms. `PLATFORMS = ["sensor", "switch"]`.
- `config_flow.py` — single-step UI flow collecting username/password/poolID.
  `_test_credentials` is a **stub that always passes**, so bad credentials only fail later
  during the coordinator's first refresh.
- `sensor.py` / `switch.py` — both are `CoordinatorEntity` subclasses created dynamically
  from the coordinator's first payload. Entities are keyed by the Klereo `index` field and
  re-scan `coordinator.data` on every property read rather than caching.

### Shape of the `GetPoolDetails.php` payload

`api.get_pool()` returns `response[0]`, and that dict is what `coordinator.data` holds.
The rest of the code depends on these keys:

- `idSystem` — pool id, used in entity naming (`klereo<poolid>probe<index>`, `klereo<poolid>out<index>`).
- `probes[]` — one sensor each; fields `index`, `type`, `filteredValue`, `filteredTime`.
- `outs[]` — one switch each; fields `index`, `type`, `mode`, `status`, `realStatus`, `updateTime`.

Writes go through `SetOut.php` with `poolID`, `outIdx`, `newMode: 2` (manual) and
`newState` 0/1. Because a write is not reflected in coordinator data until the next poll,
`KlereoOut` keeps an optimistic `self._optimistic_state` (True/False/None) that `is_on`
prefers over `out['status']`. It is cleared in `_handle_coordinator_update()`, so fresh
server data always wins; a write also fires `coordinator.async_request_refresh()` so that
handover happens in seconds rather than at the next 300 s poll.

## Known rough edges (pre-existing, don't assume they are intentional)

- `KlereoSensor` hardcodes `device_class = "temperature"` and `°C` for *every* probe,
  including pH and redox probes. The real type is in `probe['type']`, currently only
  exposed as an attribute.
- `KlereoOut.async_set_mode` / `KlereoAPI.set_device_mode` are stubs that only log.
- Entity names are the raw `klereo<id>probe<n>` scheme; the README lists auto-naming from
  the Klereo default names as a TODO.
- `KlereoSensor` extends only `CoordinatorEntity` (not `SensorEntity`), unlike `KlereoOut`
  which extends both.

## README TODOs worth knowing

The poolID is currently found by hand via browser devtools; the intended fix is to fetch it
from `GetIndex.php`. The README also carries a disclaimer that the integration is
community-driven and **not officially endorsed or supported by Klereo** — keep that framing
in any user-facing docs.
