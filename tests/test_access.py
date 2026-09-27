"""Vérifie les niveaux d’accès."""
from klereo_stub import Api, Coordinator, Hass, ServiceValidationError, run


def test_access(check):
    from klereo.number import KlereoWaterSetpoint
    from klereo.switch import KlereoOut
    from klereo.entity import klereo_access, klereo_may_command
    from klereo.const import ACCESS_COMMAND_MIN, ACCESS_PARAM_ANY
    def pool(access='absent'):
        d = {'idSystem':115,'poolNickname':'T','probes':[],'IORename':[],
             'PumpMaxSpeed':3,'params':{'ConsigneEau':28.0},
             'outs':[{'index':0,'type':0,'mode':0,'status':1,'realStatus':1,'updateTime':0}]}
        if access != 'absent': d['access'] = access
        return d
    def pool2(access='absent', index=0):
        d = pool(access)
        mode = 2 if index in (2, 3, 8, 15) else 0
        d['outs'] = [{'index':index,'type':0,'mode':mode,'status':1,'realStatus':1,
                      'updateTime':0}]
        d['params']['TraitMode'] = 1
        return d
    print("== les seuils sont ceux du PHP ==")
    check("commande", ACCESS_COMMAND_MIN, 10)
    check("tous paramètres", ACCESS_PARAM_ANY, 16)
    print("== lecture du champ ==")
    for a, want in ((16, 16), (10, 10), (0, 0), (-1, -1)):
        check(f"access={a}", klereo_access(pool(a)), want)
    for a, why in (('absent','champ absent'), (None,'None'), ('16','texte'), (True,'booléen')):
        check(f"{why} -> inconnu", klereo_access(pool(a)), None)
    print("== inconnu vaut autorisé : on ne verrouille personne ==")
    check("absent", klereo_may_command(pool('absent')), True)
    check("texte", klereo_may_command(pool('16')), True)
    for a, want in ((16, True), (10, True), (9, False), (0, False), (-1, False)):
        check(f"access={a}", klereo_may_command(pool(a)), want)
    print("== la consigne refuse localement sous le niveau 10 ==")
    for a in (9, 0):
        c = Coordinator(pool(a)); api = Api()
        sp = KlereoWaterSetpoint(api, c, 115, {}); sp.hass = Hass()
        try: run(sp.async_set_native_value(26.0)); got='ENVOYÉ'
        except ServiceValidationError as e: got = (e.key, e.placeholders['access'])
        check(f"access={a}", got, ('account_read_only', str(a)))
        check(f"  aucun appel réseau", api.calls, [])
        check(f"  mais la lecture marche", sp.native_value, 28.0)
    print("== au-dessus, et quand c'est inconnu, ça part ==")
    for a in (10, 16, 'absent'):
        c = Coordinator(pool(a)); api = Api()
        sp = KlereoWaterSetpoint(api, c, 115, {}); sp.hass = Hass()
        run(sp.async_set_native_value(26.0))
        check(f"access={a}", api.calls[-1], ('set_param', 'ConsigneEau', 26.0, None))
    print("== les sorties suivent la règle de SetOut.php ==")
    from klereo.entity import klereo_out_refusal
    from klereo.const import TREATMENT_OUT_INDEXES
    from klereo.select import KlereoOutMode
    from klereo.number import KlereoFiltrationSpeed
    check("set privilégié = celui du serveur", sorted(TREATMENT_OUT_INDEXES), [2,3,8,15])
    for a in (None, 16, 20):
        for i in range(16):
            check(f"  access={a} out{i} autorisé", klereo_out_refusal(pool2(a), i), None)
    for a in (0, 9, -1):
        for i in (0, 1, 2, 15):
            check(f"  access={a} out{i}", klereo_out_refusal(pool2(a), i), 'account_read_only')
    for a in (10, 15):
        for i in sorted(TREATMENT_OUT_INDEXES):
            check(f"  access={a} out{i} réservé", klereo_out_refusal(pool2(a), i),
                  'out_needs_full_access')
        for i in (0, 1, 4, 5, 7, 9, 14):
            check(f"  access={a} out{i} permis", klereo_out_refusal(pool2(a), i), None)
    print("== le switch refuse localement, sans appel réseau ==")
    for a, i, key in ((9, 0, 'account_read_only'), (10, 2, 'out_needs_full_access'),
                      (15, 15, 'out_needs_full_access')):
        c = Coordinator(pool2(a, i)); api = Api()
        sw = KlereoOut(api, c, c.data['outs'][0], 115, {}, None); sw.hass = Hass()
        try: run(sw.async_turn_off()); got='ENVOYÉ'
        except ServiceValidationError as e: got=(e.key, e.placeholders['access'])
        check(f"access={a} out{i}", got, (key, str(a)))
        check("  aucun appel", api.calls, [])
    print("== le sélecteur de mode aussi ==")
    c = Coordinator(pool2(10, 2)); api = Api()
    se = KlereoOutMode(api, c, c.data['outs'][0], 115, {}, None); se.hass = Hass()
    try: run(se.async_select_option(se._attr_options[0])); got='ENVOYÉ'
    except ServiceValidationError as e: got=e.key
    check("pH en access=10", got, 'out_needs_full_access')
    check("  aucun appel", api.calls, [])
    print("== et la vitesse de filtration, sur la sortie 1 ==")
    for a, want in ((9, 'account_read_only'), (10, None), (16, None)):
        c = Coordinator(pool2(a, 1)); api = Api()
        n = KlereoFiltrationSpeed(api, c, 115, {}, 3, None); n.hass = Hass()
        try: run(n.async_set_native_value(2)); got=None
        except ServiceValidationError as e: got=e.key
        check(f"access={a}", got, want)
    print("== au-dessus du seuil, ça part vraiment ==")
    for a in (16, 'absent'):
        c = Coordinator(pool2(a, 2)); api = Api()
        sw = KlereoOut(api, c, c.data['outs'][0], 115, {}, None); sw.hass = Hass()
        run(sw.async_turn_off())
        check(f"pH access={a}", api.calls[-1], ('set_out', 2, 0, 2))
    print()

    check.assert_ok()
