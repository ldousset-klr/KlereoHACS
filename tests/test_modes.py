"""Vérifie le sélecteur de mode et les refus du switch."""
from klereo_stub import Api, Coordinator, Hass, ServiceValidationError, run


def test_modes(check):
    from klereo.select import KlereoOutMode, async_setup_entry as select_setup
    from klereo.switch import KlereoOut
    from klereo.const import OUT_MODES, OUT_MODE_STATES
    def pool(outs):
        return {'idSystem': 115, 'poolNickname': 'Test', 'outs': outs,
                'probes': [], 'IORename': [], 'params': {}}
    def out(index, mode, status=0):
        return {'index': index, 'type': 0, 'mode': mode, 'status': status,
                'realStatus': status, 'updateTime': 0}
    print("== select : options offertes ==")
    c = Coordinator(pool([out(0, 0)]))
    api = Api()
    sel = KlereoOutMode(api, c, c.data['outs'][0], 115, {}, None)
    sel.hass = Hass()
    check("options éclairage", sel._attr_options,
          ['Manuel', 'Plages horaires', 'Minuterie', 'Synchronisé', 'Maintenance', 'Impulsion'])
    check("option courante (mode 0)", sel.current_option, 'Manuel')
    print("== select : mode réservé -> None, pas de valeur rejetée par HA ==")
    c.data['outs'][0]['mode'] = 3   # Régulé : hors liste pour l'éclairage
    check("mode 3 sur éclairage", sel.current_option, None)
    c.data['outs'][0]['mode'] = 99  # inconnu
    check("mode 99", sel.current_option, None)
    print("== select : l'écriture envoie newState=2 ==")
    c.data['outs'][0]['mode'] = 0
    run(sel.async_select_option('Plages horaires'))
    check("appel SetOut", api.calls[-1], ('set_out', 0, 2, 1))
    check("valeur optimiste", sel.current_option, 'Plages horaires')
    sel._handle_coordinator_update()
    check("optimiste effacé au poll", sel.current_option, 'Manuel')
    print("== select : quelles sorties en reçoivent un ==")
    outs = [out(i, 0) for i in range(16)]
    c2 = Coordinator(pool(outs))
    added = []
    class HassData(Hass):
        data = {'klereo': {'e': {'coordinator': c2, 'api': Api()}}}
    class Entry: entry_id = 'e'; data = {}
    run(select_setup(HassData(), Entry(), lambda es: added.extend(es)))
    check("index équipés", sorted(e._index for e in added), sorted(set(OUT_MODE_STATES) | {1}))
    check("filtration incluse", 1 in [e._index for e in added], True)
    check("désinfectant sans TraitMode exclu", [i for i in (3,) if i in [e._index for e in added]], [])
    check("chlore hybride inclus", 15 in [e._index for e in added], True)
    check("pH inclus", 2 in [e._index for e in added], True)
    print("== switch : on/off selon le mode ==")
    for mode, allowed in ((0,True),(1,False),(2,True),(4,False),(6,True),(8,True)):
        c3 = Coordinator(pool([out(0, mode)]))
        api3 = Api()
        sw = KlereoOut(api3, c3, c3.data['outs'][0], 115, {}, None)
        sw.hass = Hass()
        try:
            run(sw.async_turn_on())
            got = api3.calls[-1]
        except ServiceValidationError as e:
            got = e.key
        check(f"mode {mode} ({OUT_MODES[mode]}) turn_on",
              got, ('set_out', 0, 1, mode) if allowed else 'out_mode_no_switching')
    print("== switch : sortie non inscriptible et mode inconnu ==")
    c4 = Coordinator(pool([out(3, 3)]))   # désinfectant, lecture seule
    sw = KlereoOut(Api(), c4, c4.data['outs'][0], 115, {}, None); sw.hass = Hass()
    try: run(sw.async_turn_on()); got = 'PAS DE REFUS'
    except ServiceValidationError as e: got = e.key
    check("out 3 (désinfectant)", got, 'out_read_only')
    c5 = Coordinator(pool([out(0, 99)]))  # éclairage, mode réservé
    sw = KlereoOut(Api(), c5, c5.data['outs'][0], 115, {}, None); sw.hass = Hass()
    try: run(sw.async_turn_off()); got = 'PAS DE REFUS'
    except ServiceValidationError as e: got = (e.key, e.placeholders['mode'])
    check("out 0 en mode 99", got, ('out_mode_no_switching', '99'))
    print()

    check.assert_ok()
