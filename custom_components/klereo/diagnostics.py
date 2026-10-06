"""Diagnostics: what Home Assistant received from Klereo, safe to attach to an issue.

Downloaded from the integration's page. Home Assistant adds its own version and
this integration's manifest; this adds the entry, how the polling is going, and
the pool's payload — by allowlist, not denylist.
"""
from homeassistant.components.diagnostics import async_redact_data

from .const import CONF_PASSWORD, CONF_USERNAME, DOMAIN

# The top-level keys of GetPoolDetails the integration reads, and so the ones
# worth looking at when something is wrong. The payload carries more — the
# owner's address, the installer, the billing — none of it of any use here, so
# rather than chase every personal field it may hold, only these are kept and
# the rest are listed by name. A new key the integration starts reading has to
# be added here to show up.
PAYLOAD_KEYS = (
    "idSystem", "poolNickname", "podSerial", "register", "device", "access",
    "tabSW", "tabHW", "PumpMaxSpeed", "probes", "outs", "IORename", "params",
    "ExtraParams",
)

# Kept, but still identifying the owner, the pod or the account: present as
# **REDACTED** so their absence is not mistaken for the cause of a problem.
# The entry's title is the pool's nickname.
TO_REDACT = {CONF_USERNAME, CONF_PASSWORD, "poolNickname", "podSerial", "register",
             "pin", "title"}


async def async_get_config_entry_diagnostics(hass, entry):
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    coordinator = runtime["coordinator"] if runtime else None
    data = coordinator.data if coordinator else None
    pool = other_keys = None
    if isinstance(data, dict):
        pool = {key: data[key] for key in PAYLOAD_KEYS if key in data}
        other_keys = sorted(key for key in data if key not in PAYLOAD_KEYS)
    return {
        "entry": async_redact_data({
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        }, TO_REDACT),
        "coordinator": None if coordinator is None else {
            "update_interval": coordinator.update_interval.total_seconds(),
            "last_update_success": coordinator.last_update_success,
            "last_exception": (repr(coordinator.last_exception)
                               if coordinator.last_exception else None),
        },
        "pool": async_redact_data(pool, TO_REDACT) if pool is not None else None,
        "pool_other_keys": other_keys,
    }
