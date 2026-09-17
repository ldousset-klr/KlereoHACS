import logging
import requests
import hashlib
from .const import KLEREOSERVER, HA_VERSION, HTTP_TIMEOUT

LOGGER = logging.getLogger(__name__)

class KlereoAPI:
    def __init__(self, username, password, poolid):
        self.username = username
        self.password = password
        self.poolid = poolid
        self.base_url = KLEREOSERVER
        self.jwt = None

    def hash_password(self):
        return hashlib.sha1(self.password.encode()).hexdigest()

    def get_jwt(self):
        url = f"{self.base_url}/GetJWT.php"
        hashed_password = self.hash_password()
        payload = {
            'login': self.username,
            'password': hashed_password,
            'version': HA_VERSION,
            'app': 'api'
        }
        response = requests.post(url, data=payload, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        self.jwt = response.json().get('jwt')
        return self.jwt

    def _post(self, endpoint, payload=None, retry_auth=True):
        """POST an authenticated request, renewing the JWT once if it is refused."""
        if not self.jwt:
            self.get_jwt()
        url = f"{self.base_url}/{endpoint}"
        headers = {
            'Authorization': f'Bearer {self.jwt}'
        }
        response = requests.post(url, headers=headers, data=payload, timeout=HTTP_TIMEOUT)
        if response.status_code in (401, 403) and retry_auth:
            LOGGER.info("JWT refused by %s (HTTP %s), renewing it", endpoint, response.status_code)
            self.jwt = None
            return self._post(endpoint, payload, retry_auth=False)
        response.raise_for_status()
        return response.json()

    def get_index(self):
        index = self._post("GetIndex.php")['response']
        LOGGER.info(f"Successfully obtained GetIndex: {index}")
        return index

    def get_pool(self):
        LOGGER.info(f"GetPoolDetails #{self.poolid}")
        pooldetails = self._post("GetPoolDetails.php", {
            'poolID': self.poolid,
            'lang': 'fr'
        })
        pool=pooldetails['response'][0]
        return pool

    def set_out(self, outIdx, state):
        LOGGER.info(f"SetOut #{self.poolid} out{outIdx} state={state}")
        rep = self._post("SetOut.php", {
            'poolID': self.poolid,
            'outIdx': outIdx,
            'newMode': 2,
            'newState': state
        })
        LOGGER.info(f"rep={rep}")
        return rep

    def turn_on_device(self, outIdx):
        return self.set_out(outIdx, 1)

    def turn_off_device(self, outIdx):
        return self.set_out(outIdx, 0)

    def set_device_mode(self, outIdx, mode):
        LOGGER.info(f"Changemode #{outIdx} mode={mode}")
