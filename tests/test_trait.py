"""Vérifie le désinfectant et params.TraitMode."""
from klereo_stub import Api, Coordinator, Hass, ServiceValidationError, run


def test_trait(check):
    from klereo.select import KlereoOutMode, async_setup_entry as select_setup
    from klereo.switch import KlereoOut
    from klereo.entity import klereo_out_mode_name, klereo_out_mode_states
    from klereo.const import (OUT_STATE_KEEP, OUT_STATUS_OFF, OUT_STATUS_ON, OUT_MODES,
                              TRAIT_VARIANTS, PAYLOAD_VARIANTS, HEATER_PAC_KLINK,
                              TRAIT_NONE, TRAIT_CHLORE, TRAIT_ELECTRO_X, TRAIT_ELECTRO_COR,
                              TRAIT_OXYGEN, TRAIT_BROME, TRAIT_ELECTRO_BSV, TRAIT_IGNORE,
                              TRAIT_ELECTRO_KLR)
    def pool(outs, trait=None, heater=None):
        params = {}
        if trait is not None: params['TraitMode'] = trait
        if heater is not None: params['HeaterMode'] = heater
        return {'idSystem':115,'poolNickname':'T','outs':outs,'probes':[],
                'IORename':[],'params':params,'PumpMaxSpeed':3}
    def out(i, mode, status=0):
        return {'index':i,'type':0,'mode':mode,'status':status,'realStatus':status,'updateTime':0}
    print("== chaque mode permis porte un nom (sinon il disparaîtrait des options) ==")
    for t, (states, names) in sorted(TRAIT_VARIANTS.items()):
        P = pool([], trait=t)
        unnamed = [m for m in states if klereo_out_mode_name(P, 3, m) is None]
        check(f"TraitMode {t}", unnamed, [])
    print("== TraitMode décide des modes ==")
    for t, want in ((TRAIT_CHLORE,(0,2,3)), (TRAIT_ELECTRO_X,(0,2,3,4,5)),
                    (TRAIT_ELECTRO_COR,(0,2,3,4,5)), (TRAIT_ELECTRO_BSV,(0,2,3,4,5)),
                    (TRAIT_ELECTRO_KLR,(0,2,3,4,5)), (TRAIT_OXYGEN,(0,2,3)),
                    (TRAIT_BROME,(0,2,3,4))):
        check(f"TraitMode {t}", tuple(klereo_out_mode_states(pool([],trait=t), 3)), want)
    for t, label in ((TRAIT_NONE,'TRAIT_NONE'), (TRAIT_IGNORE,'TRAIT_IGNORE'),
                     (99,'hors enum'), (None,'absent')):
        check(f"{label} -> lecture seule", klereo_out_mode_states(pool([],trait=t), 3), None)
    print("== le mode 2 porte quatre noms selon le traitement ==")
    for t, want in ((TRAIT_CHLORE,'Volume fixe'), (TRAIT_OXYGEN,'Volume fixe'),
                    (TRAIT_BROME,'Temps fixe'), (TRAIT_ELECTRO_X,'Régulé température')):
        check(f"TraitMode {t} mode 2", klereo_out_mode_name(pool([],trait=t), 3, 2), want)
    check("mode 3 chlore", klereo_out_mode_name(pool([],trait=TRAIT_CHLORE), 3, 3), 'Régulé')
    check("mode 3 électro", klereo_out_mode_name(pool([],trait=TRAIT_ELECTRO_X), 3, 3), 'Régulé redox')
    check("mode 3 oxygène", klereo_out_mode_name(pool([],trait=TRAIT_OXYGEN), 3, 3), 'Régulé température')
    check("mode 5 (Choc) absent d'OUT_MODES", 5 in OUT_MODES, False)
    check("mode 5 nommé quand même", klereo_out_mode_name(pool([],trait=TRAIT_ELECTRO_X), 3, 5), 'Choc')
    check("mode 5 réservé sur le chlore", klereo_out_mode_name(pool([],trait=TRAIT_CHLORE), 3, 5), None)
    check("mode 2 ailleurs inchangé", klereo_out_mode_name(pool([]), 0, 2), 'Minuterie')
    check("dosing inchangé", klereo_out_mode_name(pool([]), 2, 2), 'Volume fixe')
    print("== le mode 2 est doseur sur le chlore, régulé sur l'électro ==")
    r_chl = klereo_out_mode_states(pool([],trait=TRAIT_CHLORE), 3)[2]
    r_ele = klereo_out_mode_states(pool([],trait=TRAIT_ELECTRO_X), 3)[2]
    check("chlore mode 2: on/off permis", r_chl.states, (0,1,2))
    check("électro mode 2: keep seul", r_ele.states, (2,))
    print("== select désinfectant ==")
    c = Coordinator(pool([out(3, 3)], trait=TRAIT_ELECTRO_KLR)); api = Api()
    sel = KlereoOutMode(api, c, c.data['outs'][0], 115, {}, None); sel.hass = Hass()
    check("options électro", sel._attr_options,
          ['Manuel','Régulé température','Régulé redox','Synchronisé filtration','Choc'])
    check("option courante", sel.current_option, 'Régulé redox')
    for opt, mode, st in (('Choc',5,OUT_STATE_KEEP), ('Synchronisé filtration',4,OUT_STATE_KEEP),
                          ('Manuel',0,OUT_STATUS_OFF)):
        api.calls.clear(); run(sel.async_select_option(opt)); sel._handle_coordinator_update()
        check(f"  {opt} -> SetOut", api.calls[-1], ('set_out', 3, st, mode))
    c = Coordinator(pool([out(3, 2)], trait=TRAIT_BROME)); api = Api()
    sel = KlereoOutMode(api, c, c.data['outs'][0], 115, {}, None); sel.hass = Hass()
    check("options brome", sel._attr_options,
          ['Manuel','Temps fixe','Régulé','Synchronisé filtration'])
    api.calls.clear(); run(sel.async_select_option('Temps fixe'))
    check("  Temps fixe -> keep", api.calls[-1], ('set_out', 3, OUT_STATE_KEEP, 2))
    print("== switch désinfectant ==")
    for t, mode, on_ok, off_ok in ((TRAIT_CHLORE,0,False,True), (TRAIT_CHLORE,2,True,True),
                                   (TRAIT_CHLORE,3,False,False), (TRAIT_ELECTRO_X,2,False,False),
                                   (TRAIT_ELECTRO_X,5,False,False), (TRAIT_BROME,2,True,True)):
        for action, ok in (('on',on_ok), ('off',off_ok)):
            c = Coordinator(pool([out(3, mode)], trait=t)); api = Api()
            sw = KlereoOut(api, c, c.data['outs'][0], 115, {}, None); sw.hass = Hass()
            try:
                run(sw.async_turn_on() if action=='on' else sw.async_turn_off()); got=api.calls[-1]
            except ServiceValidationError as e: got = e.key
            want = ('set_out',3,OUT_STATUS_ON if action=='on' else OUT_STATUS_OFF,mode) \
                   if ok else 'out_mode_no_switching'
            check(f"TraitMode {t} mode {mode} turn_{action}", got, want)
    print("== sans TraitMode : lecture seule, modes non nommés ==")
    c = Coordinator(pool([out(3, 3)], trait=None))
    sw = KlereoOut(Api(), c, c.data['outs'][0], 115, {}, None); sw.hass = Hass()
    try: run(sw.async_turn_off()); got='PAS DE REFUS'
    except ServiceValidationError as e: got = e.key
    check("turn_off", got, 'out_read_only')
    check("ModeName", sw.extra_state_attributes['ModeName'], None)
    print("== chlore hybride : ses propres règles, indépendantes de TraitMode ==")
    c = Coordinator(pool([out(15, 2)], trait=TRAIT_ELECTRO_X))
    sw = KlereoOut(Api(), c, c.data['outs'][0], 115, {}, None); sw.hass = Hass()
    run(sw.async_turn_on())
    check("out15 turn_on en Volume fixe", sw._api.calls[-1], ('set_out', 15, 1, 2))
    print("== qui reçoit un sélecteur ==")
    for trait, heater, want in ((TRAIT_CHLORE, HEATER_PAC_KLINK, list(range(16))),
                                (TRAIT_NONE,   HEATER_PAC_KLINK, [0,1,2,4,5,6,7,8,9,10,11,12,13,14,15]),
                                (TRAIT_BROME,  None,             [0,1,2,3,5,6,7,8,9,10,11,12,13,14,15])):
        c = Coordinator(pool([out(i,0) for i in range(16)], trait=trait, heater=heater)); added=[]
        class H(Hass): data={'klereo':{'e':{'coordinator':c,'api':Api()}}}
        class E: entry_id='e'; data={}
        run(select_setup(H(), E(), lambda es: added.extend(es)))
        check(f"TraitMode {trait} / HeaterMode {heater}", sorted(e._index for e in added), want)
    print()

    check.assert_ok()
