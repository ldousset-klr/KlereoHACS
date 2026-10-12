"""Vérifie le chauffage et params.HeaterMode."""
from klereo_stub import Api, Coordinator, Hass, ServiceValidationError, run


def test_heat(check):
    from klereo.select import KlereoOutMode, async_setup_entry as select_setup
    from klereo.switch import KlereoOut
    from klereo.entity import klereo_out_mode_name, klereo_out_mode_states
    from klereo.const import (OUT_STATE_KEEP, OUT_STATUS_OFF, OUT_STATUS_ON,
                              HEATER_NONE, HEATER_NORMAL, HEATER_PAC_KLINK,
                              HEATER_NOTARGET, HEATER_PAC_MODBUS)
    def pool(outs, heater=None):
        params = {} if heater is None else {'HeaterMode': heater}
        return {'idSystem': 115, 'poolNickname': 'T', 'outs': outs,
                'probes': [], 'IORename': [], 'params': params}
    def out(i, mode, status=0):
        return {'index': i, 'type': 0, 'mode': mode, 'status': status,
                'realStatus': status, 'updateTime': 0}
    print("== HeaterMode décide des modes du chauffage ==")
    for hm, want in ((HEATER_NORMAL,    (0, 3)),
                     (HEATER_NOTARGET,  (0, 3)),
                     (HEATER_PAC_KLINK, (0, 1, 2, 3)),
                     (HEATER_PAC_MODBUS,(0, 1, 2, 3))):
        st = klereo_out_mode_states(pool([], hm), 4)
        check(f"HeaterMode {hm}", tuple(st), want)
    for hm, label in ((HEATER_NONE, 'HEAT_NONE'), (99, 'hors enum'), (None, 'params sans clé')):
        check(f"{label} -> lecture seule", klereo_out_mode_states(pool([], hm), 4), None)
    check("params absent -> lecture seule",
          klereo_out_mode_states({'idSystem': 1, 'outs': []}, 4), None)
    print("== le même numéro de mode change de nom selon HeaterMode ==")
    check("réchauffeur mode 3", klereo_out_mode_name(pool([], HEATER_NORMAL), 4, 3), 'Régulé')
    check("PAC mode 3",         klereo_out_mode_name(pool([], HEATER_PAC_KLINK), 4, 3), 'Réchauffe')
    check("PAC mode 1",         klereo_out_mode_name(pool([], HEATER_PAC_KLINK), 4, 1), 'Auto')
    check("PAC mode 2",         klereo_out_mode_name(pool([], HEATER_PAC_KLINK), 4, 2), 'Refroidit')
    check("PAC mode 0",         klereo_out_mode_name(pool([], HEATER_PAC_KLINK), 4, 0), 'Manuel')
    check("réchauffeur mode 1 (réservé)",
          klereo_out_mode_name(pool([], HEATER_NORMAL), 4, 1), None)
    check("chauffage sans HeaterMode", klereo_out_mode_name(pool([], None), 4, 0), None)
    check("mode 2 ailleurs inchangé", klereo_out_mode_name(pool([], None), 0, 2), 'Minuterie')
    print("== select chauffage : options et newState ==")
    for hm, opts in ((HEATER_NORMAL, ['Manuel', 'Régulé']),
                     (HEATER_PAC_MODBUS, ['Manuel', 'Auto', 'Refroidit', 'Réchauffe'])):
        c = Coordinator(pool([out(4, 0)], hm)); api = Api()
        sel = KlereoOutMode(api, c, c.data['outs'][0], 115, {}, None); sel.hass = Hass()
        check(f"options HeaterMode {hm}", sel._attr_options, opts)
        for opt in opts:
            api.calls.clear(); run(sel.async_select_option(opt)); sel._handle_coordinator_update()
            mode = sel._modes[opt]
            want_state = OUT_STATUS_OFF if mode == 0 else OUT_STATE_KEEP
            check(f"  {opt} -> SetOut", api.calls[-1], ('set_out', 4, want_state, mode))
    print("== switch chauffage ==")
    cases = [(HEATER_NORMAL, 0, False, True), (HEATER_NORMAL, 3, False, False),
             (HEATER_PAC_KLINK, 0, False, True), (HEATER_PAC_KLINK, 1, False, False),
             (HEATER_PAC_KLINK, 2, False, False), (HEATER_PAC_KLINK, 3, False, False)]
    for hm, mode, on_ok, off_ok in cases:
        for action, ok in (('on', on_ok), ('off', off_ok)):
            c = Coordinator(pool([out(4, mode)], hm)); api = Api()
            sw = KlereoOut(api, c, c.data['outs'][0], 115, {}, None); sw.hass = Hass()
            try:
                run(sw.async_turn_on() if action=='on' else sw.async_turn_off()); got = api.calls[-1]
            except ServiceValidationError as e: got = e.key
            want = ('set_out', 4, OUT_STATUS_ON if action=='on' else OUT_STATUS_OFF, mode) \
                   if ok else 'out_mode_no_switching'
            check(f"HeaterMode {hm} mode {mode} turn_{action}", got, want)
    print("== chauffage sans HeaterMode : lecture seule ==")
    c = Coordinator(pool([out(4, 3)], None))
    sw = KlereoOut(Api(), c, c.data['outs'][0], 115, {}, None); sw.hass = Hass()
    try: run(sw.async_turn_off()); got='PAS DE REFUS'
    except ServiceValidationError as e: got = e.key
    check("turn_off", got, 'out_read_only')
    check("ModeName", sw.extra_state_attributes['ModeName'], None)
    print("== non-régression : qui reçoit un sélecteur ==")
    for hm, want in ((HEATER_PAC_KLINK, [0,1,2,4,5,6,7,8,9,10,11,12,13,14,15]),
                     (HEATER_NONE,      [0,1,2,5,6,7,8,9,10,11,12,13,14,15]),
                     (None,             [0,1,2,5,6,7,8,9,10,11,12,13,14,15])):
        c = Coordinator(pool([out(i,0) for i in range(16)], hm)); added=[]
        class H(Hass): data = {'klereo': {'e': {'coordinator': c, 'api': Api()}}}
        class E: entry_id='e'; data={}
        run(select_setup(H(), E(), lambda es: added.extend(es)))
        check(f"HeaterMode {hm}", sorted(e._index for e in added), want)
    print("== non-régression : sorties toujours en lecture seule ==")
    for i, label in ((3,'désinfectant sans TraitMode'),):
        c = Coordinator(pool([out(i,0)], HEATER_PAC_KLINK))
        sw = KlereoOut(Api(), c, c.data['outs'][0], 115, {}, None); sw.hass = Hass()
        try: run(sw.async_turn_on()); got='PAS DE REFUS'
        except ServiceValidationError as e: got = e.key
        check(f"out{i} ({label})", got, 'out_read_only')
    print()

    check.assert_ok()
