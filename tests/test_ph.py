"""Vérifie le correcteur pH."""
from klereo_stub import Api, Coordinator, Hass, ServiceValidationError, run


def test_ph(check):
    from klereo.select import KlereoOutMode, async_setup_entry as select_setup
    from klereo.switch import KlereoOut
    from klereo.entity import klereo_out_mode_name as _name, klereo_out_mode_states
    def klereo_out_mode_name(i, m): return _name(pool([]), i, m)
    from klereo.const import (OUT_MODE_STATES,
                              OUT_STATE_KEEP, OUT_STATUS_OFF, OUT_STATUS_ON)
    def pool(outs):
        return {'idSystem': 115, 'poolNickname': 'T', 'outs': outs,
                'probes': [], 'IORename': [], 'params': {}}
    def out(i, mode, status=0):
        return {'index': i, 'type': 0, 'mode': mode, 'status': status,
                'realStatus': status, 'updateTime': 0}
    print("== cohérence des tables ==")
    for i in sorted(OUT_MODE_STATES):
        check(f"out{i}: le résolveur rend la table statique",
              klereo_out_mode_states(pool([]), i), OUT_MODE_STATES[i])
    print("== le mode 2 change de nom selon la sortie ==")
    check("out0 mode 2", klereo_out_mode_name(0, 2), 'Minuterie')
    check("out2 mode 2", klereo_out_mode_name(2, 2), 'Volume fixe')
    check("out5 mode 2", klereo_out_mode_name(5, 2), 'Minuterie')
    check("out2 mode 0", klereo_out_mode_name(2, 0), 'Manuel')
    check("mode réservé", klereo_out_mode_name(2, 99), None)
    print("== select pH : options ==")
    c = Coordinator(pool([out(2, 3)]))
    api = Api()
    sel = KlereoOutMode(api, c, c.data['outs'][0], 115, {}, None)
    sel.hass = Hass()
    check("options pH", sel._attr_options, ['Manuel', 'Volume fixe', 'Régulé'])
    check("option courante (mode 3)", sel.current_option, 'Régulé')
    print("== select pH : quel newState part avec chaque mode ==")
    for option, mode, state in (('Régulé', 3, OUT_STATE_KEEP),
                                ('Volume fixe', 2, OUT_STATE_KEEP),
                                ('Manuel', 0, OUT_STATUS_OFF)):
        api.calls.clear()
        run(sel.async_select_option(option))
        check(f"{option} -> SetOut", api.calls[-1], ('set_out', 2, state, mode))
        sel._handle_coordinator_update()
    print("== select éclairage : toujours KEEP, inchangé ==")
    c2 = Coordinator(pool([out(0, 0)])); api2 = Api()
    s2 = KlereoOutMode(api2, c2, c2.data['outs'][0], 115, {}, None); s2.hass = Hass()
    run(s2.async_select_option('Maintenance'))
    check("éclairage -> Maintenance", api2.calls[-1], ('set_out', 0, OUT_STATE_KEEP, 6))
    print("== switch pH : on/off selon le mode ==")
    for mode, on_ok, off_ok in ((0, False, True),    # Manuel: arrêt seulement
                                (2, True,  True),    # Volume fixe: les deux
                                (3, False, False)):  # Régulé: ni l'un ni l'autre
        for action, ok in (('on', on_ok), ('off', off_ok)):
            c3 = Coordinator(pool([out(2, mode)])); api3 = Api()
            sw = KlereoOut(api3, c3, c3.data['outs'][0], 115, {}, None); sw.hass = Hass()
            try:
                run(sw.async_turn_on() if action == 'on' else sw.async_turn_off())
                got = api3.calls[-1]
            except ServiceValidationError as e:
                got = e.key
            want = ('set_out', 2, OUT_STATUS_ON if action == 'on' else OUT_STATUS_OFF, mode) \
                   if ok else 'out_mode_no_switching'
            check(f"pH mode {mode} ({klereo_out_mode_name(2, mode)}) turn_{action}", got, want)
    print("== le message d'erreur cite le nom vu par l'utilisateur ==")
    c4 = Coordinator(pool([out(2, 2)])); sw = KlereoOut(Api(), c4, c4.data['outs'][0], 115, {}, None)
    sw.hass = Hass()
    c4.data['outs'][0]['mode'] = 3
    try: run(sw.async_turn_on()); got='PAS DE REFUS'
    except ServiceValidationError as e: got = e.placeholders['mode']
    check("mode cité", got, 'Régulé')
    print("== sorties toujours en lecture seule ==")
    for i, label in ((3, 'désinfectant sans TraitMode'), (4, 'chauffage sans HeaterMode')):
        c5 = Coordinator(pool([out(i, 0)]))
        sw = KlereoOut(Api(), c5, c5.data['outs'][0], 115, {}, None); sw.hass = Hass()
        try: run(sw.async_turn_on()); got='PAS DE REFUS'
        except ServiceValidationError as e: got = e.key
        check(f"out{i} ({label})", got, 'out_read_only')
    print("== quelles sorties reçoivent un sélecteur ==")
    c6 = Coordinator(pool([out(i, 0) for i in range(16)]))
    added=[]
    class H(Hass): data = {'klereo': {'e': {'coordinator': c6, 'api': Api()}}}
    class E: entry_id='e'; data={}
    run(select_setup(H(), E(), lambda es: added.extend(es)))
    check("index équipés", sorted(e._index for e in added), [0,1,2,5,6,7,8,9,10,11,12,13,14,15])
    print()

    check.assert_ok()
