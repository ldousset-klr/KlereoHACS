"""Vérifie ce que GetJWT.php reçoit : le hash, et la version de l'intégration."""
import json
from pathlib import Path


def test_jwt(check):
    from klereo.const import HA_VERSION, INTEGRATION_VERSION, client_version
    from klereo.klereo_api import KlereoAPI, hash_password

    print("== la version vient du manifest ==")
    manifest = Path(__file__).parent.parent / "custom_components/klereo/manifest.json"
    check("INTEGRATION_VERSION", INTEGRATION_VERSION,
          json.loads(manifest.read_text(encoding="utf-8"))["version"])
    check("HA_VERSION en dérive", HA_VERSION, client_version(INTEGRATION_VERSION))
    print("== chiffres seuls, puis -HA ==")
    for version, want in (("1.7.0", "170-HA"), ("1.7.1", "171-HA"),
                          ("1.6.0", "160-HA"), ("2.0.0", "200-HA")):
        check(f"  {version}", client_version(version), want)

    print("== le corps du POST ==")
    sent = {}
    class S:
        def post(self, url, data=None, timeout=None, headers=None):
            sent['url'] = url; sent['data'] = dict(data)
            class R:
                status_code = 200
                def raise_for_status(self): pass
                def json(self): return {'status': 'ok', 'jwt': 'J'}
            return R()
    api = KlereoAPI('u', hash_password('p'), poolid=115); api.session = S()
    check("jeton rendu", api.get_jwt(), 'J')
    check("endpoint", sent['url'].rsplit('/', 1)[-1], 'GetJWT.php')
    check("corps", sent['data'], {'login': 'u', 'password': hash_password('p'),
                                  'version': HA_VERSION, 'app': 'api'})
    print()

    check.assert_ok()
