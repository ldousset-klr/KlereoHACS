# Klereo for Home Assistant

Unofficial Home Assistant integration for Klereo swimming pool controllers. It polls the
Klereo Connect cloud and exposes a pool's probes, outputs and filtration speed as entities.

Requires **Home Assistant 2024.11 or later**.

## What you get

One device per pool, named after its Klereo nickname, carrying:

- **A sensor per probe** — water and air temperature, pH, redox, pressure, flow, canister
  levels, cover position, salinity, alkalinity, chlorine. Each is published with the unit
  its type actually calls for, taken from the controller's own sensor table.
- **A switch per output** — lighting, filtration, pH corrector, disinfectant, heating and
  the auxiliaries.
- **The filtration speed**, on pools whose pump has more than one.
- **Diagnostic sensors** for the registration PIN and the device slot on the pod.

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

- **Only lighting and auxiliary outputs can be switched.** Filtration, pH corrector,
  disinfectant, heating, flocculant and hybrid chlorine report their state but refuse to
  be driven, until the write semantics for them are settled. That also makes the
  filtration speed read-only for now.
- **An output's mode is read-only.** It is visible as an entity attribute (*Manuel*,
  *Plages horaires*, *Régulé*…) but nothing can change it.
- **Water readings freeze while the filtration is off.** The controller does this on
  purpose — a measurement without circulation means nothing — so a sensor can sit hours
  behind. Compare the `Time` and `DirectTime` attributes to tell a settled reading from a
  stale one.
- The integration has no logo in Home Assistant yet; it is pending submission to the
  `home-assistant/brands` repository.

## Todo

- API documentation
- Expose more pool information
- A mode selector for the outputs that allow one

## Disclaimer

This integration developed for Home Assistant via HACS (Home Assistant Community Store) is provided **as-is**, without any warranties or guarantees of any kind, expressed or implied. Klereo and its developers cannot be held responsible for any damage, malfunction, or issues arising from the installation or usage of this integration.

Use of this integration is at your own risk. It is recommended to back up your Home Assistant configuration before installation. The integration is community-driven and is **not officially endorsed or supported by Klereo**.
