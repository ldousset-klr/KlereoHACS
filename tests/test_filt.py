"""Vérifie la filtration et ses vitesses."""
from klereo_stub import Api, Coordinator, Hass, ServiceValidationError, run


def test_filt(check):
    from klereo.select import KlereoOutMode
    from klereo.switch import KlereoOut
    from klereo.number import KlereoFiltrationSpeed, async_setup_entry as number_setup
    from klereo.entity import klereo_out_mode_states, klereo_pump_max_speed
    def pool(outs, max_speed=3):
        d = {'idSystem': 115, 'poolNickname': 'T', 'outs': outs, 'probes': [],
             'IORename': [], 'params': {}}
        if max_speed is not None: d['PumpMaxSpeed'] = max_speed
        return d
    def out(i, mode, status=0):
        return {'index': i, 'type': 0, 'mode': mode, 'status': status,
                'realStatus': status, 'updateTime': 0}
    print("== la plage de Manuel suit PumpMaxSpeed ==")
    for ms, want in ((3,(0,1,2,3)), (7,(0,1,2,3,4,5,6,7)), (1,(0,1)), (0,(0,)), (99,tuple(range(8)))):
        check(f"PumpMaxSpeed {ms}", klereo_out_mode_states(pool([], ms), 1)[0].states, want)
    check("PumpMaxSpeed absent", klereo_out_mode_states(pool([], None), 1)[0].states, tuple(range(8)))
    check("modes filtration", tuple(klereo_out_mode_states(pool([]), 1)), (0,1,3,6))
    print("== LE piège : 2 en Manuel = vitesse 2, pas 'conserver' ==")
    r = klereo_out_mode_states(pool([]), 1)
    check("Manuel: 2 permis mais pas keep", (2 in r[0].states, r[0].keep), (True, None))
    check("Plages: 2 EST le keep", (r[1].states, r[1].keep), ((2,), 2))
    check("Régulé: 2 EST le keep", (r[3].states, r[3].keep), ((2,), 2))
    check("Maintenance: pas de keep", (r[6].states, r[6].keep), ((0,1), None))
    print("== select filtration : le changement de mode ne démarre pas la pompe ==")
    for status in (0, 2, 3):
        c = Coordinator(pool([out(1, 1, status)])); api = Api()
        sel = KlereoOutMode(api, c, c.data['outs'][0], 115, {}, None); sel.hass = Hass()
        check("options", sel._attr_options, ['Manuel','Plages horaires','Régulé','Maintenance'])
        api.calls.clear(); run(sel.async_select_option('Manuel'))
        check(f"  Manuel depuis status={status} -> conserve la vitesse",
              api.calls[-1], ('set_out', 1, status, 0))
    c = Coordinator(pool([out(1, 0, 3)])); api = Api()
    sel = KlereoOutMode(api, c, c.data['outs'][0], 115, {}, None); sel.hass = Hass()
    for opt, mode, st in (('Plages horaires',1,2), ('Régulé',3,2)):
        api.calls.clear(); run(sel.async_select_option(opt)); sel._handle_coordinator_update()
        check(f"{opt} -> keep", api.calls[-1], ('set_out', 1, st, mode))
    print("== Maintenance n'a pas de keep et plusieurs états : status doit être 0 ou 1 ==")
    for status, want in ((0, ('set_out',1,0,6)), (1, ('set_out',1,1,6)), (3, 'out_mode_ambiguous_state')):
        c = Coordinator(pool([out(1, 0, status)])); api = Api()
        sel = KlereoOutMode(api, c, c.data['outs'][0], 115, {}, None); sel.hass = Hass()
        try: run(sel.async_select_option('Maintenance')); got = api.calls[-1]
        except ServiceValidationError as e: got = e.key
        check(f"Maintenance depuis status={status}", got, want)
    print("== number : la vitesse devient réglable, en Manuel seulement ==")
    for mode, val, want in ((0, 2, ('set_out',1,2,0)),
                            (0, 3, ('set_out',1,3,0)),
                            (0, 5, 'out_speed_not_settable'),   # > PumpMaxSpeed=3
                            (1, 2, 'out_speed_not_settable'),   # Plages
                            (3, 2, 'out_speed_not_settable'),   # Régulé
                            (6, 1, 'out_speed_not_settable')):  # Maintenance: pas une vitesse
        c = Coordinator(pool([out(1, mode, 0)])); api = Api()
        n = KlereoFiltrationSpeed(api, c, 115, {}, 3, None); n.hass = Hass()
        try: run(n.async_set_native_value(val)); got = api.calls[-1]
        except ServiceValidationError as e: got = e.key
        check(f"mode {mode}, vitesse {val}", got, want)
    print("== switch filtration ==")
    for mode, on_ok, off_ok in ((0,True,True), (1,False,False), (3,False,False), (6,True,True)):
        for action, ok in (('on',on_ok), ('off',off_ok)):
            c = Coordinator(pool([out(1, mode, 0)])); api = Api()
            sw = KlereoOut(api, c, c.data['outs'][0], 115, {}, None); sw.hass = Hass()
            try:
                run(sw.async_turn_on() if action=='on' else sw.async_turn_off()); got=api.calls[-1]
            except ServiceValidationError as e: got = e.key
            want = ('set_out',1,1 if action=='on' else 0,mode) if ok else 'out_mode_no_switching'
            check(f"mode {mode} turn_{action}", got, want)
    print("== is_on inchangé : n'importe quelle vitesse = en marche ==")
    c = Coordinator(pool([out(1, 0, 2)]))
    sw = KlereoOut(Api(), c, c.data['outs'][0], 115, {}, None)
    check("status 2 (vitesse 2)", sw.is_on, True)
    c.data['outs'][0]['status'] = 0
    check("status 0", sw.is_on, False)
    print()

    check.assert_ok()
