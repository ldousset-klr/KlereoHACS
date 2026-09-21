# Klereo for Home Assistant

Unofficial Home Assistant integration for Klereo swimming pool controllers. It polls the
Klereo Connect cloud and exposes a pool's probes, outputs, filtration speed and output
modes as entities.

Requires **Home Assistant 2024.11 or later**.

## What you get

One device per pool, named after its Klereo nickname, carrying:

- **A sensor per probe** — water and air temperature, pH, redox, pressure, flow, canister
  levels, cover position, salinity, alkalinity, chlorine. Each is published with the unit
  its type actually calls for, taken from the controller's own sensor table.
- **A switch per output** — lighting, filtration, pH corrector, disinfectant, heating and
  the auxiliaries.
- **The filtration speed**, on pools whose pump has more than one. Settable while the
  filtration is in *Manuel*; in the other modes the schedule or the regulator owns the
  pump and the control says so rather than sending a value the controller would read as
  something else.
- **A mode selector** on each output you can drive, offering what that particular output
  accepts: *Manuel*, *Plages horaires*, *Minuterie*, *Synchronisé*, *Maintenance* and
  *Impulsion* on lighting and the auxiliaries; *Manuel*, *Plages horaires*, *Régulé* and
  *Maintenance* on the filtration; *Manuel*, *Volume fixe* and *Régulé* on the pH corrector
  and *Manuel* and *Volume fixe* on the flocculant; *Manuel* and *Régulé* on a heater, or
  *Manuel*, *Auto*, *Refroidit* and *Réchauffe* when the heating output drives a Klereo
  heat pump; and on the disinfectant, whatever the pool is treated with — chlorine, bromine,
  oxygen or an electrolyser each offer their own list. Hybrid chlorine accepts one mode
  only, *Volume fixe*, so its selector shows a single option. Changing the mode leaves the
  output doing whatever it was doing — including the filtration, which keeps its speed — except
  *Manuel* on the dosing pumps, the disinfectant and the heating, which stop them, the
  controller allowing nothing else there.
- **Diagnostic sensors** for the registration PIN, the device slot on the pod and the
  pool's water volume in m³. All three are read-only. The water volume ships **disabled**,
  being a fixed property of the pool rather than something to record every five minutes —
  enable it on the device page if you want it.

Entities are named after the names you set in Klereo. Anything you never renamed falls
back to the controller's own name for that slot — *Température eau*, *Capteur pH*,
*Filtration* — rather than an opaque index.

Data refreshes every 5 minutes.

## Installation

**Via HACS** — add this repository as a custom repository (category: *Integration*),
install it, then restart Home Assistant.

**Manually** — copy `custom_components/klereo/` into your Home Assistant
`config/custom_components/` directory, then restart Home Assistant.

## Configuration

Add the integration from *Settings > Devices & Services > Add Integration > Klereo*,
enter your Klereo credentials, and pick your pool from the list. Nothing else is needed:
the pool ID is read from your account.

Add the integration again to set up a second pool.

If the pool list cannot be retrieved, setup falls back to asking for the **poolID**, which
you can read from https://connect.klereo.fr/php/GetIndex.php

The *Server* field on the first screen exists for testing against another Klereo instance.
Leave it alone unless you know why you are changing it — **your credentials are sent to
whatever address it holds**.

## Current limitations

- **The heating and the disinfectant cannot be driven when the controller does not say
  what the pool is equipped with** — no heating or no treatment, or a `HeaterMode` or
  `TraitMode` the integration does not recognise. They report their state and refuse to be
  written. Every other output can be driven.
- **Turning the filtration on from the switch resumes its last known speed** — the one it
  was last seen running at, visible as the switch's `LastSpeed` attribute and remembered
  across restarts. It falls back to speed 1 if the pump has not been seen running since
  the integration was set up, a stopped pump reporting no speed at all.
- **The mode selector only covers the outputs you can switch.** On the others the mode is
  still visible as an entity attribute (*Manuel*, *Plages horaires*, *Régulé*…) but
  nothing can change it.
- **Some modes refuse a plain on/off, and say so.** The schedule owns the output in
  *Plages horaires* and *Synchronisé*, the regulator owns it in *Régulé*, *Auto*,
  *Refroidit* and *Réchauffe*, and the dosing pumps and the heating in *Manuel* can only be
  stopped — in each case the controller defines no such command and the switch reports an
  error instead of sending one. Change the mode first, with the mode selector.
- **Water readings freeze while the filtration is off.** The controller does this on
  purpose — a measurement without circulation means nothing — so a sensor can sit hours
  behind. Compare the `Time` and `DirectTime` attributes to tell a settled reading from a
  stale one.
