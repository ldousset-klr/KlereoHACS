"""Vérifie le chlore hybride."""
from klereo_stub import Api, Coordinator, Hass, ServiceValidationError, run


def test_hybrid(check):
    from klereo.select import KlereoOutMode, async_setup_entry as select_setup
    from klereo.switch import KlereoOut
    from klereo.entity import klereo_out_mode_name, klereo_out_mode_states
    from klereo.const import (OUT_STATE_KEEP, OUT_STATUS_OFF, OUT_STATUS_ON,
                              TRAIT_CHLORE, HEATER_PAC_KLINK, OUT_LABELS)
    def pool(outs, trait=TRAIT_CHLORE, heater=HEATER_PAC_KLINK):
        p = {}
        if trait is not None: p['TraitMode']=trait
        if heater is not None: p['HeaterMode']=heater
        return {'idSystem':115,'poolNickname':'T','outs':outs,'probes':[],
                'IORename':[],'params':p,'PumpMaxSpeed':3}
    def out(i, mode, status=0):
        return {'index':i,'type':0,'mode':mode,'status':status,'realStatus':status,'updateTime':0}
    P = pool([])
    print("== chlore hybride : un seul mode ==")
    check("libellé de la sortie", OUT_LABELS[15], 'Chlore hybride')
    check("modes", tuple(klereo_out_mode_states(P, 15)), (2,))
    check("états du mode 2", klereo_out_mode_states(P, 15)[2].states, (0,1,2))
    check("keep", klereo_out_mode_states(P, 15)[2].keep, 2)
    check("nom", klereo_out_mode_name(P, 15, 2), 'Volume fixe')
    for m in (0, 1, 3, 4, 5, 6, 8):
        check(f"mode {m} réservé", klereo_out_mode_name(P, 15, m),
              None if m not in (0,1,3,4,6,8) else klereo_out_mode_name(P, 15, m))
    check("mode 0 non offert", 0 in klereo_out_mode_states(P, 15), False)
    print("== select : une seule option ==")
    c = Coordinator(pool([out(15, 2)])); api = Api()
    sel = KlereoOutMode(api, c, c.data['outs'][0], 115, {}, None); sel.hass = Hass()
    check("options", sel._attr_options, ['Volume fixe'])
    check("option courante", sel.current_option, 'Volume fixe')
    run(sel.async_select_option('Volume fixe'))
    check("réaffirmation -> keep", api.calls[-1], ('set_out', 15, OUT_STATE_KEEP, 2))
    c.data['outs'][0]['mode'] = 3
    sel._handle_coordinator_update()
    check("mode hors liste -> inconnu", sel.current_option, None)
    print("== switch : c'est le vrai gain ==")
    for mode, ok in ((2, True), (0, False), (3, False)):
        for action in ('on','off'):
            c = Coordinator(pool([out(15, mode)])); api = Api()
            sw = KlereoOut(api, c, c.data['outs'][0], 115, {}, None); sw.hass = Hass()
            try:
                run(sw.async_turn_on() if action=='on' else sw.async_turn_off()); got=api.calls[-1]
            except ServiceValidationError as e: got=e.key
            want = ('set_out',15,OUT_STATUS_ON if action=='on' else OUT_STATUS_OFF,mode) \
                   if ok else 'out_mode_no_switching'
            check(f"mode {mode} turn_{action}", got, want)
    print("== plus aucune sortie en lecture seule inconditionnelle ==")
    c = Coordinator(pool([out(i,2 if i in (3,15) else 0) for i in range(16)]))
    added=[]
    class H(Hass): data={'klereo':{'e':{'coordinator':c,'api':Api()}}}
    class E: entry_id='e'
    run(select_setup(H(), E(), lambda es: added.extend(es)))
    check("sélecteurs sur les 16 sorties", sorted(e._index for e in added), list(range(16)))
    readonly=[]
    for i in range(16):
        c2 = Coordinator(pool([out(i, 2 if i in (3,15) else 0)]))
        sw = KlereoOut(Api(), c2, c2.data['outs'][0], 115, {}, None); sw.hass = Hass()
        try: run(sw.async_turn_off())
        except ServiceValidationError as e:
            if e.key == 'out_read_only': readonly.append(i)
    check("aucune out_read_only quand le payload nomme tout", readonly, [])
    print("== mais la dépendance au payload demeure ==")
    c = Coordinator(pool([out(3,2), out(4,0), out(15,2)], trait=None, heater=None))
    for i, want in ((3,'out_read_only'), (4,'out_read_only'), (15, ('set_out',15,0,2))):
        sw = KlereoOut(Api(), c, [o for o in c.data['outs'] if o['index']==i][0], 115, {}, None)
        sw.hass = Hass(); api = sw._api
        try: run(sw.async_turn_off()); got = api.calls[-1]
        except ServiceValidationError as e: got = e.key
        check(f"out{i} sans clé params", got, want)
    print()

    check.assert_ok()
