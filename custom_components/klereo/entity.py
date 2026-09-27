"""Shared device identity, so every entity of a pool groups under one device."""

import asyncio
import logging

from requests import RequestException

from homeassistant.helpers.device_registry import DeviceInfo

from .klereo_api import KlereoAPI, KlereoError
from .const import (ACCESS_COMMAND_MIN, ACCESS_PARAM_ANY, COMMAND_DONE,
                    COMMAND_POLL_DELAYS, COMMAND_STATUS, DOMAIN,
                    FILTRATION_OUT_INDEX, MAX_PUMP_SPEED,
                    TREATMENT_OUT_INDEXES,
                    OUT_MODE_NAME_OVERRIDES, OUT_MODE_STATES, OUT_MODES,
                    PAYLOAD_VARIANTS, filtration_mode_states)


LOGGER = logging.getLogger(__name__)


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


def klereo_access(pool_data):
    """The account's access level on this pool, or None if the payload omits it.

    GetIndex is documented as carrying it; whether GetPoolDetails does has not
    been confirmed against a capture. None is therefore a real answer and means
    *unknown*, never *refused*: a payload without the field must not lock
    anyone out of a pool they own.
    """
    access = pool_data.get("access")
    return access if isinstance(access, int) and not isinstance(access, bool) else None


def klereo_may_command(pool_data):
    """Whether the account may send commands at all, as far as we can tell.

    True when the level is unknown — the server is the authority, and refusing
    locally on a guess would be worse than a round trip that comes back with a
    clear message.
    """
    access = klereo_access(pool_data)
    return access is None or access >= ACCESS_COMMAND_MIN


def klereo_out_refusal(pool_data, index):
    """The translation key refusing a write to this out, or None if it may go.

    SetOut's own rule, and only its own: below level 10 nothing is allowed,
    and below 16 the water-treatment outs are refused while every other out
    goes through. Saying so here spares a round trip that comes back in French
    with no hint that the account is the reason.

    An unknown level allows the write, the server being the authority.
    """
    access = klereo_access(pool_data)
    if access is None:
        return None
    if access < ACCESS_COMMAND_MIN:
        return "account_read_only"
    if access < ACCESS_PARAM_ANY and index in TREATMENT_OUT_INDEXES:
        return "out_needs_full_access"
    return None


class KlereoCommandMixin:
    """Follows a queued write to its end without blocking the service call.

    Both write endpoints only queue: they answer a cmdID and the pod applies
    the command later. CommandStatus says where that cmdID has got to, and
    this polls it on COMMAND_POLL_DELAYS until the pod answers or the last
    delay runs out — as a background task, so no service call waits on it.

    That task is tied to the config entry and cancelled when it unloads, and a
    second write on the same entity cancels the first: a stale verdict must not
    outlive the value it was about.

    That also fixes the flicker the optimistic value used to have. The write
    no longer refreshes immediately, which would have replaced the optimistic
    value with a payload the pod had not updated yet; it refreshes once the
    command has landed, so the reading that arrives is the new one.
    """

    # The confirmation in flight, if any. One per entity: see _follow_command.
    _confirm_task = None

    def _clear_optimistic(self):
        """Drop whatever this entity is showing ahead of the payload."""
        raise NotImplementedError

    def _follow_command(self, reply, what):
        """Start the confirmation and return. Never awaited by a service call."""
        # A second write supersedes the first, whose verdict is about a value
        # nobody is showing any more — and whose _clear_optimistic() would
        # wipe the one the new write just set. Press a switch twice quickly
        # and that is exactly what used to happen.
        self._cancel_confirmation()

        coro = self._confirm_command(reply, what)
        entry = getattr(self.coordinator, "config_entry", None)
        if entry is None:
            # The coordinator is always built with one, so this is a guard
            # rather than a path: without an entry there is nothing to tie to.
            self._confirm_task = self.hass.async_create_task(coro)
            return
        # Tied to the config entry, which cancels its background tasks when it
        # unloads. Otherwise a reload or a shutdown mid-confirmation leaves the
        # task to write state onto an entity that no longer exists, and to
        # refresh a coordinator whose api has been dropped from hass.data.
        self._confirm_task = entry.async_create_background_task(
            self.hass, coro, f"{DOMAIN} confirm: {what}"
        )

    def _cancel_confirmation(self):
        """Drop the confirmation in flight, if there is one."""
        task = self._confirm_task
        self._confirm_task = None
        if task is not None and not task.done():
            task.cancel()

    async def async_will_remove_from_hass(self):
        # Belt and braces: the entry cancels its own tasks, but an entity can
        # also go on its own — a pool that stops reporting an out, say.
        self._cancel_confirmation()
        await super().async_will_remove_from_hass()

    async def _confirm_command(self, reply, what):
        cmd_id = KlereoAPI.command_id(reply)
        if cmd_id is None:
            LOGGER.debug("%s: no cmdID to follow, refreshing blind", what)
            await self.coordinator.async_request_refresh()
            return

        status, detail = None, None
        for delay in COMMAND_POLL_DELAYS:
            # Sleeping here rather than inside a request keeps the executor
            # thread free between asks, and lets the pod have its time.
            await asyncio.sleep(delay)
            try:
                row = await self.hass.async_add_executor_job(
                    self._api.command_status, cmd_id
                )
            except (KlereoError, RequestException) as err:
                LOGGER.warning("%s: could not read command %s: %s",
                               what, cmd_id, err)
                break
            if row is None:
                LOGGER.warning("%s: the server knows no command %s", what, cmd_id)
                break
            try:
                status = int(row.get("status"))
            except (TypeError, ValueError):
                LOGGER.warning("%s: command %s reported status %r",
                               what, cmd_id, row.get("status"))
                status = None
                break
            detail = row.get("detail")
            if status >= COMMAND_DONE:
                break

        self._confirm_task = None
        if status == COMMAND_DONE:
            LOGGER.debug("%s: command %s applied", what, cmd_id)
        else:
            if status is None:
                pass                     # already logged above
            elif status < COMMAND_DONE:
                # Not a failure: the pod has simply not answered yet, and we
                # stopped asking. The payload will carry it when it lands.
                LOGGER.info("%s: command %s still pending (%s)", what, cmd_id,
                            COMMAND_STATUS.get(status, status))
            else:
                LOGGER.error("%s: command %s failed — %s%s", what, cmd_id,
                             COMMAND_STATUS.get(status, f"status {status}"),
                             f" ({detail})" if detail else "")
            # In every case but success the optimistic value has outlived its
            # usefulness: whatever the payload says next is more trustworthy.
            self._clear_optimistic()
            self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
