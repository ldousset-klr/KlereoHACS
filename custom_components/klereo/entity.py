"""Shared device identity, so every entity of a pool groups under one device."""

from homeassistant.helpers.device_registry import DeviceInfo

from .const import (DOMAIN, FILTRATION_OUT_INDEX, HEATER_OUT_INDEX,
                    HEATER_VARIANTS, MAX_PUMP_SPEED, OUT_MODE_NAME_OVERRIDES,
                    OUT_MODE_STATES, OUT_MODES, filtration_mode_states)


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
    tab_sw = pool_data.get("tabSW")
    if tab_sw:
        info["sw_version"] = str(tab_sw)
    pod_serial = pool_data.get("podSerial")
    if pod_serial:
        info["serial_number"] = str(pod_serial)
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


def _heater_variant(pool_data):
    """The heating output's rules on this pool, or None if it has none.

    params.HeaterMode says what the output actually drives. A value outside
    the enum, HEATER_NONE, or no params at all all mean the same thing here:
    the kind is not established, so nothing is written.
    """
    params = pool_data.get("params") or {}
    return HEATER_VARIANTS.get(params.get("HeaterMode"))


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

    Most outs answer from their index alone. Two answer from the payload: the
    heating, a heat pump taking four modes where a dry-contact heater takes
    two, and the filtration, whose Manuel takes a speed index running up to
    the pool's own PumpMaxSpeed.
    """
    if index == HEATER_OUT_INDEX:
        variant = _heater_variant(pool_data)
        return variant[0] if variant else None
    if index == FILTRATION_OUT_INDEX:
        return filtration_mode_states(klereo_pump_max_speed(pool_data))
    return OUT_MODE_STATES.get(index)


def klereo_out_mode_name(pool_data, index, mode):
    """The name an out gives one of its modes, or None if the mode is reserved.

    A mode number does not always carry the same label. Mode 2 is "Minuterie"
    on the switched outs and "Volume fixe" on the pH corrector; mode 3 is
    "Régulé" on a dry-contact heater and "Réchauffe" on a heat pump — so the
    heating output's wording depends on the payload, not just on its index.
    Everything user-facing goes through here rather than reading OUT_MODES, so
    an out never shows another out's wording.
    """
    if index == HEATER_OUT_INDEX:
        variant = _heater_variant(pool_data)
        if variant is None:
            # Kind unknown: naming a mode would be guessing which table to read.
            return None
        states, names = variant
        if mode not in states:
            # Reserved on this kind of heater, whatever it means elsewhere.
            return None
        if mode in names:
            return names[mode]
        return OUT_MODES.get(mode)
    override = OUT_MODE_NAME_OVERRIDES.get(index)
    if override and mode in override:
        return override[mode]
    return OUT_MODES.get(mode)
