"""The fake Klereo server the suites run the integration against.

`FakeKlereoAPI` stands in for `KlereoAPI` wherever the component builds one,
answering from `POOL`: a synthetic payload, not a capture, so it carries no
one's address, serial or PIN.
"""
import copy

from custom_components.klereo import const
from custom_components.klereo.klereo_api import KlereoAPI

POOLID = 115

POOL = {
    "idSystem": POOLID,
    "poolNickname": "Test pool",
    "tabSW": "212D",
    "tabHW": "3",
    "podSerial": "TEST0000",
    "device": 0,
    "register": {"pin": 1234},
    "access": 16,
    "PumpMaxSpeed": 3,
    "probes": [
        # At the slots the controller names them by, so PROBE_LABELS reads
        # true where IORename leaves a probe unnamed.
        {"index": 16, "type": 5, "filteredValue": 26.5, "filteredTime": 60,
         "directValue": 26.6, "directTime": 30},
        {"index": 17, "type": 3, "filteredValue": 7.2, "filteredTime": 60,
         "directValue": 7.3, "directTime": 30},
        {"index": 18, "type": 4, "filteredValue": 720, "filteredTime": 60,
         "directValue": 715, "directTime": 30},
        {"index": 13, "type": 6, "filteredValue": -1000, "filteredTime": 60,
         "directValue": -1000, "directTime": 30},
    ],
    "outs": [
        {"index": 0, "type": 0, "mode": 0, "status": 0, "realStatus": 0, "updateTime": 0},
        {"index": 1, "type": 0, "mode": 0, "status": 2, "realStatus": 2, "updateTime": 0},
        {"index": 2, "type": 0, "mode": 3, "status": 0, "realStatus": 0, "updateTime": 0},
        {"index": 3, "type": 0, "mode": 3, "status": 1, "realStatus": 1, "updateTime": 0},
        {"index": 4, "type": 0, "mode": 3, "status": 0, "realStatus": 0, "updateTime": 0},
    ],
    "IORename": [
        {"ioType": 1, "ioIndex": 0, "name": "Spots"},
        {"ioType": 2, "ioIndex": 16, "name": "Eau bassin"},
    ],
    "params": {
        "ConsigneEau": 27.5,
        "HeaterMode": const.HEATER_NORMAL,
        "TraitMode": const.TRAIT_CHLORE,
        "VolumeEau": 50,
        "Filtration_TotalTime": 36000,
        "PHMinus_TotalTime": 3600,
        "ElectroChlore_TotalTime": 7200,
        "Chauff_TotalTime": 0,
        "PHMinus_Debit": 15,
        "Chlore_Debit": 20,
    },
}

DATA = {"username": "user@example.com", "password": "secret",
        "poolid": POOLID, "server": const.DEF_SERVER}


class FakeKlereoAPI:
    """Stands in for KlereoAPI: answers from POOL, records every write.

    Class-level state, reset by the `api` fixture, because the component builds
    its own instances — the config flow one per attempt, the entry one at setup.
    """
    pool = None
    pools = []            # what list_pools answers
    error = None          # raised by every read when set
    list_error = None     # raised by list_pools alone when set
    made = []
    calls = []

    def __init__(self, username, password, poolid=None, server=None):
        FakeKlereoAPI.made.append((username, password, poolid, server))

    def get_pool(self):
        if FakeKlereoAPI.error:
            raise FakeKlereoAPI.error
        return copy.deepcopy(FakeKlereoAPI.pool)

    def list_pools(self):
        if FakeKlereoAPI.list_error or FakeKlereoAPI.error:
            raise FakeKlereoAPI.list_error or FakeKlereoAPI.error
        return list(FakeKlereoAPI.pools)

    def set_out(self, outIdx, state, mode):
        FakeKlereoAPI.calls.append(("set_out", outIdx, state, mode))
        # The pod applies it, so the refresh after the confirmation shows it.
        # Keep leaves the state alone, except on the filtration, where 2 is
        # a speed in Manuel.
        for out in FakeKlereoAPI.pool["outs"]:
            if out["index"] == outIdx:
                out["mode"] = mode
                if state != const.OUT_STATE_KEEP or outIdx == const.FILTRATION_OUT_INDEX:
                    out["status"] = state
        return {"status": "ok", "response": [{"cmdID": 1, "poolID": POOLID}]}

    def turn_on_device(self, outIdx, mode):
        return self.set_out(outIdx, 1, mode)

    def turn_off_device(self, outIdx, mode):
        return self.set_out(outIdx, 0, mode)

    def set_param(self, paramID, value, label=None):
        FakeKlereoAPI.calls.append(("set_param", paramID, value))
        FakeKlereoAPI.pool["params"][paramID] = value
        return {"status": "ok", "response": [{"cmdID": 2, "poolID": POOLID}]}

    def command_status(self, cmd_id):
        FakeKlereoAPI.calls.append(("command_status", cmd_id))
        return {"cmdID": cmd_id, "status": const.COMMAND_DONE}

    command_id = staticmethod(KlereoAPI.command_id)
