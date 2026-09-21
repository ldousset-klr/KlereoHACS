"""Shared device identity, so every entity of a pool groups under one device."""

from homeassistant.helpers.device_registry import DeviceInfo

from .const import (DOMAIN, FILTRATION_OUT_INDEX, MAX_PUMP_SPEED,
                    OUT_MODE_NAME_OVERRIDES, OUT_MODE_STATES, OUT_MODES,
                    PAYLOAD_VARIANTS, filtration_mode_states)


def klereo_device_info(pool_data, poolid) -> DeviceInfo:
    """Build the device all entities of this pool belong to.

    Fields the payload may omit are only set when present, so a missing one
    leaves the device registry untouched instead of showing the string "None".
    """
    info = DeviceInfo(
        identifiers={(DOMAIN, str(poolid))},
        manufacturer="Klereo",
        name=pool_data.get("poolNickname") or f"Klereo pool #{poolid}",
        configuration_url="https://connect.klereo.fr",
    )
    # The firmware revision is tabSW, not PodSW: PodSW is the pod application
    # number (a plain integer), tabSW is the board software version ("212D").
    # tabHW is the board's hardware revision, which DeviceInfo has its own
    # field for — so it belongs here rather than among the diagnostic sensors
    # the way the PIN and the water volume do.
    for key, field in (("tabSW", "sw_version"),
                       ("tabHW", "hw_version"),
                       ("podSerial", "serial_number")):
        value = pool_data.get(key)
        if value:
            info[field] = str(value)
    return info


# IORename[].ioType. 3 and 4 were seen naming the two end states of a cover
# probe, on the same ioIndex as that probe, so matching on ioIndex alone would
# rename the probe itself "Ouverte". Always filter on ioType first.
IO_TYPE_OUT = 1
IO_TYPE_PROBE = 2


def klereo_io_names(pool_data, io_type):
    """Map ioIndex -> the name the user gave that out or probe in Klereo."""
    names = {}
    for entry in pool_data.get("IORename") or []:
        if entry.get("ioType") != io_type:
            continue
        name = (entry.get("name") or "").strip()
        if name:
            names[entry.get("ioIndex")] = name
    return names


def _payload_variant(pool_data, index):
    """The rules for an out whose kind a params key decides, or None.

    The heating reads params.HeaterMode and the disinfectant params.TraitMode:
    what the output is wired to, or what the pool is treated with, decides both
    the modes it takes and what they are called. A value the enum does not
    cover, one that means "none", and no params at all read alike — the kind is
    not established, so nothing is written.
    """
    spec = PAYLOAD_VARIANTS.get(index)
    if spec is None:
        return None
    params_key, variants = spec
    params = pool_data.get("params") or {}
    return variants.get(params.get(params_key))


def klereo_pump_max_speed(pool_data):
    """The pool's own top speed index, clamped to what SetOut accepts.

    0 is a real answer — a pool driving no pump speed — so only an absent or
    malformed field falls back to the protocol's ceiling.
    """
    max_speed = pool_data.get("PumpMaxSpeed")
    if not isinstance(max_speed, int):
        return MAX_PUMP_SPEED
    return min(max_speed, MAX_PUMP_SPEED)


def klereo_out_mode_states(pool_data, index):
    """{mode: ModeRule} for this out, or None if it is read-only.

    This is the single answer to both "may Home Assistant write this out" and
    "which modes may it offer": an out is writable exactly when its permitted
    states are known, and the keys are the modes, in the firmware's own order.

    Most outs answer from their index alone. Three answer from the payload: the
    heating and the disinfectant through PAYLOAD_VARIANTS, and the filtration,
    whose Manuel takes a speed index running up to the pool's own PumpMaxSpeed.
    """
    if index in PAYLOAD_VARIANTS:
        variant = _payload_variant(pool_data, index)
        return variant[0] if variant else None
    if index == FILTRATION_OUT_INDEX:
        return filtration_mode_states(klereo_pump_max_speed(pool_data))
    return OUT_MODE_STATES.get(index)


def klereo_out_mode_name(pool_data, index, mode):
    """The name an out gives one of its modes, or None if the mode is reserved.

    A mode number does not always carry the same label. Mode 2 is "Minuterie" on
    the switched outs, "Volume fixe" on the dosing pumps, "Temps fixe" on a
    bromine disinfectant and "Régulé température" on an electrolyser; mode 3 is
    "Régulé" on a dry-contact heater and "Réchauffe" on a heat pump. So the
    wording of the payload-driven outs depends on the payload, not just on the
    index. Everything user-facing goes through here rather than reading
    OUT_MODES, so an out never shows another out's wording.
    """
    if index in PAYLOAD_VARIANTS:
        variant = _payload_variant(pool_data, index)
        if variant is None:
            # Kind unknown: naming a mode would be guessing which table to read.
            return None
        states, names = variant
        if mode not in states:
            # Reserved on this kind of output, whatever it means elsewhere.
            return None
        if mode in names:
            return names[mode]
        return OUT_MODES.get(mode)
    override = OUT_MODE_NAME_OVERRIDES.get(index)
    if override and mode in override:
        return override[mode]
    return OUT_MODES.get(mode)
