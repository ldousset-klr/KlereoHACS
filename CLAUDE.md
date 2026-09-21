# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant custom integration (distributed via HACS) for Klereo swimming pool
controllers. The component lives in `custom_components/klereo/` and is copied as-is to
the same path under the Home Assistant host's `config/`. The root holds `README.md`,
`hacs.json` (HACS reads it there, never inside the component), `LICENSE` and
`.github/workflows/`. There is no
build system, no test suite, and no lint/CI configuration.

All source paths below are relative to `custom_components/klereo/`.

## Testing changes

There is no local test harness. The only way to exercise the code is to copy
`custom_components/klereo/` into a running Home Assistant's `config/custom_components/`,
restart HA, add the integration via the UI config flow (username / password / poolID),
and read the logs. Everything logs through `logging.getLogger(__name__)` at INFO/DEBUG, so raise the
`custom_components.klereo` logger to `debug` in `configuration.yaml` when debugging.

`.github/workflows/validate.yml` runs **hassfest** and the **HACS action** on every push
to `main`, every PR and weekly. hassfest is strict about `manifest.json`: keys must read
`domain`, `name`, then alphabetical, and an integration defining `async_setup` must also
define a `CONFIG_SCHEMA` — this one has neither, being config-entry only, and declares
`cv.config_entry_only_config_schema(DOMAIN)`. The HACS action additionally requires the
repository itself to carry a description, topics and a license, none of which live in the
tree. Its `brands` check is ignored permanently: that repository no longer accepts custom
integrations.

Bump `version` in `manifest.json` when publishing a release that HACS should pick up.
`hacs.json` declares the minimum Home Assistant version (2024.11.0, set by the
`config_entry` argument the coordinator is built with — it was added in that release and
raises `TypeError` on 2024.10 and earlier); raise it if newer HA APIs are adopted.

## Architecture

Cloud polling against the Klereo Connect PHP endpoints. The server is per config entry:
the `user` step offers `DEF_SERVER` (`https://connect.klereo.fr`) and accepts any other,
so a dev or staging server can be pointed at. `KlereoAPI._base_url()` trims it and appends
`KLEREO_PATH` (`/php`), tolerating a trailing slash or an already-typed `/php`. An entry
created before this existed has no `server` key and falls back to production, so nothing
migrates. **The credentials are sent wherever this points**, so treat a typo there as a
credential disclosure, not just a connection failure.

- `klereo_api.py` — `KlereoAPI`, the only networking layer. Plain **synchronous**
  `requests`; it must never be called directly from the event loop. Auth is lazy: every
  `get_index()`/`list_pools()` need no poolID — that is what lets the config flow list an
  account's pools before one is chosen, and why `poolid` is optional on the constructor.
  Every
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
  `PLATFORMS = ["sensor", "switch", "number", "select"]`.
  The update callback maps `KlereoAuthError` to `ConfigEntryAuthFailed` (triggering the
  reauth flow) and `KlereoError`/`RequestException` to `UpdateFailed`.
- `entity.py` — `klereo_device_info()`, the single source of the device every entity of a
  pool attaches to (`identifiers={(DOMAIN, str(poolid))}`, named from `poolNickname`).
  Both platforms build it once in `async_setup_entry` and pass it to each entity. Optional
  fields (`sw_version` from **`tabSW`**, the board software version like "212D" — *not*
  `PodSW`, which is the pod application number — and `serial_number` from `podSerial`) are
  only set when the payload carries them, so a missing one is absent rather than the
  string `"None"`. `DeviceInfo` has no free-form field, so the pool's `register.pin`, its
  `device` number and its `params.VolumeEau` water volume are published as **diagnostic
  sensors** instead (`INFO_SENSORS` in `sensor.py`), which is how Home Assistant surfaces
  extra device metadata on the device page. Each row is
  `(key, label, getter, icon, unit)`; a row whose getter returns `None` creates no entity,
  so a missing value is absent rather than shown as `"None"` — but `0` is a real answer
  and does create one. None carries a `device_class`, so the table's icon is the one shown,
  the same rule `KlereoSensor` follows. `device` is the slot on the physical pod: the two systems sharing a `podSerial`
  and a `pin` are device 0 and device 1.
  **The device is keyed on the poolID, and must stay that way**: one physical pod can serve
  several systems — two captured pools share a `podSerial` and a `register.pin` — so keying
  on the serial would merge them into a single device. Two HA devices showing the same
  serial is correct here, and the registry only enforces uniqueness on `identifiers`.
  `DeviceInfo` is imported from `helpers.device_registry`, its canonical home;
  `helpers.entity` only re-exports it.
