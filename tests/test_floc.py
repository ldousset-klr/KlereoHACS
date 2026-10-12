"""Vérifie le floculant."""
from klereo_stub import Api, Coordinator, Hass, ServiceValidationError, run


def test_floc(check):
    from klereo.select import KlereoOutMode, async_setup_entry as select_setup
    from klereo.switch import KlereoOut
    from klereo.entity import klereo_out_mode_name, klereo_out_mode_states
    from klereo.const import OUT_STATE_KEEP, OUT_STATUS_OFF, OUT_STATUS_ON, HEATER_PAC_KLINK
    def pool(outs, heater=None):
        return {'idSystem': 115, 'poolNickname': 'T', 'outs': outs, 'probes': [],
                'IORename': [], 'params': ({} if heater is None else {'HeaterMode': heater})}
    def out(i, mode, status=0):
        return {'index': i, 'type': 0, 'mode': mode, 'status': status,
                'realStatus': status, 'updateTime': 0}
    P = pool([])
    print("== floculant : modes et noms ==")
    check("modes", tuple(klereo_out_mode_states(P, 8)), (0, 2))
    check("pas de Régulé", 3 in klereo_out_mode_states(P, 8), False)
    check("mode 2 nommé", klereo_out_mode_name(P, 8, 2), 'Volume fixe')
    check("mode 0 nommé", klereo_out_mode_name(P, 8, 0), 'Manuel')
    check("pH inchangé",  klereo_out_mode_name(P, 2, 2), 'Volume fixe')
    check("auxiliaire inchangé", klereo_out_mode_name(P, 5, 2), 'Minuterie')
    print("== select floculant ==")
    c = Coordinator(pool([out(8, 2)])); api = Api()
    sel = KlereoOutMode(api, c, c.data['outs'][0], 115, {}, None); sel.hass = Hass()
    check("options", sel._attr_options, ['Manuel', 'Volume fixe'])
    check("option courante", sel.current_option, 'Volume fixe')
    for opt, mode, st in (('Manuel', 0, OUT_STATUS_OFF), ('Volume fixe', 2, OUT_STATE_KEEP)):
        api.calls.clear(); run(sel.async_select_option(opt)); sel._handle_coordinator_update()
        check(f"{opt} -> SetOut", api.calls[-1], ('set_out', 8, st, mode))
    c.data['outs'][0]['mode'] = 3    # Régulé : réservé sur cette sortie
    check("mode 3 réservé -> None", sel.current_option, None)
    print("== switch floculant ==")
    for mode, on_ok, off_ok in ((0, False, True), (2, True, True)):
        for action, ok in (('on', on_ok), ('off', off_ok)):
            c2 = Coordinator(pool([out(8, mode)])); api2 = Api()
            sw = KlereoOut(api2, c2, c2.data['outs'][0], 115, {}, None); sw.hass = Hass()
            try:
                run(sw.async_turn_on() if action=='on' else sw.async_turn_off()); got=api2.calls[-1]
            except ServiceValidationError as e: got = e.key
            want = ('set_out', 8, OUT_STATUS_ON if action=='on' else OUT_STATUS_OFF, mode) \
                   if ok else 'out_mode_no_switching'
            check(f"mode {mode} turn_{action}", got, want)
    print("== il ne reste que le désinfectant, la filtration et le chlore hybride ==")
    for i, label in ((3,'désinfectant sans TraitMode'),):
        c3 = Coordinator(pool([out(i, 0)]))
        sw = KlereoOut(Api(), c3, c3.data['outs'][0], 115, {}, None); sw.hass = Hass()
        try: run(sw.async_turn_on()); got='PAS DE REFUS'
        except ServiceValidationError as e: got = e.key
        check(f"out{i} ({label})", got, 'out_read_only')
    c4 = Coordinator(pool([out(i,0) for i in range(16)], HEATER_PAC_KLINK)); added=[]
    class H(Hass): data={'klereo':{'e':{'coordinator':c4,'api':Api()}}}
    class E: entry_id='e'; data={}
    run(select_setup(H(), E(), lambda es: added.extend(es)))
    check("sélecteurs", sorted(e._index for e in added), [0,1,2,4,5,6,7,8,9,10,11,12,13,14,15])
    print()

    check.assert_ok()
