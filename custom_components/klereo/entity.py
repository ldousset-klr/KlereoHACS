"""Shared device identity, so every entity of a pool groups under one device."""

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


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
