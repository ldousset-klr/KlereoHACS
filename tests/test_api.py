"""Vérifie KlereoAPI au niveau HTTP : jeton, rejeu, erreurs et charges utiles."""
import pytest
import requests


class Resp:
    def __init__(self, status=200, body=None, text=None):
        self.status_code = status
        self._body = body
        self.text = text if text is not None else str(body)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self._body is None:
            raise ValueError("no JSON")
        return self._body


class Session:
    """Answers GetJWT with a fresh token each time, and the rest from a script."""

    def __init__(self, *replies, jwt=None):
        self.replies = list(replies)
        self.jwt = jwt or []
        self.calls = []
        self.tokens = 0

    def post(self, url, data=None, timeout=None, headers=None):
        endpoint = url.rsplit('/', 1)[-1]
        self.calls.append((endpoint, dict(data or {}), (headers or {}).get('Authorization')))
        if endpoint == 'GetJWT.php':
            if self.jwt:
                return self.jwt.pop(0)
            self.tokens += 1
            return Resp(body={'status': 'ok', 'jwt': f"J{self.tokens}"})
        return self.replies.pop(0)

    def endpoints(self):
        return [c[0] for c in self.calls]


def ok(response=None):
    return Resp(body={'status': 'ok', 'response': response if response is not None else []})


