"""Vérifie les volumes dosés : temps de marche x débit de la pompe."""
from copy import deepcopy

from klereo_stub import Api, Coordinator, Hass, run


def test_dosed(check):
    from klereo.sensor import KlereoInfoSensor, async_setup_entry as sensor_setup
    from klereo.const import (CHLORINE_FLOW_PARAM, FLOCCULANT_OUT_INDEX,
                              HYBRID_CHLORINE_OUT_INDEX, HYBRID_CHLORINE_TIME_KEY,
                              ML_PER_FLOW_UNIT, OUT_TOTAL_TIME_KEY, PH_FLOW_PARAM,
                              PUMP_DOSED_TREATMENTS, SECONDS_PER_HOUR,
                              TREATMENT_OUT_INDEXES,
                              TRAIT_NONE, TRAIT_CHLORE, TRAIT_ELECTRO_X,
                              TRAIT_ELECTRO_COR, TRAIT_OXYGEN, TRAIT_BROME,
                              TRAIT_ELECTRO_BSV, TRAIT_IGNORE, TRAIT_ELECTRO_KLR)
    VOLUMES = ('phvolume', 'disinfectantvolume', 'flocculantvolume',
               'hybridchlorinevolume')
    def out(index, total=None, key='totalTime'):
        o = {'index':index,'type':0,'mode':0,'status':0,'realStatus':0,'updateTime':0}
        if total is not None: o[key] = total
        return o
    def pool(params=None, outs=None, extra=None):
        # deepcopy : le bloc « il suit le payload » mute coordinator.data, et
        # sans copie il mutait aussi le FULL partagé par les blocs suivants.
        d = {'idSystem':115,'poolNickname':'T','outs':deepcopy(outs) or [],'probes':[],
             'IORename':[],'params':deepcopy(params) or {},
             'register':{'pin':'1234'},'device':0}
        if extra is not None: d['ExtraParams'] = deepcopy(extra)
        return d
    def build(params=None, outs=None, extra=None):
        c = Coordinator(pool(params, outs, extra)); added=[]
        class H(Hass): data={'klereo':{'e':{'coordinator':c,'api':Api()}}}
        class E: entry_id='e'
        run(sensor_setup(H(), E(), lambda es: added.extend(es)))
        return c, {e._key.replace('klereo115',''): e for e in added if isinstance(e, KlereoInfoSensor)}
    def vols(info):
        return sorted(k for k in info if k in VOLUMES)
    # Un bassin au chlore, les quatre pompes qui tournent.
    FULL = dict(
        params={'TraitMode': TRAIT_CHLORE,
                'PHMinus_TotalTime': 3600,      PH_FLOW_PARAM: 15,
                'ElectroChlore_TotalTime': 7200, CHLORINE_FLOW_PARAM: 20},
        outs=[out(FLOCCULANT_OUT_INDEX, 1800)],
        extra={HYBRID_CHLORINE_TIME_KEY: 900},
    )

    print("== les constantes disent ce que le coffret annonce ==")
    check("débit pH",        PH_FLOW_PARAM, 'PHMinus_Debit')
    check("débit chlore",    CHLORINE_FLOW_PARAM, 'Chlore_Debit')
    check("clé hybride",     HYBRID_CHLORINE_TIME_KEY, 'HybChl_TotalTime')
    check("clé outs",        OUT_TOTAL_TIME_KEY, 'totalTime')
    check("floculant = 8",   FLOCCULANT_OUT_INDEX, 8)
    check("hybride = 15",    HYBRID_CHLORINE_OUT_INDEX, 15)
    check("0,1 L/h en mL/h", ML_PER_FLOW_UNIT, 100)
    check("heure en s",      SECONDS_PER_HOUR, 3600)
    check("les quatre sorties de traitement", sorted(TREATMENT_OUT_INDEXES), [2,3,8,15])
    print("== seuls le chlore et l'oxygène dosent avec une pompe ==")
    check("traitements à pompe", sorted(PUMP_DOSED_TREATMENTS),
          sorted([TRAIT_CHLORE, TRAIT_OXYGEN]))

    print("== la conversion : 1,5 L/h pendant 1 h = 1500 mL ==")
    c, i = build(**FULL)
    check("les quatre présents", vols(i), sorted(VOLUMES))
    check("pH : 3600 s x 15",          i['phvolume'].native_value, 1500)
    check("désinfectant : 7200 s x 20", i['disinfectantvolume'].native_value, 4000)
    check("floculant : 1800 s x 20",    i['flocculantvolume'].native_value, 1000)
    check("hybride : 900 s x 20",       i['hybridchlorinevolume'].native_value, 500)

    print("== métadonnées, identiques sur les quatre ==")
    LABELS = {'phvolume':'pH corrector volume', 'disinfectantvolume':'Disinfectant volume',
              'flocculantvolume':'Flocculant volume',
              'hybridchlorinevolume':'Hybrid chlorine volume'}
    for key in VOLUMES:
        e = i[key]
        check(f"{key}: nom",          e._name, LABELS[key])
        check(f"{key}: unité",        e._attr_native_unit_of_measurement, 'mL')
        check(f"{key}: device_class", e._attr_device_class, 'volume')
        check(f"{key}: state_class",  e._attr_state_class, 'total_increasing')
        check(f"{key}: sans icône",   '_attr_icon' in e.__dict__, False)
        check(f"{key}: actif",        e._attr_entity_registry_enabled_default, True)
        check(f"{key}: unique_id",    e.unique_id, f'id_klereo115{key}')

    print("== chaque volume lit SA source : params, outs[], ExtraParams ==")
    _, i = build(params={'PHMinus_TotalTime': 3600, PH_FLOW_PARAM: 10})
    check("pH seul", vols(i), ['phvolume'])
    check("pH = 1000 mL", i['phvolume'].native_value, 1000)
    _, i = build(params={'TraitMode': TRAIT_CHLORE, 'ElectroChlore_TotalTime': 3600,
                         CHLORINE_FLOW_PARAM: 10})
    check("désinfectant seul", vols(i), ['disinfectantvolume'])
    _, i = build(params={CHLORINE_FLOW_PARAM: 10}, outs=[out(FLOCCULANT_OUT_INDEX, 3600)])
    check("floculant seul", vols(i), ['flocculantvolume'])
    check("floculant = 1000 mL", i['flocculantvolume'].native_value, 1000)
    _, i = build(params={CHLORINE_FLOW_PARAM: 10}, extra={HYBRID_CHLORINE_TIME_KEY: 3600})
    check("hybride seul", vols(i), ['hybridchlorinevolume'])
    check("hybride = 1000 mL", i['hybridchlorinevolume'].native_value, 1000)

    print("== le floculant : la bonne clé, sur la bonne sortie ==")
    _, i = build(params={CHLORINE_FLOW_PARAM: 10},
                 outs=[out(FLOCCULANT_OUT_INDEX, 3600, OUT_TOTAL_TIME_KEY)])
    check("outs[8].totalTime", i['flocculantvolume'].native_value, 1000)
    # La majuscule n'est pas la clé du coffret : elle ne doit rien créer.
    _, i = build(params={CHLORINE_FLOW_PARAM: 10},
                 outs=[out(FLOCCULANT_OUT_INDEX, 3600, 'TotalTime')])
    check("outs[8].TotalTime ignoré", 'flocculantvolume' in i, False)
    _, i = build(params={CHLORINE_FLOW_PARAM: 10}, outs=[out(FLOCCULANT_OUT_INDEX)])
    check("sortie sans compteur", 'flocculantvolume' in i, False)
    _, i = build(params={CHLORINE_FLOW_PARAM: 10}, outs=[out(2, 3600), out(9, 3600)])
    check("compteur d'une autre sortie ignoré", 'flocculantvolume' in i, False)
    _, i = build(params={CHLORINE_FLOW_PARAM: 10}, outs=[])
    check("aucune sortie", 'flocculantvolume' in i, False)

    print("== l'hybride : un bassin sans ExtraParams n'a rien ==")
    _, i = build(params={CHLORINE_FLOW_PARAM: 10})
    check("ExtraParams absent", 'hybridchlorinevolume' in i, False)
    _, i = build(params={CHLORINE_FLOW_PARAM: 10}, extra={})
    check("ExtraParams vide", 'hybridchlorinevolume' in i, False)
    _, i = build(params={CHLORINE_FLOW_PARAM: 10}, extra={'HybChl_Total': 3600})
    check("autre clé ignorée", 'hybridchlorinevolume' in i, False)

    print("== LE point : le désinfectant reste en heures sur brome et électrolyse ==")
    GATE = {TRAIT_CHLORE: True,  TRAIT_OXYGEN: True,
            TRAIT_BROME: False, TRAIT_ELECTRO_X: False, TRAIT_ELECTRO_COR: False,
            TRAIT_ELECTRO_BSV: False, TRAIT_ELECTRO_KLR: False,
            TRAIT_NONE: False, TRAIT_IGNORE: False}
    for trait, dosed in sorted(GATE.items()):
        _, i = build(params={'TraitMode': trait, 'ElectroChlore_TotalTime': 7200,
                             CHLORINE_FLOW_PARAM: 20})
        check(f"TraitMode {trait}: volume", 'disinfectantvolume' in i, dosed)
        check(f"TraitMode {trait}: heures", i['disinfectanttime'].native_value, 2.0)
    for absent in ({}, {'TraitMode': 99}, {'TraitMode': None}, {'TraitMode': '1'}):
        _, i = build(params=dict(absent, ElectroChlore_TotalTime=7200,
                                 **{CHLORINE_FLOW_PARAM: 20}))
        check(f"TraitMode {absent.get('TraitMode', 'absent')!r}",
              'disinfectantvolume' in i, False)

    print("== et le garde ne touche QUE le désinfectant ==")
    for trait in (TRAIT_BROME, TRAIT_ELECTRO_KLR):
        _, i = build(params={'TraitMode': trait, 'PHMinus_TotalTime': 3600,
                             PH_FLOW_PARAM: 15, CHLORINE_FLOW_PARAM: 20,
                             'ElectroChlore_TotalTime': 7200},
                     outs=[out(FLOCCULANT_OUT_INDEX, 1800)],
                     extra={HYBRID_CHLORINE_TIME_KEY: 900})
        check(f"TraitMode {trait}: les trois autres", vols(i),
              ['flocculantvolume', 'hybridchlorinevolume', 'phvolume'])
        check(f"TraitMode {trait}: floculant chiffré", i['flocculantvolume'].native_value, 1000)

    print("== il faut les deux : compteur et débit ==")
    _, i = build(params={'TraitMode': TRAIT_CHLORE, 'PHMinus_TotalTime': 3600,
                         'ElectroChlore_TotalTime': 3600},
                 outs=[out(FLOCCULANT_OUT_INDEX, 3600)],
                 extra={HYBRID_CHLORINE_TIME_KEY: 3600})
    check("aucun débit déclaré", vols(i), [])
    _, i = build(params={'TraitMode': TRAIT_CHLORE, PH_FLOW_PARAM: 15,
                         CHLORINE_FLOW_PARAM: 20})
    check("débits seuls", vols(i), [])

    print("== débit nul ou négatif : pas de pompe, pas de capteur ==")
    for zero in (0, 0.0, -1, -20):
        _, i = build(params={'TraitMode': TRAIT_CHLORE, 'PHMinus_TotalTime': 3600,
                             PH_FLOW_PARAM: zero, CHLORINE_FLOW_PARAM: zero,
                             'ElectroChlore_TotalTime': 3600},
                     outs=[out(FLOCCULANT_OUT_INDEX, 3600)],
                     extra={HYBRID_CHLORINE_TIME_KEY: 3600})
        check(f"débit {zero}", vols(i), [])

    print("== valeurs aberrantes, des deux côtés ==")
    for bad in (None, '15', True, False, [1], {}):
        _, i = build(params={'PHMinus_TotalTime': 3600, PH_FLOW_PARAM: bad})
        check(f"pH, débit {bad!r}", 'phvolume' in i, False)
        _, i = build(params={'PHMinus_TotalTime': bad, PH_FLOW_PARAM: 15})
        check(f"pH, compteur {bad!r}", 'phvolume' in i, False)
        _, i = build(params={CHLORINE_FLOW_PARAM: 20},
                     outs=[out(FLOCCULANT_OUT_INDEX, bad)])
        check(f"floculant, compteur {bad!r}", 'flocculantvolume' in i, False)
        _, i = build(params={CHLORINE_FLOW_PARAM: 20}, extra={HYBRID_CHLORINE_TIME_KEY: bad})
        check(f"hybride, compteur {bad!r}", 'hybridchlorinevolume' in i, False)

    print("== un compteur à zéro est une vraie réponse : 0 mL ==")
    _, i = build(params={'TraitMode': TRAIT_CHLORE, 'PHMinus_TotalTime': 0,
                         PH_FLOW_PARAM: 15, CHLORINE_FLOW_PARAM: 20,
                         'ElectroChlore_TotalTime': 0},
                 outs=[out(FLOCCULANT_OUT_INDEX, 0)],
                 extra={HYBRID_CHLORINE_TIME_KEY: 0})
    check("les quatre créés", vols(i), sorted(VOLUMES))
    for key in VOLUMES:
        check(f"{key} = 0", i[key].native_value, 0)

    print("== arrondi au millilitre entier ==")
    _, i = build(params={'PHMinus_TotalTime': 1, PH_FLOW_PARAM: 1})
    check("1 s x 0,1 L/h -> 0", i['phvolume'].native_value, 0)
    _, i = build(params={'PHMinus_TotalTime': 100, PH_FLOW_PARAM: 1})
    check("100 s x 0,1 L/h -> 3", i['phvolume'].native_value, 3)
    check("entier, pas flottant", isinstance(i['phvolume'].native_value, int), True)
    _, i = build(params={'PHMinus_TotalTime': 3283200, PH_FLOW_PARAM: 15})
    check("912 h x 1,5 L/h", i['phvolume'].native_value, 1368000)
    _, i = build(params={'PHMinus_TotalTime': 3600, PH_FLOW_PARAM: 12.5})
    check("débit décimal 1,25 L/h", i['phvolume'].native_value, 1250)

    print("== il suit le payload ==")
    c, i = build(**FULL)
    c.data['params']['PHMinus_TotalTime'] = 7200
    check("compteur qui avance", i['phvolume'].native_value, 3000)
    c.data['outs'][0]['totalTime'] = 3600
    check("floculant qui avance", i['flocculantvolume'].native_value, 2000)
    c.data['ExtraParams'][HYBRID_CHLORINE_TIME_KEY] = 1800
    check("hybride qui avance", i['hybridchlorinevolume'].native_value, 1000)
    c.data['params'][CHLORINE_FLOW_PARAM] = 40
    check("pompe remplacée : floculant", i['flocculantvolume'].native_value, 4000)
    check("pompe remplacée : hybride",  i['hybridchlorinevolume'].native_value, 2000)
    check("pompe remplacée : désinf.",  i['disinfectantvolume'].native_value, 8000)
    check("le pH ne bouge pas",         i['phvolume'].native_value, 3000)
    c.data['params']['TraitMode'] = TRAIT_BROME
    check("passage au brome -> inconnu", i['disinfectantvolume'].native_value, None)
    c.data['params'].pop(CHLORINE_FLOW_PARAM)
    check("débit disparu", i['flocculantvolume'].native_value, None)

    print("== les compteurs en heures ne bougent pas ==")
    _, i = build(params=dict(FULL['params'], VolumeEau=45,
                             Filtration_TotalTime=3600, Chauff_TotalTime=7200),
                 outs=FULL['outs'], extra=FULL['extra'])
    check("liste complète", sorted(i),
          ['device', 'disinfectanttime', 'disinfectantvolume', 'filtrationtime',
           'flocculantvolume', 'heatingtime', 'hybridchlorinevolume', 'phtime',
           'phvolume', 'pin', 'volume'])
    check("pH en heures",        i['phtime'].native_value, 1.0)
    check("pH en heures, unité", i['phtime']._attr_native_unit_of_measurement, 'h')
    check("désinf. en heures",   i['disinfectanttime'].native_value, 2.0)
    check("bassin en m³",        i['volume']._attr_native_unit_of_measurement, 'm³')
    check("bassin désactivé",    i['volume']._attr_entity_registry_enabled_default, False)
    print()

    check.assert_ok()
