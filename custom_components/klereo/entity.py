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
    # The pod firmware revision, when the payload carries it.
    pod_sw = pool_data.get("PodSW")
    if pod_sw is not None:
        info["sw_version"] = str(pod_sw)
    pod_serial = pool_data.get("podSerial")
    if pod_serial:
        info["serial_number"] = str(pod_serial)
    return info
