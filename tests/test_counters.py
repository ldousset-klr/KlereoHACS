"""Vérifie les quatre compteurs de marche."""
from klereo_stub import Api, Coordinator, Hass, run


def test_counters(check):
    from klereo.sensor import INFO_SENSORS, KlereoInfoSensor, async_setup_entry as sensor_setup
    COUNTERS = {
        'filtrationtime':   ('Filtration runtime',    'Filtration_TotalTime'),
        'phtime':           ('pH corrector runtime',  'PHMinus_TotalTime'),
        'disinfectanttime': ('Disinfectant runtime',  'ElectroChlore_TotalTime'),
        'heatingtime':      ('Heating runtime',       'Chauff_TotalTime'),
    }
    ALL = {k: (i+1)*3600 for i, k in enumerate(v[1] for v in COUNTERS.values())}
    def pool(params):
        return {'idSystem':115,'poolNickname':'T','outs':[],'probes':[],'IORename':[],
                'params':params,'register':{'pin':'1234'},'device':0}
    def build(params):
        c = Coordinator(pool(params)); added=[]
        class H(Hass): data={'klereo':{'e':{'coordinator':c,'api':Api()}}}
        class E: entry_id='e'
        run(sensor_setup(H(), E(), lambda es: added.extend(es)))
        return c, {e._key.replace('klereo115',''): e for e in added if isinstance(e, KlereoInfoSensor)}
    print("== les quatre compteurs ==")
    c, info = build(dict(ALL))
    check("présents", sorted(k for k in info if k.endswith('time')), sorted(COUNTERS))
    for i, (key, (label, pkey)) in enumerate(COUNTERS.items()):
        e = info[key]
        check(f"{key}: nom",         e._name, label)
        check(f"{key}: heures",      e.native_value, float(i+1))
        check(f"{key}: unité",       e._attr_native_unit_of_measurement, 'h')
        check(f"{key}: device_class", e._attr_device_class, 'duration')
        check(f"{key}: state_class", e._attr_state_class, 'total_increasing')
        check(f"{key}: sans icône",  '_attr_icon' in e.__dict__, False)
        check(f"{key}: actif",       e._attr_entity_registry_enabled_default, True)
        check(f"{key}: unique_id",   e.unique_id, f'id_klereo115{key}')
    print("== chaque compteur lit bien SA clé ==")
    for key, (_, pkey) in COUNTERS.items():
        _, i = build({pkey: 7200})
        check(f"seul {pkey} présent", sorted(k for k in i if k.endswith('time')), [key])
    print("== un bassin sans chauffage ni traitement n'a que ce qu'il a ==")
    _, i = build({'Filtration_TotalTime': 3600})
    check("filtration seule", sorted(k for k in i if k.endswith('time')), ['filtrationtime'])
    _, i = build({})
    check("aucun compteur", [k for k in i if k.endswith('time')], [])
    print("== une clé mal orthographiée ne crée rien et ne casse rien ==")
    _, i = build({'Chauffage_TotalTime': 3600})
    check("clé inconnue ignorée", [k for k in i if k.endswith('time')], [])
    print("== valeurs aberrantes, par compteur ==")
    for key, (_, pkey) in COUNTERS.items():
        for bad in (None, '3600', True, [1]):
            _, i = build({pkey: bad})
            check(f"{key} = {bad!r}", key in i, False)
        _, i = build({pkey: 0})
        check(f"{key} = 0 -> créé", key in i, True)
    print("== les capteurs d'identité restent intacts ==")
    _, i = build(dict(ALL, VolumeEau=45))
    check("liste complète", sorted(i),
          ['device','disinfectanttime','filtrationtime','heatingtime','phtime','pin','volume'])
    check("volume désactivé", i['volume']._attr_entity_registry_enabled_default, False)
    check("volume garde son icône", i['volume']._attr_icon, 'mdi:pool')
    check("pin sans state_class", i['pin']._attr_state_class, None)
    print()

    check.assert_ok()
