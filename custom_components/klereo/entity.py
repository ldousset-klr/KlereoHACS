"""Shared device identity, so every entity of a pool groups under one device."""

from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


def klereo_device_info(pool_data, poolid) -> DeviceInfo:
    """Build the device all entities of this pool belong to.

    `serial_number` (podSerial) is simply not exposed yet; the minimum version
    hacs.json declares now covers it.
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
    return info