- **The logo needs Home Assistant 2026.3 or later.** It ships in
  `custom_components/klereo/brand/`, which older releases ignore; they fall back to a
  placeholder.

## The Klereo Connect API

Undocumented and unofficial — everything below was established from live captures and from
the firmware's own enums. **Klereo may change it without notice.**

Base URL `https://connect.klereo.fr/php`. Every call is a `POST` with form-encoded
parameters, and every response is JSON.

### Authenticating

`GetJWT.php` takes the credentials and returns a bearer token:

| parameter | value |
|---|---|
| `login` | account name |
| `password` | **SHA-1 of the password, lowercase hex** — never the password itself |
| `version` | client version string, e.g. `100-HA` |
| `app` | `api` |

```bash
JWT=$(curl -s -X POST https://connect.klereo.fr/php/GetJWT.php \
  -d "login=$USER" \
  -d "password=$(printf '%s' "$PASSWORD" | sha1sum | cut -d' ' -f1)" \
  -d "version=100-HA&app=api" | python3 -c 'import sys,json;print(json.load(sys.stdin)["jwt"])')
```

Every other call carries `Authorization: Bearer <jwt>`. The token's lifetime is not
documented; treat a 401 or 403 as "renew and retry once".

### Endpoints

| endpoint | parameters | returns |
|---|---|---|
| `GetJWT.php` | see above | `{"jwt": "…"}` |
| `GetIndex.php` | none | every system the account can see |
| `GetPoolDetails.php` | `poolID`, `lang` | one system in full |
| `SetOut.php` | `poolID`, `outIdx`, `newMode`, `newState` | acknowledgement |

### Response envelope

```json
{"status": "ok", "response": [ … ]}
```

`response` is always a list, even for a single system. **A failure can arrive with HTTP
200** and a `status` other than `ok`, so the status code alone is not enough to tell
success from failure.

`GetIndex.php` returns one entry per system with `idSystem`, `poolNickname`, `suspended`,
`access` and a summary. `GetPoolDetails.php` returns one entry, the whole system.

### `probes[]`

| field | meaning |
|---|---|
| `index` | probe slot, 0-31; the slot determines what the probe is for |
| `type` | sensor type, see below |
| `filteredValue` | the smoothed reading — **what you should display** |
| `filteredTime` | age of that reading |
| `directValue` / `directTime` | the raw reading and its age |

`filteredValue` freezes while the filtration is off, by design: a water measurement
without circulation is meaningless. It can then sit hours behind `directValue`. A value of
**`-1000` means the probe is absent or unreadable**, not a measurement.

`type` follows the firmware's `e_TypeCapteurs`:

| | | | | | |
|---|---|---|---|---|---|
| 0 plant room °C | 1 air °C | 2 level % | 3 pH | 4 redox mV | 5 water °C |
| 6 pressure mbar | 7 TAC/TH °f | 8 salinity g/L | 9 turbidity | 10 generic | 11 flow m³/h |
| 12 canister % | 13 cover % | 14 chlorine mg/L | 15 unknown | | |

Types 9, 10 and 15 carry no unit: the controller does not know the quantity. Type 7 covers
both alkalinity and hardness without distinguishing them.

### `outs[]`

| field | meaning |
|---|---|
| `index` | output slot, 0-15; **the slot is the role** |
| `status` | see below — *not* a boolean |
| `realStatus` | the state actually reached |
| `mode` | how the output is driven |

Roles by index: 0 lighting, 1 filtration, 2 pH corrector, 3 disinfectant, 4 heating,
5-7 and 9-14 auxiliaries, 8 flocculant, 15 hybrid chlorine.

`status` means different things depending on the output:

- **on the filtration**, a variable-speed index from 0 (stopped) to 7;
- **on every other output**, `0` off, `1` on, **`2` unknown**.

`mode`: 0 Manuel, 1 Plages horaires, 2 Minuterie, 3 Régulé, 4 Synchronisé, 6 Maintenance,
8 Impulsion. Other values are reserved and must be left alone where an output carries one.
Lighting and auxiliaries accept 0/1/2/4/6/8; the regulated outputs (pH, disinfectant,
flocculant, heating) accept 0 and 3 only.

### Writing

`SetOut.php` takes `newState` in the same encoding as `status`, and `newMode` in the same
encoding as `mode`. **`newMode` is not optional**: whatever you send becomes the output's
mode, so send the output's current mode unless you actually intend to change how it is
driven.

The two are not independent — each mode accepts only certain states, and **the rules
differ from one output to the next**. Lighting and the auxiliaries:

