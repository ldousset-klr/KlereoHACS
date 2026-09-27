"""Vérifie la reprise de la dernière vitesse connue."""
from klereo_stub import Api, Coordinator, Hass, ServiceValidationError, State, run


def test_resume(check):
    from klereo.switch import KlereoOut
    def pool(outs, max_speed=3):
        return {'idSystem':115,'poolNickname':'T','outs':outs,'probes':[],
                'IORename':[],'params':{},'PumpMaxSpeed':max_speed}
    def out(i, mode, status=0):
        return {'index':i,'type':0,'mode':mode,'status':status,'realStatus':status,'updateTime':0}
    def sw_for(o, pdata=None):
        c = Coordinator(pdata or pool([o])); api = Api()
        s = KlereoOut(api, c, o, 115, {}, None); s.hass = Hass()
        return s, api, c
    print("== la vitesse est apprise des polls ==")
    o = out(1, 0, 3)
    sw, api, c = sw_for(o)
    check("apprise à la construction", sw._last_speed, 3)
    c.data['outs'][0]['status'] = 0        # la pompe s'arrête
    sw._handle_coordinator_update()
    check("0 n'efface pas la mémoire", sw._last_speed, 3)
    c.data['outs'][0]['status'] = 2
    sw._handle_coordinator_update()
    check("mise à jour sur nouvelle vitesse", sw._last_speed, 2)
    print("== turn_on reprend la dernière vitesse ==")
    o = out(1, 0, 3); sw, api, c = sw_for(o)
    c.data['outs'][0]['status'] = 0
    sw._handle_coordinator_update()
    run(sw.async_turn_on())
    check("Manuel, dernière vitesse 3", api.calls[-1], ('set_out', 1, 3, 0))
    print("== jamais vue en marche : vitesse 1, l'ancien comportement ==")
    o = out(1, 0, 0); sw, api, c = sw_for(o)
    check("rien en mémoire", sw._last_speed, None)
    run(sw.async_turn_on())
    check("repli sur 1", api.calls[-1], ('set_out', 1, 1, 0))
    print("== une vitesse devenue hors plage est ignorée ==")
    o = out(1, 0, 6); sw, api, c = sw_for(o, pool([out(1,0,6)], max_speed=7))
    c.data['PumpMaxSpeed'] = 3             # pompe remplacée, moins rapide
    c.data['outs'][0]['status'] = 0
    sw._handle_coordinator_update()
    run(sw.async_turn_on())
    check("6 hors 0..3 -> repli sur 1", api.calls[-1], ('set_out', 1, 1, 0))
    print("== Maintenance : des états on/off, pas des vitesses ==")
    o = out(1, 6, 0); sw, api, c = sw_for(o)
    sw._last_speed = 3
    run(sw.async_turn_on())
    check("envoie 1, pas 3", api.calls[-1], ('set_out', 1, 1, 6))
    print("== les autres sorties ne changent pas ==")
    for i in (0, 5):
        o = out(i, 0, 1); sw, api, c = sw_for(o)
        check(f"out{i} n'apprend rien", sw._last_speed, None)
        run(sw.async_turn_on())
        check(f"out{i} turn_on", api.calls[-1], ('set_out', i, 1, 0))
    o = out(2, 2, 1); sw, api, c = sw_for(o)     # pH en Volume fixe
    run(sw.async_turn_on())
    check("pH turn_on", api.calls[-1], ('set_out', 2, 1, 2))
    print("== turn_off et les refus inchangés ==")
    o = out(1, 0, 3); sw, api, c = sw_for(o)
    run(sw.async_turn_off())
    check("turn_off envoie 0", api.calls[-1], ('set_out', 1, 0, 0))
    for mode in (1, 3):
        o = out(1, mode, 2); sw, api, c = sw_for(o)
        sw._last_speed = 3
        try: run(sw.async_turn_on()); got='PAS DE REFUS'
        except ServiceValidationError as e: got = e.key
        check(f"mode {mode} refuse toujours", got, 'out_mode_no_switching')
    print("== survie au redémarrage via l'attribut publié ==")
    o = out(1, 0, 3); sw, api, c = sw_for(o)
    attrs = sw.extra_state_attributes
    check("LastSpeed publié", attrs['LastSpeed'], 3)
    o2 = out(1, 0, 0); sw2, api2, c2 = sw_for(o2)      # HA redémarre, pompe arrêtée
    sw2._restored = State(attrs)
    run(sw2.async_added_to_hass())
    check("restauré", sw2._last_speed, 3)
    run(sw2.async_turn_on())
    check("turn_on après restauration", api2.calls[-1], ('set_out', 1, 3, 0))
    o3 = out(1, 0, 0); sw3, api3, c3 = sw_for(o3)      # rien à restaurer
    sw3._restored = None
    run(sw3.async_added_to_hass())
    check("sans état précédent", sw3._last_speed, None)
    o4 = out(0, 0, 1); sw4, _, _ = sw_for(o4)
    check("éclairage : pas de LastSpeed", 'LastSpeed' in sw4.extra_state_attributes, False)
    print()

    check.assert_ok()
