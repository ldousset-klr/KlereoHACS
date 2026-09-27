"""Vérifie SetParam."""
from klereo_stub import Api, Coordinator, Hass, run


def test_setparam(check):
    from klereo.number import KlereoWaterSetpoint
    from klereo.klereo_api import KlereoAPI, KlereoError
    def pool(v=28.0):
        return {'idSystem':115,'poolNickname':'T','probes':[],'IORename':[],'outs':[],
                'PumpMaxSpeed':3,'params':{'ConsigneEau':v}}
    print("== la charge POST correspond au PHP ==")
    sent={}
    class FakeSession:
        def post(self, url, headers=None, data=None, timeout=None):
            sent['url']=url; sent['data']=dict(data)
            class R:
                status_code=200
                text='{"status":"ok","response":[{"cmdID":42,"poolID":115}]}'
                def raise_for_status(self): pass
                def json(self): return {"status":"ok","response":[{"cmdID":42,"poolID":115}]}
            return R()
    api = KlereoAPI('u','p',poolid=115); api.session=FakeSession(); api.jwt='J'
    rep = api.set_param('ConsigneEau', 28.0)
    check("endpoint", sent['url'].rsplit('/',1)[-1], 'SetParam.php')
    check("champs", sorted(sent['data']), ['label','newValue','paramID','poolID'])
    check("poolID", sent['data']['poolID'], 115)
    check("paramID", sent['data']['paramID'], 'ConsigneEau')
    check("28.0 envoyé en 28", sent['data']['newValue'], 28)
    check("label de provenance", sent['data']['label'], 'Home Assistant: ConsigneEau=28')
    check("comMode absent (défaut serveur 0)", 'comMode' in sent['data'], False)
    check("réponse rendue", rep, {"status":"ok","response":[{"cmdID":42,"poolID":115}]})
    api.set_param('ConsigneEau', 26.5)
    check("26.5 reste 26.5", sent['data']['newValue'], 26.5)
    api.set_param('X', 3, label='perso')
    check("label explicite respecté", sent['data']['label'], 'perso')
    print("== valeurs que le serveur rejetterait, refusées avant l'aller-retour ==")
    for bad, why in ((float('nan'),'NaN'), (float('inf'),'inf'), (float('-inf'),'-inf'),
                     ('28','texte'), (None,'None'), (True,'booléen')):
        before = dict(sent)
        try: api.set_param('ConsigneEau', bad); got='ENVOYÉ'
        except KlereoError: got='refusé'
        check(f"  {why}", got, 'refusé')
    print("== l'entité écrit, et garde sa valeur jusqu'au poll suivant ==")
    c = Coordinator(pool()); a = Api()
    sp = KlereoWaterSetpoint(a, c, 115, {}); sp.hass = Hass()
    check("valeur initiale", sp.native_value, 28.0)
    run(sp.async_set_native_value(26.0))
    check("appel", a.calls[-1], ('set_param', 'ConsigneEau', 26.0, None))
    check("optimiste affiché", sp.native_value, 26.0)
    check("payload pas encore à jour", c.data['params']['ConsigneEau'], 28.0)
    sp._handle_coordinator_update()
    check("optimiste lâché au poll", sp.native_value, 28.0)
    c.data['params']['ConsigneEau'] = 26.0
    check("puis la vraie valeur", sp.native_value, 26.0)
    print("== arrondi au dixième, comme le coffret ==")
    for asked, kept in ((26.35, 26.4), (26.34, 26.3), (26.0, 26.0),
                        (28.649999, 28.6), (-1.27, -1.3), (26.05, 26.1)):
        c.data['params']['ConsigneEau'] = 99      # pour voir l'optimiste seul
        run(sp.async_set_native_value(asked))
        check(f"  {asked} -> {kept}", (a.calls[-1][2], sp.native_value), (kept, kept))
        sp._handle_coordinator_update()
    print("== une modification faite ailleurs passe ==")
    c.data['params']['ConsigneEau'] = 26.0
    sp._handle_coordinator_update()
    run(sp.async_set_native_value(24.0))
    c.data['params']['ConsigneEau'] = 30.0      # quelqu'un règle en façade
    sp._handle_coordinator_update()
    check("le coffret gagne", sp.native_value, 30.0)
    print("== aucun message des deux endpoints ne déclenche AUTH_HINTS ==")
    # Un faux positif ici ferait passer une erreur serveur pour un jeton expiré :
    # l'intégration renouvellerait le JWT, rejouerait, puis demanderait ses
    # identifiants à l'utilisateur pour un problème qui n'a rien à voir.
    from klereo.klereo_api import KlereoAPI as K
    MESSAGES = [
        # partagés
        "Désolé, le service n'est pas disponible pour le moment",   # GENERIC_ERROR
        "Vous n'êtes pas autorisé à faire cette action",
        "Vous n'êtes pas autorisé à faire cette action!",
        "poolID absent", "poolID incorrect",
        # SetParam.php
        "Mauvais Paramètre!", "Paramètre inconnu",
        "La modification à distance de ce paramètre est impossible sur cet appareil!",
        # SetOut.php
        "custFlags absent", "otherFlags absent", "outIdx absent",
        "newMode absent", "newState absent",
        "Commande non executée! Bassin réel!",
    ]
    for msg in MESSAGES:
        check(f"  {msg[:42]}", K._looks_like_auth_error(f"error={msg}"), False)
    check("total couvert", len(MESSAGES), 14)
    print()

    check.assert_ok()