- `config_flow.py` — the `user` step takes credentials only and calls `list_pools()`,
  then the `pool` step offers what the account holds, minus what is already configured,
  through a `SelectSelector` in dropdown mode — a combo box that filters as the user types,
  which `vol.In` does not, and a professional account can hold hundreds of pools. Options
  are pre-sorted by name case-insensitively, hence `sort=False`.
  A `KlereoError` there (not a `KlereoAuthError`, which is a real credential failure)
  routes to the `manual` step, where the poolID is typed as before — GetIndex being down
  must not block setup. `_test_credentials` still performs a real `get_pool()` in the
  executor, so a bad login *and* a bad poolID are caught before the entry is created. `async_step_reauth`/`async_step_reauth_confirm` handle the
  `ConfigEntryAuthFailed` the coordinator raises. Form error keys (`invalid_auth`,
  `cannot_connect`) must exist in `strings.json` **and** `translations/*.json` — HA reads
  the latter at runtime, so adding a key to only one of them shows a raw slug in the UI.
  The `user` step also takes the server, carried into the entry data and used by
  `list_pools()`, `_test_credentials()` and the coordinator alike, so a dev server is
  exercised end to end rather than only at setup.
  The entry's `unique_id` is the poolID, so a pool can only be configured once;
  `async_setup_entry` backfills it on entries created before that existed. Entry data keeps
  the same three keys, so nothing migrates.
- `number.py` — the filtration speed, the one out whose `status` is a speed index. It is
  created only when the pool declares `PumpMaxSpeed > 1`, so pools with no speed control
  keep just their switch; the range is `0..min(PumpMaxSpeed, MAX_PUMP_SPEED)`, resolved by
  `klereo_pump_max_speed()` which the filtration's own rules share. Values 0, 1
  and 3 have been seen and **0 is a real answer, not a missing one** — only an absent or
  non-integer field falls back to the protocol's 7. The switch over the same out stays,
  unchanged, so existing automations keep working — turning it on sends speed 1.
- `select.py` — one entity per writable out, its drive mode. Offered exactly where
  `klereo_out_mode_states()` answers — so every out has one, save a heating or
  disinfectant whose kind the payload does not name. The options are resolved **once, in `__init__`**: `HeaterMode`, `TraitMode` and
  `PumpMaxSpeed` describe how the pool is equipped, which is a reinstallation rather than
  something that changes under a poll. The write sends
  `OUT_STATE_KEEP` as `newState` **wherever the target mode accepts it**, so changing the
  mode normally leaves the output doing what it was doing; the pH corrector's Manuel is the
  exception, taking only "off", so selecting it stops the dosing. `current_option` returns `None` rather than a name when the out
  carries a mode outside its permitted list: a reserved value must be left alone, and Home
  Assistant rejects a state that is not among the options anyway.
