"""Vérifie le suivi des commandes via CommandStatus."""
from klereo_stub import Api, Coordinator, Hass, ServiceValidationError, run


def test_wait(check):
    from klereo.switch import KlereoOut
    from klereo.number import KlereoWaterSetpoint
    from klereo.klereo_api import KlereoAPI, KlereoError
    from klereo.const import COMMAND_DONE, COMMAND_STATUS, COMMAND_POLL_DELAYS, HTTP_TIMEOUT
    def pool():
        return {'idSystem':115,'poolNickname':'T','probes':[],'IORename':[],'PumpMaxSpeed':3,
                'params':{'ConsigneEau':28.0},
                'outs':[{'index':0,'type':0,'mode':0,'status':0,'realStatus':0,'updateTime':0}]}
    print("== l'énumération vient de CommandSender.h ==")
    check("COMMAND_DONE", COMMAND_DONE, 9)
    check("seul 9 est un succès", [k for k in COMMAND_STATUS if k == COMMAND_DONE], [9])
    check("en attente", sorted(k for k in COMMAND_STATUS if k < 9), [0, 1])
    check("échecs", sorted(k for k in COMMAND_STATUS if k > 9), [10,11,12,13,15,16,17,18,19])
    check("14 absent de l'en-tête", 14 in COMMAND_STATUS, False)
    check("cadence choisie par nous", COMMAND_POLL_DELAYS, (1,2,3,5,5,5,5))
    check("  fenêtre totale", sum(COMMAND_POLL_DELAYS), 26)
    check("  requêtes au pire", len(COMMAND_POLL_DELAYS), 7)
    check("  aucun timeout spécial : HTTP_TIMEOUT suffit", HTTP_TIMEOUT, 30)
    print("== command_id() extrait le cmdID des réponses d'écriture ==")
    check("réponse normale", KlereoAPI.command_id({'status':'ok','response':[{'cmdID':77,'poolID':115}]}), 77)
    check("plusieurs systèmes -> le premier",
          KlereoAPI.command_id({'response':[{'cmdID':5},{'cmdID':6}]}), 5)
    for bad, why in ((None,'None'), ({}, 'sans response'), ({'response':[]}, 'liste vide'),
                     ({'response':{}}, 'pas une liste'), ({'response':[{}]}, 'sans cmdID'),
                     ({'response':[{'cmdID':'77'}]}, 'cmdID texte')):
        check(f"  {why}", KlereoAPI.command_id(bad), None)
    print("== command_status : une liste, on y cherche notre ligne ==")
    sent={}
    class FS:
        def post(self, url, headers=None, data=None, timeout=None):
            sent['url']=url; sent['data']=dict(data); sent['timeout']=timeout
            row={'cmdID':77,'status':9,'startTime':'2026-09-27 12:00:00',
                 'updateTime':'2026-09-27 12:00:01','detail':None}
            class R:
                status_code=200
                def raise_for_status(self): pass
                def json(self): return {'status':'ok','response':[row]}
            return R()
    api = KlereoAPI('u','p',poolid=115); api.session=FS(); api.jwt='J'
    row = api.command_status(77)
    check("endpoint", sent['url'].rsplit('/',1)[-1], 'CommandStatus.php')
    check("charge", sent['data'], {'cmdID': 77})
    check("timeout standard", sent['timeout'], HTTP_TIMEOUT)
    check("ligne rendue", row['status'], 9)
    check("horodatages laissés tels quels", row['startTime'], '2026-09-27 12:00:00')
    print("== le succès garde la valeur optimiste jusqu'au rafraîchissement ==")
    c = Coordinator(pool()); api2 = Api(); api2.wait_status = 9
    h = Hass(); h.keep_tasks = True
    sw = KlereoOut(api2, c, c.data['outs'][0], 115, {}, None); sw.hass = h
    run(sw.async_turn_on())
    check("écriture partie", api2.calls[0], ('set_out', 0, 1, 0))
    check("optimiste posé", sw.is_on, True)
    check("aucune attente bloquante dans le service", len(api2.calls), 1)
    h.run_tasks()
    check("CommandStatus appelé en fond", api2.calls[1], ('command_status', 77))
    check("optimiste conservé (appliquée)", sw._optimistic_state, True)
    print("== un échec lâche l'optimiste et journalise la raison ==")
    for st, mot in ((13,'access'), (17,'not connected'), (19,'firmware'), (10,'error')):
        c = Coordinator(pool()); a = Api(); a.wait_status = st; a.wait_detail = 'd'
        h = Hass(); h.keep_tasks = True
        sw = KlereoOut(a, c, c.data['outs'][0], 115, {}, None); sw.hass = h
        run(sw.async_turn_on())
        check(f"  status={st} optimiste posé", sw._optimistic_state, True)
        h.run_tasks()
        check(f"  status={st} ({COMMAND_STATUS[st][:24]}) lâché", sw._optimistic_state, None)
    print("== encore en attente : lâché aussi, mais ce n'est pas un échec ==")
    for st in (0, 1):
        c = Coordinator(pool()); a = Api(); a.wait_status = st
        h = Hass(); h.keep_tasks = True
        sw = KlereoOut(a, c, c.data['outs'][0], 115, {}, None); sw.hass = h
        run(sw.async_turn_on()); h.run_tasks()
        check(f"  status={st}", sw._optimistic_state, None)
    print("== CommandStatus injoignable : on n'invente pas un échec ==")
    c = Coordinator(pool()); a = Api(); a.wait_raises = KlereoError('boom')
    h = Hass(); h.keep_tasks = True
    sw = KlereoOut(a, c, c.data['outs'][0], 115, {}, None); sw.hass = h
    run(sw.async_turn_on()); h.run_tasks()
    check("optimiste lâché, le payload tranchera", sw._optimistic_state, None)
    print("== la consigne suit le même chemin ==")
    c = Coordinator(pool()); a = Api(); a.wait_status = 9
    h = Hass(); h.keep_tasks = True
    sp = KlereoWaterSetpoint(a, c, 115, {}); sp.hass = h
    run(sp.async_set_native_value(26.0))
    check("SetParam parti", a.calls[0], ('set_param','ConsigneEau',26.0,None))
    check("service non bloquant", len(a.calls), 1)
    h.run_tasks()
    check("CommandStatus sur le cmdID de SetParam", a.calls[1], ('command_status', 88))
    check("optimiste tenu", sp.native_value, 26.0)
    print("== le seul message d'erreur de CommandStatus ==")
    for m in ["Désolé, le service n'est pas disponible pour le moment"]:
        check(f"  {m}", KlereoAPI._looks_like_auth_error('error='+m), False)
    print("== il sonde jusqu'à ce que le pod réponde ==")
    c = Coordinator(pool()); a = Api(); a.wait_sequence = [0, 1, 1, 9]
    h = Hass(); h.keep_tasks = True
    sw = KlereoOut(a, c, c.data['outs'][0], 115, {}, None); sw.hass = h
    run(sw.async_turn_on()); h.run_tasks()
    polls = [x for x in a.calls if x[0]=='command_status']
    check("a sondé jusqu'au verdict", len(polls), 4)
    check("s'est arrêté au 9", sw._optimistic_state, True)
    print("== jamais plus que la cadence prévue ==")
    c = Coordinator(pool()); a = Api(); a.wait_status = 0      # toujours en attente
    h = Hass(); h.keep_tasks = True
    sw = KlereoOut(a, c, c.data['outs'][0], 115, {}, None); sw.hass = h
    run(sw.async_turn_on()); h.run_tasks()
    polls = [x for x in a.calls if x[0]=='command_status']
    check("plafonné", len(polls), len(COMMAND_POLL_DELAYS))
    check("optimiste lâché", sw._optimistic_state, None)
    print("== cmdID inconnu du serveur : liste vide -> None ==")
    c = Coordinator(pool()); a = Api(); a.wait_missing = True
    h = Hass(); h.keep_tasks = True
    sw = KlereoOut(a, c, c.data['outs'][0], 115, {}, None); sw.hass = h
    run(sw.async_turn_on()); h.run_tasks()
    check("un seul essai, puis abandon", len([x for x in a.calls if x[0]=='command_status']), 1)
    check("optimiste lâché", sw._optimistic_state, None)
    print()

    check.assert_ok()
