import logging
import requests
import hashlib
from .const import (DEF_SERVER, KLEREO_PATH, HA_VERSION, HTTP_TIMEOUT,
                    WAIT_COMMAND_TIMEOUT)

LOGGER = logging.getLogger(__name__)


class KlereoError(Exception):
    """The Klereo API returned something unusable."""


class KlereoAuthError(KlereoError):
    """The Klereo API rejected the credentials or the JWT."""


# The API reports part of its failures with HTTP 200 and an error payload, so
# the status code alone is not enough. These markers are matched
# case-insensitively against such a payload to tell an expired or refused token
# from any other failure; adjust them once a real payload has been observed.
AUTH_HINTS = ("jwt", "token", "auth", "login", "expir", "credential")


class KlereoAPI:
    def __init__(self, username, password, poolid=None, server=None):
        self.username = username
        self.password = password
        self.poolid = poolid
        self.base_url = self._base_url(server)
        self.jwt = None
        # One session for the whole integration: without it every call to the
        # five endpoints paid for a fresh TLS handshake.
        self.session = requests.Session()

    @staticmethod
    def _base_url(server):
        """Normalise the configured server into the endpoints' base URL."""
        base = (server or DEF_SERVER).strip().rstrip("/")
        if not base:
            base = DEF_SERVER
        if not base.endswith(KLEREO_PATH):
            base += KLEREO_PATH
        return base

    def hash_password(self):
        return hashlib.sha1(self.password.encode()).hexdigest()

    @staticmethod
    def _parse(response, endpoint):
        try:
            return response.json()
        except ValueError as err:
            raise KlereoError(f"{endpoint} did not return JSON: {response.text[:200]}") from err

    @staticmethod
    def _payload_error(data):
        """Return an error description if a HTTP 200 payload reports a failure."""
        if not isinstance(data, dict):
            return None
        for key in ("error", "errorMessage"):
            value = data.get(key)
            if value and str(value).lower() not in ("ok", "success", "0", "none"):
                return f"{key}={value}"
        # A live GetPoolDetails capture shows the envelope always carries
        # "status": "ok", so anything else in that field is a failure.
        status = data.get("status")
        if isinstance(status, str) and status.lower() not in ("ok", "success"):
            return f"status={status}"
        return None

    @staticmethod
    def _looks_like_auth_error(detail):
        lowered = detail.lower()
        return any(hint in lowered for hint in AUTH_HINTS)

    def get_jwt(self):
        endpoint = "GetJWT.php"
        url = f"{self.base_url}/{endpoint}"
        hashed_password = self.hash_password()
        payload = {
            'login': self.username,
            'password': hashed_password,
            'version': HA_VERSION,
            'app': 'api'
        }
        response = self.session.post(url, data=payload, timeout=HTTP_TIMEOUT)
        if response.status_code in (401, 403):
            raise KlereoAuthError(f"{endpoint} rejected the credentials (HTTP {response.status_code})")
        response.raise_for_status()
        data = self._parse(response, endpoint)
        error = self._payload_error(data)
        if error:
            raise KlereoAuthError(f"{endpoint} rejected the credentials: {error}")
        jwt = data.get('jwt') if isinstance(data, dict) else None
        if not jwt:
            # Without this the token stayed None and every later call
            # re-authenticated in a loop instead of failing.
            raise KlereoAuthError(f"{endpoint} returned no token: {str(data)[:200]}")
        self.jwt = jwt
        return self.jwt

    def _post(self, endpoint, payload=None, retry_auth=True, timeout=None):
        """POST an authenticated request, renewing the JWT once if it is refused.

        `timeout` overrides HTTP_TIMEOUT for the one endpoint that blocks on
        purpose; everything else leaves it alone.
        """
        if not self.jwt:
            self.get_jwt()
        url = f"{self.base_url}/{endpoint}"
        headers = {
            'Authorization': f'Bearer {self.jwt}'
        }
        response = self.session.post(url, headers=headers, data=payload,
                                     timeout=timeout or HTTP_TIMEOUT)
        if response.status_code in (401, 403):
            if retry_auth:
                LOGGER.info("JWT refused by %s (HTTP %s), renewing it", endpoint, response.status_code)
                self.jwt = None
                return self._post(endpoint, payload, retry_auth=False, timeout=timeout)
            raise KlereoAuthError(f"{endpoint} refused the JWT (HTTP {response.status_code})")
        response.raise_for_status()
        data = self._parse(response, endpoint)
        error = self._payload_error(data)
        if error is None:
            return data
        if self._looks_like_auth_error(error):
            if retry_auth:
                LOGGER.info("JWT looks expired (%s said: %s), renewing it", endpoint, error)
                self.jwt = None
                return self._post(endpoint, payload, retry_auth=False, timeout=timeout)
            raise KlereoAuthError(f"{endpoint} refused the JWT: {error}")
        raise KlereoError(f"{endpoint} failed: {error}")

    @staticmethod
    def _unwrap(data, endpoint):
        """Return the 'response' envelope, which GetIndex and GetPoolDetails always carry."""
        if not isinstance(data, dict) or 'response' not in data:
            raise KlereoError(f"{endpoint} returned an unexpected payload: {str(data)[:200]}")
        return data['response']

    def get_index(self):
        """Every system this account can see. Needs no poolID."""
        index = self._unwrap(self._post("GetIndex.php"), "GetIndex.php")
        LOGGER.info("GetIndex returned %s systems", len(index) if index else 0)
        return index

    def list_pools(self):
        """Reduce GetIndex to [(idSystem, name)], skipping anything unusable.

        GetIndex carries a lot more (probes, outsmodes, pin, compta); only what
        the config flow needs is kept. `suspended` is passed through untouched:
        a suspended system is still listed, and fails later at GetPoolDetails
        with a clear message rather than silently disappearing from the picker.
        """
        pools = []
        for system in self.get_index() or []:
            if not isinstance(system, dict):
                continue
            pool_id = system.get('idSystem')
            if pool_id is None:
                continue
            name = (system.get('poolNickname') or '').strip()
            pools.append((pool_id, name or f"Klereo pool #{pool_id}"))
        return pools

    def get_pool(self):
        LOGGER.info(f"GetPoolDetails #{self.poolid}")
        pools = self._unwrap(self._post("GetPoolDetails.php", {
            'poolID': self.poolid,
            'lang': 'fr'
        }), "GetPoolDetails.php")
        if not pools:
            raise KlereoError(f"GetPoolDetails.php knows no pool #{self.poolid}")
        return pools[0]

    def set_out(self, outIdx, state, mode):
        """Write an out's state. `mode` is newMode and has no default on
        purpose: it used to be hardcoded to 2 (Minuterie), which silently
        retimed every output it touched, so the caller must say what it wants.
        """
        LOGGER.info(f"SetOut #{self.poolid} out{outIdx} state={state} mode={mode}")
        rep = self._post("SetOut.php", {
            'poolID': self.poolid,
            'outIdx': outIdx,
            'newMode': mode,
            'newState': state
        })
        LOGGER.info(f"rep={rep}")
        return rep

    def set_param(self, paramID, value, label=None):
        """Queue a parameter write. `paramID` is the params[] key, e.g. ConsigneEau.

        **SetParam does not apply the value.** It inserts a UDP command into the
        server's queue for the pod and answers one {cmdID, poolID} per matched
        system, so the new value only reaches GetPoolDetails once the pod has
        fetched and applied it. A success here means *accepted*, never *applied*.

        `comMode` is deliberately omitted: the endpoint defaults it to 0.

        The server rejects the literal "NaN", and packs the value with the
        format its parameter table declares — rounding to an integer for the
        c/C/v formats. So a fractional value may come back rounded on a
        parameter declared as an integer, and what scale it is on is the
        table's business, not this method's: the caller sends the same units it
        read. ConsigneEau is a float in degrees Celsius and escapes that
        rounding; a parameter whose format is unknown should not assume it does.
        """
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise KlereoError(f"SetParam {paramID}: {value!r} is not a number")
        if value != value or value in (float("inf"), float("-inf")):
            # NaN and the infinities: the server rejects "NaN" by name, and the
            # rest would pack into nonsense. Refuse before the round trip.
            raise KlereoError(f"SetParam {paramID}: {value!r} is not finite")
        if isinstance(value, float) and value.is_integer():
            # "28" rather than "28.0": the server packs what it is given.
            value = int(value)
        payload = {
            'poolID': self.poolid,
            'paramID': paramID,
            'newValue': value,
        }
        # The server builds its own label when none is sent, carrying the
        # parameter's offset and length. Ours trades those internals for
        # provenance: the command log then says who asked for the change.
        payload['label'] = label or f"Home Assistant: {paramID}={value}"
        LOGGER.info(f"SetParam #{self.poolid} {paramID}={value}")
        rep = self._post("SetParam.php", payload)
        LOGGER.info(f"rep={rep}")
        return rep

    def wait_command(self, cmd_id):
        """Wait for a queued command to reach a terminal state, and say which.

        Returns the Commands row: cmdID, status, startTime, updateTime, detail.
        **The caller must read that status.** The endpoint answers json_ok even
        when it gives up — its loop also exits on its own 25 s ceiling with the
        command still pending — so a successful call means only that the
        question was asked. `status < COMMAND_DONE` is "still waiting", not
        "failed".

        Unlike the write endpoints, `response` here is a single object rather
        than a list, since the server passes one row to json_ok.
        """
        rep = self._post("WaitCommand.php", {'cmdID': cmd_id},
                         timeout=WAIT_COMMAND_TIMEOUT)
        row = self._unwrap(rep, "WaitCommand.php")
        if isinstance(row, list):
            # Not what the source does today, but indexing a list as a dict
            # would be a confusing crash if that ever changed.
            row = row[0] if row else {}
        if not isinstance(row, dict):
            raise KlereoError(f"WaitCommand.php returned {type(row).__name__}, not a row")
        return row

    @staticmethod
    def command_id(reply):
        """The cmdID a SetOut/SetParam reply carries, or None if it carries none.

        Those answer one {cmdID, poolID} per matched system. Every call here
        names a single pool, so there is exactly one — but a reply without it
        is not worth raising over: the command was accepted either way, and
        only the confirmation is lost.
        """
        if not isinstance(reply, dict):
            return None
        rows = reply.get("response")
        if not isinstance(rows, list) or not rows:
            return None
        cmd_id = rows[0].get("cmdID") if isinstance(rows[0], dict) else None
        return cmd_id if isinstance(cmd_id, int) else None

    def turn_on_device(self, outIdx, mode):
        return self.set_out(outIdx, 1, mode)

    def turn_off_device(self, outIdx, mode):
        return self.set_out(outIdx, 0, mode)