- `sensor.py` / `switch.py` — both are `CoordinatorEntity` subclasses created dynamically
  from the coordinator's first payload. Entities are keyed by the Klereo `index` field and
  re-scan `coordinator.data` on every property read rather than caching. Each entity keeps
  `_key` (`klereo<poolid>probe<index>`) separate from `_name`: **`unique_id` is built from
  `_key` and must never follow the name**, or renaming a probe in Klereo would orphan the
  entity and lose its history. `_name` is the `IORename` label when there is one, else
  `_key`. `KlereoOut` is also a `RestoreEntity`, for the filtration alone: turning that
  out on has to name a speed, and **a stopped pump reports `status: 0`**, so the speed it
  was last running at is nowhere in the payload. `_learn_speed()` takes it from every poll
  that shows the pump running, `_on_state()` sends it back instead of `OUT_STATUS_ON`
  where the mode's rule says its states are speeds, and it is published as the `LastSpeed`
  attribute — which is also how `async_added_to_hass()` recovers it after a restart that
  happened while the pump was stopped. A speed that no longer fits the pool's
  `PumpMaxSpeed` is not in the rule's states and is ignored, falling back to speed 1.
  A sensor falls back once more before the key: `PROBE_LABELS` in `const.py`
  gives the controller's own name for each probe **index** (0-31). That table is keyed on
  the index, not the type, and the two disagree on a few installs — a type 10 generic at
  index 20 whose label reads "Température air 3" — so it is only ever a fallback, never
  applied over an `IORename` name. On the captured pools every mismatched slot carried a
  user name, so the conflict stays hidden. `OUT_LABELS` does the same for outs, and the
  speed entity in `number.py` names itself from it too.
  `KlereoSensor`
  resolves its unit once in `__init__` and exposes `native_value`. Icons come from
  `PROBE_ICONS` and `OUT_ICONS` in `const.py`, **only where the entity has no
  `device_class`**: where it has one, Home Assistant already picks a fitting icon and
  overriding it would also lose the state-aware variants. Every name there was checked
  against the Material Design Icons set — an unknown one renders blank; `device_class` and
  `state_class` are kept as plain strings in `const.py` so no enum member missing from an
  older Home Assistant can break the import.

### Shape of the `GetPoolDetails.php` payload

`api.get_pool()` returns `response[0]`, and that dict is what `coordinator.data` holds.
It varies a lot between installations — a controller may drive a boiler rather than a
pool, with `outs: []`, no `ExtraParams`, a probe reading -16 °C (a freezer) and a generic
probe the owner named "Luminosité (lux)". Assume every section can be empty or absent.
The rest of the code depends on these keys:

- `idSystem` — pool id, used in entity naming (`klereo<poolid>probe<index>`, `klereo<poolid>out<index>`).
- `probes[]` — one sensor each; fields `index`, `type`, `filteredValue`, `filteredTime`.
  The state reports `filteredValue`, the smoothed reading. **It freezes while the
  filtration is off** — one pool was seen with `filteredTime` 6207 against `directTime`
  603, its pressure probe reporting 2337 against a live 1216 — which is deliberate, since
  a water measurement without circulation means nothing, but it does mean a sensor can sit
  hours behind. `directValue`/`directTime` are exposed as attributes so the two can be
  compared.
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
  `PressureMin/Max`) — **usually**: one pool's pressure probe bounds 200..2400 against a
  `PressureMax` of 1100, so this is a hint, not an invariant. `params.HeaterMode` and
  `params.TraitMode` are read too, and decide what the heating and the disinfectant may be
  set to — see the writes section below. `params.VolumeEau`, the pool's water volume in
  m³, is read as well and published as a diagnostic sensor; it is **read-only**, having no
  `SetOut` equivalent and describing how the pool is built rather than anything Home
  Assistant may command. It is how `PROBE_TYPES` was
  first derived, before the firmware enum confirmed it. **`PressionCapteur` is unreliable**: a pool was seen with
  `PressionCapteur: -1` while carrying a working type 6 probe, though another points at
  its pressure probe correctly — so trust `probes[].type`, not these pointers. Probe dicts are not uniform either — flow probes carry `DebitK`/
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
  the filtration — reporting it as on or off would both be wrong. Not every pool exposes every out — one has
  `outs: []`, another only index 0, a lighting output. Roles are fixed by index rather than
  declared — confirmed by the firmware's own slot names in `OUT_LABELS`, index 1 being the
  filtration, which is what `FILTRATION_OUT_INDEX = 1` rests on and which matches the
  `totalTime` of outs 1/2/3/4 tracking `params` `Filtration_`, `PHMinus_`,
  `ElectroChlore_` and `Chauff_TotalTime`. Installations that are not pools reuse the
  slots — a boiler names out 0 "Circulateur" where the table reads "Éclairage". **`outs[].type` is not the role** — it is 0 on every
  output of one pool, and 8 on the disinfectant and the heater of the other. The codeowner
  confirmed it is *not* the firmware's `e_OutTypes` and has yet to establish what it does
  encode, so don't map it against that enum; like `mode`, it stays an attribute only.

