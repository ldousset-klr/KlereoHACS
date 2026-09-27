"""Just enough Home Assistant for the component to import and run.

The integration is a thin layer over tables and rules, and those are what the
suites check. Standing up the real Home Assistant to reach them would cost a
heavy dependency and a slow test run for no extra coverage, so this module
supplies the handful of base classes and helpers `custom_components/klereo`
imports, and nothing else.

Two of them are modelled a little more closely, because tests turned on the
difference. `FakeEntry` keeps the background tasks handed to it and cancels
them on unload, as `ConfigEntry` does; `_Handle` stands in for `asyncio.Task`,
cancellable and interrogable, so a test can assert a confirmation was dropped
rather than merely that it did not run.
"""

import sys, types, asyncio

def _mod(name):
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m

for pkg in ('homeassistant', 'homeassistant.components', 'homeassistant.helpers'):
    m = _mod(pkg)
    m.__path__ = []          # make them packages, so submodules resolve

ce = _mod('homeassistant.config_entries')
ce.ConfigEntry = object

cv = _mod('homeassistant.helpers.config_validation')
cv.config_entry_only_config_schema = lambda domain: None
import homeassistant.helpers as _h
_h.config_validation = cv

class _Entity:
    hass = None
    _attr_device_info = None
    _attr_icon = None
    def async_write_ha_state(self): pass
    async def async_will_remove_from_hass(self): pass

m = _mod('homeassistant.components.select');  m.SelectEntity = type('SelectEntity', (_Entity,), {})
m = _mod('homeassistant.components.switch');  m.SwitchEntity = type('SwitchEntity', (_Entity,), {})
m = _mod('homeassistant.components.number');  m.NumberEntity = type('NumberEntity', (_Entity,), {})
m = _mod('homeassistant.components.sensor');  m.SensorEntity = type('SensorEntity', (_Entity,), {})

import enum
class EntityCategory(enum.Enum):
    DIAGNOSTIC = 'diagnostic'
    CONFIG = 'config'
hc = _mod('homeassistant.const'); hc.EntityCategory = EntityCategory

core = _mod('homeassistant.core')
core.callback = lambda f: f
core.HomeAssistant = object

exc = _mod('homeassistant.exceptions')
class ServiceValidationError(Exception):
    def __init__(self, translation_domain=None, translation_key=None,
                 translation_placeholders=None):
        self.key = translation_key
        self.placeholders = translation_placeholders or {}
        super().__init__(f"{translation_key}: {self.placeholders}")
exc.ServiceValidationError = ServiceValidationError

upd = _mod('homeassistant.helpers.update_coordinator')
class CoordinatorEntity:
    def __init__(self, coordinator): self.coordinator = coordinator
    def _handle_coordinator_update(self): pass
    async def async_will_remove_from_hass(self): pass
upd.CoordinatorEntity = CoordinatorEntity
upd.DataUpdateCoordinator = object
class UpdateFailed(Exception): pass
upd.UpdateFailed = UpdateFailed
exc.ConfigEntryAuthFailed = type('ConfigEntryAuthFailed', (Exception,), {})

rs = _mod('homeassistant.helpers.restore_state')
class RestoreEntity:
    _restored = None                 # test hook: the State to hand back
    async def async_added_to_hass(self): pass
    async def async_get_last_state(self): return self._restored
rs.RestoreEntity = RestoreEntity

class State:
    def __init__(self, attributes): self.attributes = attributes

dr = _mod('homeassistant.helpers.device_registry')
dr.DeviceInfo = dict

class FakeEntry:
    """Comme ConfigEntry : garde ses tâches de fond et les annule au unload."""
    entry_id = 'e'
    def __init__(self): self.tasks = []
    def async_create_background_task(self, hass, coro, name, eager_start=True):
        t = hass.async_create_task(coro)
        self.tasks.append(t)
        return t
    def unload(self):
        for t in self.tasks:
            if hasattr(t, 'cancel') and not t.done(): t.cancel()
        self.tasks.clear()

class Coordinator:
    def __init__(self, data):
        self.data = data
        self.config_entry = FakeEntry()
    async def async_request_refresh(self): pass

LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(LOOP)


def run(coro):
    """Drive a coroutine to completion on the suites' shared loop."""
    return LOOP.run_until_complete(coro)


class _Handle:
    """Un ersatz de asyncio.Task : annulable, interrogeable, exécutable après coup."""
    def __init__(self, coro): self.coro = coro; self.cancelled = False; self._done = coro is None
    def cancel(self): self.cancelled = True; self.close()
    def done(self): return self._done or self.cancelled
    def close(self):
        if self.coro is not None: self.coro.close(); self.coro = None
        self._done = True

class Hass:
    def __init__(self): self.tasks = []
    async def async_add_executor_job(self, fn, *args): return fn(*args)
    keep_tasks = False
    def async_create_task(self, coro):
        # Le vrai HA planifie. Ici : un test qui veut observer la confirmation
        # met keep_tasks=True puis appelle run_tasks(); les autres n'en ont pas
        # besoin, et fermer la coroutine évite un RuntimeWarning parasite.
        if self.keep_tasks:
            h = _Handle(coro); self.tasks.append(h); return h
        coro.close()
        return _Handle(None)
    def run_tasks(self):
        """Run the confirmations this Hass was handed, oldest first."""
        loop = LOOP
        while self.tasks:
            h = self.tasks.pop(0)
            if h.cancelled: h.close(); continue
            loop.run_until_complete(h.coro)
            h._done = True

class Api:
    def __init__(self): self.calls = []
    def set_out(self, outIdx, state, mode):
        self.calls.append(('set_out', outIdx, state, mode))
        return {'status':'ok','response':[{'cmdID':77,'poolID':115}]}
    wait_status = 9          # COMMAND_DONE par défaut
    wait_detail = None
    wait_raises = None
    wait_sequence = None     # statuts rendus l'un après l'autre, puis wait_status
    wait_missing = False     # le serveur ne connaît pas ce cmdID
    def command_status(self, cmd_id):
        self.calls.append(('command_status', cmd_id))
        if self.wait_raises: raise self.wait_raises
        if self.wait_missing: return None
        st = self.wait_status
        if self.wait_sequence:
            st = self.wait_sequence.pop(0)
        return {'cmdID': cmd_id, 'status': st,
                'startTime': '2026-09-27 12:00:00',
                'updateTime': '2026-09-27 12:00:01', 'detail': self.wait_detail}
    @staticmethod
    def command_id(reply):
        from klereo.klereo_api import KlereoAPI
        return KlereoAPI.command_id(reply)
    def set_param(self, paramID, value, label=None):
        self.calls.append(('set_param', paramID, value, label))
        return {'status':'ok','response':[{'cmdID':88,'poolID':115}]}
    def turn_on_device(self, outIdx, mode):  return self.set_out(outIdx, 1, mode)
    def turn_off_device(self, outIdx, mode): return self.set_out(outIdx, 0, mode)
