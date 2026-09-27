"""Vérifie les volumes dosés, temps de marche x débit de la pompe."""
from klereo_stub import Api, Coordinator, Hass, run


def test_dosed(check):
    from klereo.sensor import INFO_SENSORS, KlereoInfoSensor, async_setup_entry as sensor_setup
    from klereo.const import (CHLORINE_FLOW_PARAM, ML_PER_FLOW_UNIT,
                              PH_FLOW_PARAM, SECONDS_PER_HOUR)
    # (clé de l'entité, libellé, clé du compteur, clé du débit)
    DOSED = (
        ('phvolume',           'pH corrector volume', 'PHMinus_TotalTime',      PH_FLOW_PARAM),
        ('disinfectantvolume', 'Disinfectant volume', 'ElectroChlore_TotalTime', CHLORINE_FLOW_PARAM),
    )
    def pool(params):
        return {'idSystem':115,'poolNickname':'T','outs':[],'probes':[],'IORename':[],
                'params':params,'register':{'pin':'1234'},'device':0}
    def build(params):
        c = Coordinator(pool(params)); added=[]
        class H(Hass): data={'klereo':{'e':{'coordinator':c,'api':Api()}}}
        class E: entry_id='e'
        run(sensor_setup(H(), E(), lambda es: added.extend(es)))
        return c, {e._key.replace('klereo115',''): e for e in added if isinstance(e, KlereoInfoSensor)}
    BOTH = {'PHMinus_TotalTime': 3600, PH_FLOW_PARAM: 15,
            'ElectroChlore_TotalTime': 7200, CHLORINE_FLOW_PARAM: 20}

    print("== les constantes disent ce que le coffret annonce ==")
    check("clé débit pH",     PH_FLOW_PARAM, 'PHMinus_Debit')
    check("clé débit chlore", CHLORINE_FLOW_PARAM, 'Chlore_Debit')
    # Le débit est en 0,1 L/h : une unité vaut donc 100 mL par heure.
    check("0,1 L/h en mL/h",  ML_PER_FLOW_UNIT, 100)
    check("heure en secondes", SECONDS_PER_HOUR, 3600)

    print("== la conversion : une pompe 1,5 L/h pendant 1 h dose 1500 mL ==")
    c, info = build(dict(BOTH))
    check("les deux présents", sorted(k for k in info if k.endswith('volume') and k != 'volume'),
          ['disinfectantvolume', 'phvolume'])
    check("pH : 3600 s x 15 (1,5 L/h)", info['phvolume'].native_value, 1500)
    check("désinfectant : 7200 s x 20 (2 L/h)", info['disinfectantvolume'].native_value, 4000)

    print("== métadonnées ==")
    for key, label, _, _ in DOSED:
        e = info[key]
        check(f"{key}: nom",          e._name, label)
        check(f"{key}: unité",        e._attr_native_unit_of_measurement, 'mL')
        check(f"{key}: device_class", e._attr_device_class, 'volume')
        check(f"{key}: state_class",  e._attr_state_class, 'total_increasing')
        check(f"{key}: sans icône",   '_attr_icon' in e.__dict__, False)
        check(f"{key}: actif",        e._attr_entity_registry_enabled_default, True)
        check(f"{key}: unique_id",    e.unique_id, f'id_klereo115{key}')

    print("== chaque capteur lit bien SES deux clés ==")
    for key, _, tkey, fkey in DOSED:
        _, i = build({tkey: 3600, fkey: 10})
        check(f"seul {key}", sorted(k for k in i if k.endswith('volume')), [key])
        check(f"{key} = 1000 mL", i[key].native_value, 1000)

    print("== il faut les deux : un compteur sans débit ne donne rien ==")
    for key, _, tkey, fkey in DOSED:
        _, i = build({tkey: 3600})
        check(f"{key}: débit absent", key in i, False)
        _, i = build({fkey: 15})
        check(f"{key}: compteur absent", key in i, False)
    _, i = build({})
    check("payload vide", [k for k in i if k.endswith('volume')], [])

    print("== débit nul : un électrolyseur n'a pas de pompe doseuse ==")
    # ElectroChlore_TotalTime compte quand même la marche de la cellule, mais
    # un volume figé à 0 mL n'est pas une réponse.
    for key, _, tkey, fkey in DOSED:
        for zero in (0, 0.0, -1, -15):
            _, i = build({tkey: 3600, fkey: zero})
            check(f"{key}: débit {zero}", key in i, False)

    print("== valeurs aberrantes, des deux côtés ==")
    for key, _, tkey, fkey in DOSED:
        for bad in (None, '15', True, False, [1], {}):
            _, i = build({tkey: 3600, fkey: bad})
            check(f"{key}: débit {bad!r}", key in i, False)
            _, i = build({tkey: bad, fkey: 15})
            check(f"{key}: compteur {bad!r}", key in i, False)

    print("== un compteur à zéro est une vraie réponse : 0 mL, pas rien ==")
    for key, _, tkey, fkey in DOSED:
        _, i = build({tkey: 0, fkey: 15})
        check(f"{key}: créé", key in i, True)
        check(f"{key}: vaut 0", i[key].native_value, 0)

    print("== arrondi au millilitre entier ==")
    # 1 s a 0,1 L/h = 0,0277 mL : la pompe n'a pas cette précision.
    _, i = build({'PHMinus_TotalTime': 1, PH_FLOW_PARAM: 1})
    check("1 s x 0,1 L/h -> 0", i['phvolume'].native_value, 0)
    _, i = build({'PHMinus_TotalTime': 100, PH_FLOW_PARAM: 1})
    check("100 s x 0,1 L/h -> 3", i['phvolume'].native_value, 3)
    check("entier, pas flottant", isinstance(i['phvolume'].native_value, int), True)
    # Une saison entière : 912 h a 1,5 L/h.
    _, i = build({'PHMinus_TotalTime': 3283200, PH_FLOW_PARAM: 15})
    check("912 h x 1,5 L/h", i['phvolume'].native_value, 1368000)
    # Un débit décimal reste exploitable.
    _, i = build({'PHMinus_TotalTime': 3600, PH_FLOW_PARAM: 12.5})
    check("débit 1,25 L/h", i['phvolume'].native_value, 1250)

    print("== il suit le payload ==")
    c, i = build(dict(BOTH))
    c.data['params']['PHMinus_TotalTime'] = 7200
    check("compteur qui avance", i['phvolume'].native_value, 3000)
    c.data['params'][PH_FLOW_PARAM] = 30
    check("pompe remplacee", i['phvolume'].native_value, 6000)
    c.data['params'].pop(PH_FLOW_PARAM)
    check("débit disparu -> inconnu", i['phvolume'].native_value, None)

    print("== les compteurs en heures ne bougent pas ==")
    _, i = build(dict(BOTH, VolumeEau=45, Filtration_TotalTime=3600,
                      Chauff_TotalTime=7200))
    check("liste complète", sorted(i),
          ['device', 'disinfectanttime', 'disinfectantvolume',
           'filtrationtime', 'heatingtime', 'phtime', 'phvolume', 'pin', 'volume'])
    check("pH en heures intact",   i['phtime'].native_value, 1.0)
    check("pH en heures, unité",   i['phtime']._attr_native_unit_of_measurement, 'h')
    check("désinf. en heures",     i['disinfectanttime'].native_value, 2.0)
    check("volume du bassin en m³", i['volume']._attr_native_unit_of_measurement, 'm³')
    check("volume du bassin désactivé", i['volume']._attr_entity_registry_enabled_default, False)

    print("== le chlore hybride (sortie 15) n'a pas de compteur, donc pas de volume ==")
    _, i = build({CHLORINE_FLOW_PARAM: 20})
    check("débit seul ne crée rien", [k for k in i if k.endswith('volume')], [])
    print()

    check.assert_ok()
