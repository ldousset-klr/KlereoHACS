"""Vérifie les contrôles désactivés par défaut."""
from klereo_stub import Api, Coordinator, Hass, run


def test_enabled(check):
    from klereo.switch import KlereoOut, async_setup_entry as switch_setup
    from klereo.select import async_setup_entry as select_setup
    from klereo.number import KlereoFiltrationSpeed, async_setup_entry as number_setup
    from klereo.sensor import async_setup_entry as sensor_setup
    from klereo.const import OUTS_DISABLED_BY_DEFAULT, OUT_LABELS, TRAIT_CHLORE, HEATER_PAC_KLINK
    ENABLED  = [0, 1, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14]
    DISABLED = [2, 3, 8, 15]
    def pool():
        return {'idSystem':115,'poolNickname':'T','probes':[],'IORename':[],
                'PumpMaxSpeed':3,
                'params':{'TraitMode':TRAIT_CHLORE,'HeaterMode':HEATER_PAC_KLINK,
                          'VolumeEau':45,'Filtration_TotalTime':3600},
                'register':{'pin':'1234'},'device':0,
                'outs':[{'index':i,'type':0,'mode':2 if i in (3,15) else 0,'status':1,
                         'realStatus':1,'updateTime':0} for i in range(16)]}
    def setup(fn):
        c = Coordinator(pool()); added=[]
        class H(Hass): data={'klereo':{'e':{'coordinator':c,'api':Api()}}}
        class E: entry_id='e'
        run(fn(H(), E(), lambda es: added.extend(es)))
        return added
    print("== la table dit ce que l'utilisateur a demandé ==")
    check("désactivées", sorted(OUTS_DISABLED_BY_DEFAULT), DISABLED)
    for i in DISABLED: check(f"  {i} = {OUT_LABELS[i]}", True, True)
    check("activées", [i for i in range(16) if i not in OUTS_DISABLED_BY_DEFAULT], ENABLED)
    print("== switch ==")
    sw = {e._index: e for e in setup(switch_setup)}
    check("16 switches créés", sorted(sw), list(range(16)))
    check("activés", sorted(i for i,e in sw.items()
                            if e._attr_entity_registry_enabled_default), ENABLED)
    check("désactivés", sorted(i for i,e in sw.items()
                               if not e._attr_entity_registry_enabled_default), DISABLED)
    print("== sélecteur de mode ==")
    se = {e._index: e for e in setup(select_setup)}
    check("activés", sorted(i for i,e in se.items()
                            if e._attr_entity_registry_enabled_default), ENABLED)
    check("désactivés", sorted(i for i,e in se.items()
                               if not e._attr_entity_registry_enabled_default), DISABLED)
    print("== la vitesse de filtration suit la sortie 1, donc reste active ==")
    nb = setup(number_setup)
    check("une entité vitesse", len(nb), 1)
    check("activée", getattr(nb[0], '_attr_entity_registry_enabled_default', True), True)
    print("== les capteurs ne bougent pas ==")
    sn = {e._key.replace('klereo115',''): e for e in setup(sensor_setup)}
    check("volume toujours désactivé", sn['volume']._attr_entity_registry_enabled_default, False)
    check("compteur filtration actif", sn['filtrationtime']._attr_entity_registry_enabled_default, True)
    check("pin actif", sn['pin']._attr_entity_registry_enabled_default, True)
    print("== désactivé ne veut pas dire non pilotable ==")
    c = Coordinator(pool()); api = Api()
    out3 = [o for o in c.data['outs'] if o['index']==3][0]
    s3 = KlereoOut(api, c, out3, 115, {}, None); s3.hass = Hass()
    check("out3 désactivé", s3._attr_entity_registry_enabled_default, False)
    run(s3.async_turn_off())
    check("mais l'écriture marche une fois activé", api.calls[-1], ('set_out', 3, 0, 2))
    print()

    check.assert_ok()