Writes go through `SetOut.php` with `poolID`, `outIdx`, `newMode` and `newState`.
`newState` takes the same encoding as `status` above — so turning the filtration on
sends speed 1, and speeds 2-7 are reachable but not exposed by a plain switch. Because a write is not reflected in coordinator data until the next poll,
`KlereoOut` keeps an optimistic `self._optimistic_state` (True/False/None) that `is_on`
prefers over `out['status']`. It is cleared in `_handle_coordinator_update()`, so fresh
server data always wins; a write also fires `coordinator.async_request_refresh()` so that
handover happens in seconds rather than at the next 300 s poll.

`newMode` is an out's drive mode, named in `OUT_MODES` (0 Manuel, 1 Plages horaires,
2 Minuterie, 3 Régulé, 4 Synchronisé, 6 Maintenance, 8 Impulsion). **It used to be
hardcoded to 2**, so every write silently put its output into timer mode, including
outputs for which 2 is not even permitted. `set_out()` now takes it explicitly and has no
default; the switch and the speed entity pass the out's *current* mode through, so a write
changes the state and nothing else.

**The two fields are not independent**, and **the rules differ per output**:
`OUT_MODE_STATES` is keyed by out index, then by mode, and the codeowner supplies it one
output family at a time. The same mode number does not take the same states everywhere.

`2` — `OUT_STATE_KEEP`, the same number that reads back as *unknown* — usually means
"apply the mode and leave the output's state alone", which is what makes a mode change
possible without also commanding the output. On the **switched outs** (lighting and the
auxiliaries) every mode accepts it; Manuel, Minuterie, Maintenance and Impulsion take `0`
and `1` as well, while **Plages horaires and Synchronisé take nothing else**, the schedule
owning the output there.

The **filtration** (index 1) is where the encoding stops being uniform, and it is why a
mode's rule is a `ModeRule` naming what its states *mean* rather than a bare list. Its
Manuel takes a **speed index**, 0 to the pool's own `PumpMaxSpeed`; Plages horaires and
Régulé take the keep sentinel; Maintenance takes 0 (Arrêt) and 1 (Marche) and has no keep.
So `newState: 2` is the keep sentinel in two of its modes, **speed 2** in Manuel, and not
permitted at all in the fourth — one number, three meanings on one output, told apart only
by the mode. Hence `ModeRule(states, keep, speed)`: `keep` is the value that leaves the
output alone or `None`, and `speed` marks the states as speed indexes. Inferring either
from `states` would start the pump on a mode change, or let the speed control write a 2
the controller reads as "leave it alone".

The **heating output** (4) and the **disinfectant** (3) are payload-dependent for a
different reason: their rules come from what the pool is equipped with. `PAYLOAD_VARIANTS`
maps each to the `params` key that decides — `HeaterMode` and `TraitMode` — and to the
variants it selects, so a third such output is a line there rather than another special
case. `params.HeaterMode` says what the output drives — 1 a dry-contact heater,
2 and 4 a Klereo heat pump (K-LINK and ModBus), 3 HEAT_NOTARGET, 0 no heating. A heater
takes Manuel and Régulé; a heat pump takes Manuel, Auto, Refroidit and Réchauffe. Manuel
is stop-only on both, and every other mode takes `OUT_STATE_KEEP` alone. **Mode 3 is
"Régulé" on the heater and "Réchauffe" on the pump** — the same number on the same output,
named differently by what it is wired to. `HEATER_NONE`, a value outside the enum, and a
missing `HeaterMode` all read alike: the kind is not established, so the output stays
read-only and its modes go unnamed rather than being guessed from the wrong table.