| `newMode` | accepted `newState` |
| --- | --- |
| 0 Manuel | 0 off, 1 on, 2 keep |
| 1 Plages horaires | 2 keep |
| 2 Minuterie | 0 off, 1 on, 2 keep |
| 4 Synchronisé | 2 keep |
| 6 Maintenance | 0 off, 1 on, 2 keep |
| 8 Impulsion | 0 off, 1 on, 2 keep |

The dosing pumps — the pH corrector, and the flocculant without the last row:

| `newMode` | accepted `newState` |
| --- | --- |
| 0 Manuel | 0 off **only** |
| 2 Volume fixe | 0 off, 1 on, 2 keep |
| 3 Régulé | 2 keep — pH corrector only |

Mode 2 is the same mechanism in both tables; the controller just calls it *Minuterie* on
the switched outputs and *Volume fixe* on the dosing pumps.

The disinfectant, where `params.TraitMode` decides which list applies. Note mode 2 is a
dosing mode on chlorine, bromine and oxygen but a **regulation** mode on an electrolyser,
taking nothing but keep:

| `TraitMode` | treatment | `newMode` | accepted `newState` |
| --- | --- | --- | --- |
| 1 | chlorine | 0 Manuel | 0 off **only** |
| | | 2 Volume fixe | 0 off, 1 on, 2 keep |
| | | 3 Régulé | 2 keep |
| 4 | oxygen | 0 Manuel | 0 off **only** |
| | | 2 Volume fixe | 0 off, 1 on, 2 keep |
| | | 3 Régulé température | 2 keep |
| 5 | bromine | 0 Manuel | 0 off **only** |
| | | 2 Temps fixe | 0 off, 1 on, 2 keep |
| | | 3 Régulé | 2 keep |
| | | 4 Synchronisé filtration | 2 keep |
| 2, 3, 6, 8 | electrolyser | 0 Manuel | 0 off **only** |
| | | 2 Régulé température | 2 keep |
| | | 3 Régulé redox | 2 keep |
| | | 4 Synchronisé filtration | 2 keep |
| | | 5 Choc | 2 keep |

`TraitMode` 0 and 7 mean no treatment the integration can drive.

Hybrid chlorine accepts mode 2 (*Volume fixe*) and nothing else, with 0 off, 1 on and
2 keep.

The heating output, where `params.HeaterMode` decides which of the two applies:

| `HeaterMode` | what it drives | `newMode` | accepted `newState` |
| --- | --- | --- | --- |
| 1, 3 | dry-contact heater | 0 Manuel | 0 off **only** |
| | | 3 Régulé | 2 keep |
| 2, 4 | Klereo heat pump (K-LINK, ModBus) | 0 Manuel | 0 off **only** |
| | | 1 Auto | 2 keep |
| | | 2 Refroidit | 2 keep |
| | | 3 Réchauffe | 2 keep |

`HeaterMode: 0` means no heating at all. Note mode 3 is *Régulé* on a heater and
*Réchauffe* on a heat pump: the same number on the same output, named by what it is wired
to.

And the filtration, where `newState` changes meaning from one mode to the next:

| `newMode` | accepted `newState` |
| --- | --- |
| 0 Manuel | 0 stopped, 1..`PumpMaxSpeed` — a **speed index** |
| 1 Plages horaires | 2 keep |
| 3 Régulé | 2 keep |
| 6 Maintenance | 0 off, 1 on |

`newState: 2`, written rather than read, does not mean *unknown* but **"apply the mode and
leave the output's state as it is"** — which is how a mode is changed without also
commanding the output. Most modes take it; the dosing pumps' and the heating's *Manuel* do
not, so selecting that mode necessarily stops them.

**On the filtration the same 2 means three different things**: keep in *Plages horaires*
and *Régulé*, **speed 2** in *Manuel*, and nothing at all in *Maintenance*, which does not
accept it. Only the mode tells them apart, so read the table above rather than assuming.

The disinfectant is listed as accepting modes 0 and 3, but that list predates the
per-output tables above, and the two outputs it also covered — the pH corrector and the
flocculant — turned out to accept 0/2/3 and 0/2. It has been wrong twice, in both
directions, so treat it as unconfirmed.

A write is not reflected in `GetPoolDetails.php` until the controller has polled, so expect
a lag of seconds before a read confirms it.

## Todo

- Expose more pool information
- Writing the outputs that are still read-only, and a mode selector on them

## Disclaimer

This integration developed for Home Assistant via HACS (Home Assistant Community Store) is provided **as-is**, without any warranties or guarantees of any kind, expressed or implied. Klereo and its developers cannot be held responsible for any damage, malfunction, or issues arising from the installation or usage of this integration.

Use of this integration is at your own risk. It is recommended to back up your Home Assistant configuration before installation. The integration is community-driven and is **not officially endorsed or supported by Klereo**.