def test_api(check):
    from klereo.klereo_api import KlereoAPI, KlereoAuthError, KlereoError

    def api(*replies, jwt=None):
        a = KlereoAPI('u', 'h', poolid=115)
        a.session = Session(*replies, jwt=jwt)
        return a

    def raises(exc, fn):
        with pytest.raises(exc) as err:
            fn()
        return err.value

    print("== l'adresse du serveur ==")
    for server, want in ((None, "https://connect.klereo.fr/php"),
                         ("", "https://connect.klereo.fr/php"),
                         ("   ", "https://connect.klereo.fr/php"),
                         ("https://dev.example/", "https://dev.example/php"),
                         ("https://dev.example/php/", "https://dev.example/php")):
        check(f"  {server!r}", KlereoAPI._base_url(server), want)

    print("== une réponse 200 qui annonce un échec ==")
    pe = KlereoAPI._payload_error
    check("  pas un dict", pe([1]), None)
    check("  status ok", pe({'status': 'ok'}), None)
    check("  error", pe({'error': 'boom'}), "error=boom")
    check("  error 'success'", pe({'error': 'success'}), None)
    check("  errorMessage", pe({'errorMessage': 'x'}), "errorMessage=x")
    check("  status ko", pe({'status': 'ko'}), "status=ko")

    print("== GetJWT refusé ==")
    a = api(jwt=[Resp(401)])
    check("  HTTP 401 : identifiants", 'HTTP 401' in str(raises(KlereoAuthError, a.get_jwt)), True)
    a = api(jwt=[Resp(body={'status': 'ko', 'error': 'bad login'})])
    check("  erreur dans la réponse", 'bad login' in str(raises(KlereoAuthError, a.get_jwt)), True)
    a = api(jwt=[Resp(body={'status': 'ok'})])
    check("  aucun jeton", 'no token' in str(raises(KlereoAuthError, a.get_jwt)), True)
    check("  et rien de gardé", a.jwt, None)
    a = api(jwt=[Resp(500)])
    check("  HTTP 500 : pas une erreur d'identifiants",
          isinstance(raises(requests.HTTPError, a.get_jwt), KlereoError), False)
    a = api(jwt=[Resp(200, None, text="<html>")])
    check("  pas du JSON", 'did not return JSON' in str(raises(KlereoError, a.get_jwt)), True)

    print("== le jeton est demandé au premier appel, puis réutilisé ==")
    a = api(ok([{'idSystem': 115}]), ok([{'idSystem': 115}]))
    a.get_pool(); a.get_pool()
    check("  un seul GetJWT", a.session.endpoints(),
          ['GetJWT.php', 'GetPoolDetails.php', 'GetPoolDetails.php'])
    check("  envoyé en Bearer", a.session.calls[1][2], 'Bearer J1')

    print("== 401/403 : un jeton neuf, la requête rejouée une fois ==")
    for code in (401, 403):
        a = api(Resp(code), ok([{'idSystem': 115}]))
        check(f"  {code} puis succès", a.get_pool(), {'idSystem': 115})
        check("    renouvelé", a.session.endpoints(),
              ['GetJWT.php', 'GetPoolDetails.php', 'GetJWT.php', 'GetPoolDetails.php'])
        check("    avec le nouveau jeton", a.session.calls[3][2], 'Bearer J2')
    a = api(Resp(401), Resp(401))
    raises(KlereoAuthError, a.get_pool)
    check("  refusé deux fois : KlereoAuthError, sans boucle",
          a.session.endpoints().count('GetPoolDetails.php'), 2)

    print("== une erreur qui ressemble à un jeton expiré : même rejeu ==")
    expired = Resp(body={'status': 'error', 'error': 'JWT expired'})
    a = api(expired, ok([{'idSystem': 115}]))
    check("  puis succès", a.get_pool(), {'idSystem': 115})
    check("    un GetJWT de plus", a.session.endpoints().count('GetJWT.php'), 2)
    a = api(expired, Resp(body={'status': 'error', 'error': 'JWT expired'}))
    raises(KlereoAuthError, a.get_pool)
    check("  deux fois : KlereoAuthError", a.session.endpoints().count('GetPoolDetails.php'), 2)

    print("== toute autre erreur ne touche pas au jeton ==")
    a = api(Resp(body={'status': 'error', 'error': 'pool inconnue'}))
    err = raises(KlereoError, a.get_pool)
    check("  KlereoError", type(err).__name__, 'KlereoError')
    check("  pas de rejeu", a.session.endpoints(), ['GetJWT.php', 'GetPoolDetails.php'])
    a = api(Resp(500))
    raises(requests.HTTPError, a.get_pool)
    check("  HTTP 500 : remonte tel quel, sans rejeu",
          a.session.endpoints(), ['GetJWT.php', 'GetPoolDetails.php'])

    print("== GetPoolDetails ==")
    a = api(ok([{'idSystem': 115}, {'idSystem': 116}]))
    check("  la première", a.get_pool(), {'idSystem': 115})
    check("  le corps", a.session.calls[1][1], {'poolID': 115, 'lang': 'fr'})
    a = api(ok([]))
    check("  vide : KlereoError", '#115' in str(raises(KlereoError, a.get_pool)), True)
    a = api(Resp(body={'status': 'ok'}))
    check("  sans 'response'", 'unexpected payload' in str(raises(KlereoError, a.get_pool)), True)

    print("== GetIndex et la liste des bassins ==")
    a = api(ok([{'idSystem': 2, 'poolNickname': ' Spa '},
                {'idSystem': 3, 'poolNickname': ''},
                {'poolNickname': 'sans id'},
                'pas un dict',
                {'idSystem': 4}]))
    check("  nettoyée", a.list_pools(),
          [(2, 'Spa'), (3, 'Klereo pool #3'), (4, 'Klereo pool #4')])
    check("  sans poolID", a.session.calls[1][1], {})
    a = api(Resp(body={'status': 'ok', 'response': None}))
    check("  réponse nulle : liste vide", a.list_pools(), [])

    print("== SetOut ==")
    a = api(ok([{'cmdID': 7}]), ok(), ok())
    check("  réponse rendue", a.set_out(5, 2, 1)['response'], [{'cmdID': 7}])
    check("  le corps", a.session.calls[1][1],
          {'poolID': 115, 'outIdx': 5, 'newMode': 1, 'newState': 2})
    a.turn_on_device(0, 4); a.turn_off_device(0, 4)
    check("  marche/arrêt", [c[1]['newState'] for c in a.session.calls[2:]], [1, 0])
    check("  le mode passe tel quel", [c[1]['newMode'] for c in a.session.calls[2:]], [4, 4])
    print()

    check.assert_ok()