The **disinfectant** reads `params.TraitMode` (the firmware's `e_Traitements`) the same
way, and its families barely resemble each other. Chlorine takes Manuel, Volume fixe and
Régulé; bromine adds Synchronisé filtration and calls mode 2 *Temps fixe*; oxygen matches
chlorine but names mode 3 *Régulé température*; an **electrolyser** — whatever bus it is
driven over — has no dosing mode at all, offering Manuel plus four regulation modes, and
uses mode 2 for *Régulé température*, where it takes the keep sentinel alone rather than
on/off. So mode 2 carries **four different labels and two different state sets** on this
one output, depending only on `TraitMode`. Mode 5 (*Choc*) exists nowhere else, which is
why `OUT_MODES` does not name it and the variant's own table does. `TRAIT_NONE`,
`TRAIT_IGNORE`, a value outside the enum and a missing `TraitMode` all leave the output
read-only.

That is why **nothing reads the mode tables directly**. `entity.klereo_out_mode_states()`
is the single answer to both "may this be written" and "which modes may it offer" — it
returns `None` for a read-only out and, otherwise, `{mode: ModeRule}` whose keys are the
modes in the firmware's order. `entity.klereo_out_mode_name()` is the matching
answer for wording. Both take `pool_data`, and there is no `WRITABLE_OUT_INDEXES`
constant any more: writability is a property of a pool *and* an out, not of an out alone.

The **dosing pumps** — the pH corrector (2) and the flocculant (8) — break the pattern
twice. Their Manuel accepts **only `0`**: a dosing pump put back under manual control is
stopped, it cannot be commanded on and it cannot keep its state, so selecting Manuel there
does stop the dosing, which is the firmware's rule and not the integration's choice. `KlereoOutMode._state_for()` therefore
sends `rule.keep` where the mode has one, the mode's single permitted state where it does
not (stopping the output), and otherwise **the out's current `status`** — which is how the
filtration keeps its speed across a move into Manuel, the protocol having no sentinel
there. A status outside the permitted list raises `out_mode_ambiguous_state` rather than
guessing. Their mode 2 is
also named **"Volume fixe"** rather than "Minuterie" — functionally identical, the
codeowner confirmed, only the label differs. The pH corrector adds Régulé to the pair; the
flocculant has no regulation and takes those two modes only.

`KlereoOut._writable_mode()` refuses a turn_on/turn_off the out's current mode does not
accept, with the `out_mode_no_switching` key, rather than sending a combination the
firmware does not define. **That is the codeowner's decision, not a fallback**:
forcing `0` (Manuel) would make a switch behave the way people expect, but it would also
pull the pH corrector, the disinfectant or the heater out of regulation and disturb the
water treatment. The accepted cost is that toggling a regulated output may appear to do
nothing, the regulator still owning its state — so don't "fix" an inert switch on such an
output by writing a mode.

**Every output now carries its rules.** Lighting (0), the filtration (1), the pH corrector
(2), the flocculant (8), hybrid chlorine (15) and the auxiliaries (5-7, 9-14) answer from
their index; the heating (4) and the disinfectant (3) answer from the payload and stay
read-only while their `params` key names no kind. So `out_read_only` is no longer a
property of an output but of a pool that has not said what it is equipped with — it still
lives in the `exceptions` section of `strings.json` and both translations, and an out that
raises it still reports state.

Hybrid chlorine takes **one mode and no other**, Volume fixe, so its select offers a single
option: it reports the mode and can only re-assert it. The switch over the same out is the
real gain, that mode accepting 0, 1 and keep.

**The filtration speed entity is writable too, in Manuel only.** `number.py` looks up the
out's current mode and refuses with `out_speed_not_settable` unless `rule.speed` is set —
not merely unless the value is permitted, since in Plages horaires the permitted 2 is the
keep sentinel and Maintenance's 0/1 are off and on. Writing either from a speed control
would send a number the controller reads as something else.

The modes an out permits are the keys of its rules — `OUT_MODE_STATES`, the tables
`PAYLOAD_VARIANTS` selects, or `filtration_mode_states()` — so the list and the states can
never disagree: lighting and auxiliaries take 0/1/2/4/6/8, the filtration 0/1/3/6, the pH
corrector 0/2/3, the flocculant 0/2, hybrid chlorine 2 alone, a dry-contact heater 0/3, a
heat pump 0/1/2/3, a chlorine or oxygen disinfectant 0/2/3, a bromine one 0/2/3/4 and an
electrolyser 0/2/3/4/5.

The `(0, 3)` once recorded for the disinfectant was wrong in every direction, and it is
gone: chlorine and oxygen take 0/2/3, bromine 0/2/3/4, an electrolyser 0/2/3/4/5. That
list had also covered the pH corrector and the flocculant, which turned out to take
`(0, 2, 3)` and `(0, 2)` — three outputs, three contradictions. Hybrid chlorine had 2/3
*observed* on it and takes 2 alone. **No observed list ever matched the supplied one**,
which is the standing reason not to infer a rule from a capture. Values outside a rule's
list are reserved and must be left alone where an out already carries one.

## Known rough edges (pre-existing, don't assume they are intentional)

- A heating or disinfectant whose `params` key names no kind gets no `select` and no
  write; its mode is visible as the switch's `Mode`/`ModeName` attributes only. No output
  is unconditionally read-only any more.
- `ModeName` reports a reserved mode's generic name where the out's rules are static — a
  hybrid chlorine somehow sitting in mode 0 reads "Manuel", though only Volume fixe is
  permitted there. The payload-driven outs return `None` instead, the table to read being
  unknown. The `select` refuses the value either way, so this only affects the attribute.
- A filtration never seen running since Home Assistant started, and with no restored
  state, still turns on at speed 1. There is nowhere else to learn a speed from: a stopped
  pump reports `status: 0` and the payload keeps no history.

### Shape of the `GetIndex.php` payload

Same `{"status": "ok", "response": [...]}` envelope, one entry per system the account can
see, carrying `idSystem` and `poolNickname` plus a summary of the system (`probes`,
`outsmodes`, `pin`, `compta`, `proID`, `suspended`, `access`). `list_pools()` keeps only
the id and the name. `suspended` is deliberately *not* filtered on — the codeowner's call:
a suspended system stays in the picker and fails later at `GetPoolDetails` with a clear
message, rather than vanishing with no explanation.

## README TODOs worth knowing

The integration's **logo** lives in `custom_components/klereo/brand/`. Since Home
Assistant 2026.3 a custom integration ships its own brand images there and they take
priority over the CDN; `home-assistant/brands` no longer accepts custom integrations, so
`ignore: brands` in the workflow is permanent rather than pending a submission. Supported
names are `icon.png`, `logo.png`, their `@2x` variants and a `dark_` prefix for each;
`icon.png` (256x256) and `icon@2x.png` (512x512) are present, the first downscaled from
the second so the two frame the artwork identically — Home Assistant picks one by display
density, and a separately exported pair made the logo change size between them. Releases
before 2026.3 ignore the directory and show a placeholder. Entity icons are a separate
mechanism entirely, see `PROBE_ICONS`/`OUT_ICONS`.

The README carries a disclaimer that the integration is
community-driven and **not officially endorsed or supported by Klereo** — keep that framing
in any user-facing docs.
