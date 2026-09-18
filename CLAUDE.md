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
`hacs.json` declares the minimum Home Assistant version (2024.11.0, set by the
`config_entry` argument the coordinator is built with — it was added in that release and
raises `TypeError` on 2024.10 and earlier); raise it if newer HA APIs are adopted.

## Architecture

Cloud polling against the Klereo Connect PHP endpoints (`https://connect.klereo.fr/php`,
set in `const.py` as `KLEREOSERVER`).

- `klereo_api.py` — `KlereoAPI`, the only networking layer. Plain **synchronous**
  `requests`; it must never be called directly from the event loop. Auth is lazy: every
  authenticated call goes through `_post()`, which lazily calls `get_jwt()` (SHA-1 of the
  password POSTed to `GetJWT.php`), sends `Authorization: Bearer <jwt>`, and on a 401/403
  clears the token and replays the request **once** before `raise_for_status()`. Every
  request carries `timeout=HTTP_TIMEOUT` (30 s) so a hung server cannot pin an executor
  thread, and all of them share one `requests.Session` so the five endpoints stop paying
  for a TLS handshake each. Note `self.jwt` is mutated from executor threads: a poll and a
  switch press overlapping can both renew it, which costs a spare `GetJWT` but is
  otherwise harmless — there is no lock. `turn_on_device`/`turn_off_device` are thin wrappers over `set_out()`.
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
  `hass.data[DOMAIN][entry.entry_id]` for the platforms.
  `PLATFORMS = ["sensor", "switch", "number"]`.
  The update callback maps `KlereoAuthError` to `ConfigEntryAuthFailed` (triggering the
  reauth flow) and `KlereoError`/`RequestException` to `UpdateFailed`.
- `entity.py` — `klereo_device_info()`, the single source of the device every entity of a
  pool attaches to (`identifiers={(DOMAIN, str(poolid))}`, named from `poolNickname`).
  Both platforms build it once in `async_setup_entry` and pass it to each entity. Optional
  fields (`sw_version` from `PodSW`, `serial_number` from `podSerial`) are only set when
  the payload carries them, so a missing one is absent rather than the string `"None"`.
  `DeviceInfo` is imported from `helpers.device_registry`, its canonical home;
  `helpers.entity` only re-exports it.
- `config_flow.py` — UI flow collecting username/password/poolID. `_test_credentials`
  performs a real `get_pool()` in the executor, so a bad login *and* a bad poolID are
  caught at setup time. `async_step_reauth`/`async_step_reauth_confirm` handle the
  `ConfigEntryAuthFailed` the coordinator raises. Form error keys (`invalid_auth`,
  `cannot_connect`) must exist in `strings.json` **and** `translations/*.json` — HA reads
  the latter at runtime, so adding a key to only one of them shows a raw slug in the UI.
  The entry's `unique_id` is the poolID, so a pool can only be configured once;
  `async_setup_entry` backfills it on entries created before that existed.
- `number.py` — the filtration speed, the one out whose `status` is a speed index. It is
  created only when the pool declares `PumpMaxSpeed > 1`, so single-speed pools keep just
  their switch; the range is `0..min(PumpMaxSpeed, MAX_PUMP_SPEED)`, falling back to the
  protocol's 7 when the payload has no usable value. The switch over the same out stays,
  unchanged, so existing automations keep working — turning it on sends speed 1.
- `sensor.py` / `switch.py` — both are `CoordinatorEntity` subclasses created dynamically
  from the coordinator's first payload. Entities are keyed by the Klereo `index` field and
  re-scan `coordinator.data` on every property read rather than caching. Each entity keeps
  `_key` (`klereo<poolid>probe<index>`) separate from `_name`: **`unique_id` is built from
  `_key` and must never follow the name**, or renaming a probe in Klereo would orphan the
  entity and lose its history. `_name` is the `IORename` label when there is one, else
  `_key`. `KlereoSensor`
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
- `params` points at some probes: `EauCapteur`, `pHCapteur`, `TraitCapteur` and
  `PressionCapteur` hold probe *indexes*, and each probe's `seuilMin`/`seuilMax` mirror the
  matching `params` bounds (`EauMin/Max`, `pHMin/Max`, `OrpMin/Max`, `AirMin/Max`,
  `PressureMin/Max`). That cross-check is how `PROBE_TYPES` was first derived, before the
  firmware enum confirmed it. **`PressionCapteur` is unreliable**: a pool was seen with
  `PressionCapteur: -1` while carrying a working type 6 probe, so trust `probes[].type`,
  not these pointers. Probe dicts are not uniform either — flow probes carry `DebitK`/
  `debitO` where the others carry `calib1..3`.
- `IORename[]` carries the user's own names, read by `klereo_io_names()`: `ioType: 1`
  entries index into `outs[]`, `ioType: 2` into `probes[]`. `ioType: 3` and `4` were seen
  on the *same* `ioIndex` as a cover probe, naming its two end states ("Ouverte"/"Fermée"),
  so **always filter on `ioType` first** — matching `ioIndex` alone would rename that probe
  "Ouverte". Entries exist for indexes that have no probe or out, and are simply unused.
- `outs[]` — one switch each; fields `index`, `type`, `mode`, `status`, `realStatus`,
  `updateTime`. **`status` is not a boolean, and its meaning depends on the output**: on
  the filtration it is a variable-speed index, 0 (stopped) to 7; on every other output it
  is `0` off, `1` on, `2` *unknown*. So `is_on` returns `None` on a 2 it did not read from
  the filtration — reporting it as on or off would both be wrong. Roles look fixed by index rather
  than declared: on both captured pools, outs 1/2/3/4 `totalTime` matches `params`
  `Filtration_`, `PHMinus_`, `ElectroChlore_` and `Chauff_TotalTime`, which is what
  `FILTRATION_OUT_INDEX = 1` rests on. **`outs[].type` is not the role** — it is 0 on every
  output of one pool, and 8 on the disinfectant and the heater of the other. The codeowner
  confirmed it is *not* the firmware's `e_OutTypes` and has yet to establish what it does
  encode, so don't map it against that enum; like `mode`, it stays an attribute only.

Writes go through `SetOut.php` with `poolID`, `outIdx`, `newMode: 2` (manual) and
`newState`, which takes the same encoding as `status` above — so turning the filtration on
sends speed 1, and speeds 2-7 are reachable but not exposed by a plain switch. Because a write is not reflected in coordinator data until the next poll,
`KlereoOut` keeps an optimistic `self._optimistic_state` (True/False/None) that `is_on`
prefers over `out['status']`. It is cleared in `_handle_coordinator_update()`, so fresh
server data always wins; a write also fires `coordinator.async_request_refresh()` so that
handover happens in seconds rather than at the next 300 s poll.

## Known rough edges (pre-existing, don't assume they are intentional)

- An out's `mode` is read-only: it is exposed as an attribute but nothing can change it.
  The stubs that pretended to (`KlereoOut.async_set_mode`, `KlereoAPI.set_device_mode`)
  only logged and were unreachable, so they were removed. Implementing it needs the
  meaning of the `mode` values — 0, 1, 2, 3, 4 and 8 have been seen — and a service
  registered on the switch platform.

## README TODOs worth knowing

The poolID is currently found by hand via browser devtools; the intended fix is to fetch it
from `GetIndex.php`. The README also carries a disclaimer that the integration is
community-driven and **not officially endorsed or supported by Klereo** — keep that framing
in any user-facing docs.
