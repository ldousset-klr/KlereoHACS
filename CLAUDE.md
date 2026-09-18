# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant custom integration (distributed via HACS) for Klereo swimming pool
controllers. The component lives in `custom_components/klereo/` and is copied as-is to
the same path under the Home Assistant host's `config/`. The root holds only `README.md`,
`hacs.json` (HACS reads it there, never inside the component) and `icon.png`. There is no
build system, no test suite, and no lint/CI configuration.

All source paths below are relative to `custom_components/klereo/`.

## Testing changes

There is no local test harness. The only way to exercise the code is to copy
`custom_components/klereo/` into a running Home Assistant's `config/custom_components/`,
restart HA, add the integration via the UI config flow (username / password / poolID),
and read the logs. Everything logs through `logging.getLogger(__name__)` at INFO/DEBUG, so raise the
`custom_components.klereo` logger to `debug` in `configuration.yaml` when debugging.

Bump `version` in `manifest.json` when publishing a release that HACS should pick up.
`hacs.json` declares the minimum Home Assistant version (2022.8.0, set by the use of
`async_forward_entry_setups`); raise it if newer HA APIs are adopted.

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
  Failures raise `KlereoAuthError` (bad credentials, refused JWT) or `KlereoError`
  (anything else) — never a raw `KeyError`/`IndexError`. The API also answers *some*
  failures with HTTP 200 and an error payload, so `_payload_error()` inspects the body;
  when that error text matches `AUTH_HINTS` it is treated like a 401. **Those hints are a
  heuristic** — no real expired-token payload has been observed yet, so confirm them
  against a live capture before relying on them.
- `__init__.py` — `async_setup_entry` builds the `KlereoAPI`, wraps `api.get_pool` in
  `hass.async_add_executor_job` (this is the bridge between HA's async world and the
  blocking `requests` calls), and drives a `DataUpdateCoordinator` polling every
  `UPDATE_INTERVAL` (300 s). Coordinator + api are stashed in
  `hass.data[DOMAIN][entry.entry_id]` for the platforms. `PLATFORMS = ["sensor", "switch"]`.
  The update callback maps `KlereoAuthError` to `ConfigEntryAuthFailed` (triggering the
  reauth flow) and `KlereoError`/`RequestException` to `UpdateFailed`.
- `entity.py` — `klereo_device_info()`, the single source of the device every entity of a
  pool attaches to (`identifiers={(DOMAIN, str(poolid))}`, named from `poolNickname`).
  Both platforms build it once in `async_setup_entry` and pass it to each entity. It only
  uses `DeviceInfo` keys available in HA 2021.12; `serial_number` (`podSerial`) would need
  2023.8, so bump `hacs.json` before adding it.
- `config_flow.py` — UI flow collecting username/password/poolID. `_test_credentials`
  performs a real `get_pool()` in the executor, so a bad login *and* a bad poolID are
  caught at setup time. `async_step_reauth`/`async_step_reauth_confirm` handle the
  `ConfigEntryAuthFailed` the coordinator raises. Form error keys (`invalid_auth`,
  `cannot_connect`) must exist in `strings.json` **and** `translations/*.json` — HA reads
  the latter at runtime, so adding a key to only one of them shows a raw slug in the UI.
  The entry's `unique_id` is the poolID, so a pool can only be configured once;
  `async_setup_entry` backfills it on entries created before that existed.
- `sensor.py` / `switch.py` — both are `CoordinatorEntity` subclasses created dynamically
  from the coordinator's first payload. Entities are keyed by the Klereo `index` field and
  re-scan `coordinator.data` on every property read rather than caching. `KlereoSensor`
  resolves its unit once in `__init__` and exposes `native_value`; `device_class` and
  `state_class` are kept as plain strings in `const.py` so no enum member missing from an
  older Home Assistant can break the import.

### Shape of the `GetPoolDetails.php` payload

`api.get_pool()` returns `response[0]`, and that dict is what `coordinator.data` holds.
The rest of the code depends on these keys:

- `idSystem` — pool id, used in entity naming (`klereo<poolid>probe<index>`, `klereo<poolid>out<index>`).
- `probes[]` — one sensor each; fields `index`, `type`, `filteredValue`, `filteredTime`.
  `type` selects the unit through `PROBE_TYPES` in `const.py`, keyed by the firmware's
  `e_TypeCapteurs` enum (0-15, the authoritative list — a type outside it logs a warning).
  Every mapped unit is confirmed against the firmware. `GENERIC` (10), `UNKNOWN` (15) and
  `TURBIDITE` (9) carry no unit on purpose. Type 7 carries both TAC and TH, which the
  firmware does not distinguish; its `°f` is the French degree of alkalinity/hardness, not
  Fahrenheit, and must never be given a temperature `device_class`. A `filteredValue` of
  `-1000` means the probe is absent or unreadable and becomes `None`.
- `params` is what identifies a probe's role: `EauCapteur`, `pHCapteur`, `TraitCapteur`
  and `PressionCapteur` hold probe *indexes*, and each probe's `seuilMin`/`seuilMax`
  mirror the matching `params` bounds (`EauMin/Max`, `pHMin/Max`, `OrpMin/Max`,
  `AirMin/Max`). That cross-check is how `PROBE_TYPES` was first derived, before the
  firmware enum confirmed it.
- `IORename[]` carries the user's own names: `ioType: 1` entries index into `outs[]`,
  `ioType: 2` into `probes[]`. This is what the README's auto-naming TODO needs; nothing
  reads it yet.
- `outs[]` — one switch each; fields `index`, `type`, `mode`, `status`, `realStatus`, `updateTime`.

Writes go through `SetOut.php` with `poolID`, `outIdx`, `newMode: 2` (manual) and
`newState` 0/1. Because a write is not reflected in coordinator data until the next poll,
`KlereoOut` keeps an optimistic `self._optimistic_state` (True/False/None) that `is_on`
prefers over `out['status']`. It is cleared in `_handle_coordinator_update()`, so fresh
server data always wins; a write also fires `coordinator.async_request_refresh()` so that
handover happens in seconds rather than at the next 300 s poll.

## Known rough edges (pre-existing, don't assume they are intentional)

- `KlereoOut.async_set_mode` / `KlereoAPI.set_device_mode` are stubs that only log, and
  `async_set_mode` is not registered as a service, so nothing can reach it.
- Entity names are the raw `klereo<id>probe<n>` scheme; the README lists auto-naming from
  the Klereo default names as a TODO.

## README TODOs worth knowing

The poolID is currently found by hand via browser devtools; the intended fix is to fetch it
from `GetIndex.php`. The README also carries a disclaimer that the integration is
community-driven and **not officially endorsed or supported by Klereo** — keep that framing
in any user-facing docs.
