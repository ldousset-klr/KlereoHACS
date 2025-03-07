import logging
import requests
import hashlib
from .const import KLEREOSERVER, HA_VERSION

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
        response = requests.post(url, data=payload)
        response.raise_for_status()
        self.jwt = response.json().get('jwt')
        return self.jwt

    def get_index(self):
        if not self.jwt:
            self.get_jwt()
        url = f"{self.base_url}/GetIndex.php"
        headers = {
            'Authorization': f'Bearer {self.jwt}'
        }
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        index = response.json()['response']
        LOGGER.info(f"Successfully obtained GetIndex: {sensors}")
        return index

    def get_pool(self):

        LOGGER.info(f"GetPoolDetails #{self.poolid}")
        if not self.jwt:
            self.get_jwt()
        url = f"{self.base_url}/GetPoolDetails.php"
        headers = {
            'Authorization': f'Bearer {self.jwt}'
        }
        payload={
            'poolID': self.poolid,
            'lang': 'fr'
        }
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()
        pooldetails = response.json()
        pool=pooldetails['response'][0]
        return pool

    def turn_on_device(self, outIdx):
        LOGGER.info(f"TurnOn #{self.poolid} out{outIdx}")
        if not self.jwt:
            self.get_jwt()
        url = f"{self.base_url}/SetOut.php"
        headers = {
            'Authorization': f'Bearer {self.jwt}'
        }
        payload={
            'poolID': self.poolid,
            'outIdx': outIdx,
            'newMode': 2,
            'newState': 1
        }
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()
        rep = response.json()
        LOGGER.info(f"rep={rep}")

    def turn_off_device(self, outIdx):
        LOGGER.info(f"TurnOff #{self.poolid} out{outIdx}")
        if not self.jwt:
            self.get_jwt()
        url = f"{self.base_url}/SetOut.php"
        headers = {
            'Authorization': f'Bearer {self.jwt}'
        }
        payload={
            'poolID': self.poolid,
            'outIdx': outIdx,
            'newMode': 2,
            'newState': 0
        }
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()
        rep = response.json()
        LOGGER.info(f"rep={rep}")

    def set_device_mode(self, outIdx, mode):
        LOGGER.info(f"Changemode #{outIdx} mode={mode}")
        

