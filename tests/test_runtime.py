"""Vérifie le compteur de filtration."""
from klereo_stub import Api, Coordinator, Hass, run


def test_runtime(check):
    from klereo.sensor import (INFO_SENSORS, KlereoInfoSensor,
                               async_setup_entry as sensor_setup)
    def pool(params=None, **over):
        d = {'idSystem':115,'poolNickname':'T','outs':[],'probes':[],'IORename':[],
             'params':{'VolumeEau':45,'Filtration_TotalTime':3283200} if params is None else params,
             'register':{'pin':'1234'},'device':0}
        d.update(over); return d
    def build(p):
        c = Coordinator(p); added=[]
        class H(Hass): data={'klereo':{'e':{'coordinator':c,'api':Api()}}}
        class E: entry_id='e'; data={}
        run(sensor_setup(H(), E(), lambda es: added.extend(es)))
        return c, {e._key.replace('klereo115',''): e for e in added if isinstance(e, KlereoInfoSensor)}
    print("== secondes converties en heures ==")
    c, info = build(pool())
    r = info['filtrationtime']
    check("3283200 s", r.native_value, 912.0)
    check("unité", r._attr_native_unit_of_measurement, 'h')
    check("nom", r._name, 'Filtration runtime')
    check("unique_id", r.unique_id, 'id_klereo115filtrationtime')
    for sec, want in ((0, 0.0), (3600, 1.0), (1800, 0.5), (5400, 1.5), (100, 0.0),
                      (359, 0.1), (86400, 24.0), (36000000, 10000.0)):
        c.data['params']['Filtration_TotalTime'] = sec
        check(f"  {sec} s", r.native_value, want)
    print("== classes et icône ==")
    check("device_class", r._attr_device_class, 'duration')
    check("state_class", r._attr_state_class, 'total_increasing')
    # L'instance ne doit pas poser _attr_icon du tout : HA retombe alors sur
    # l'icône du device_class. Le contrôle porte donc sur __dict__, pas getattr —
    # la classe de base en définit un à None.
    check("_attr_icon non posé sur l'instance", '_attr_icon' in r.__dict__, False)
    check("volume le pose, lui", '_attr_icon' in info['volume'].__dict__, True)
    check("actif par défaut", r._attr_entity_registry_enabled_default, True)
    check("diagnostic", str(r._attr_entity_category), 'EntityCategory.DIAGNOSTIC')
    print("== valeurs aberrantes : pas d'entité plutôt qu'un plantage ==")
    for label, params in (
            ("compteur absent",   {'VolumeEau':45}),
            ("valeur None",       {'Filtration_TotalTime':None}),
            ("valeur texte",      {'Filtration_TotalTime':'3600'}),
            ("valeur booléenne",  {'Filtration_TotalTime':True}),
            ("params absent",     None)):
        _, i = build(pool(params=params if params is not None else {}))
        check(label, 'filtrationtime' in i, False)
    _, i = build(pool(params={'Filtration_TotalTime':0}))
    check("0 s -> entité créée", 'filtrationtime' in i, True)
    _, i = build(pool(params={'Filtration_TotalTime':1234.5}))
    check("flottant accepté", i['filtrationtime'].native_value, 0.3)
    print("== les capteurs existants ne bougent pas ==")
    _, i = build(pool())
    check("volume: pas de device_class", i['volume']._attr_device_class, None)
    check("volume: garde son icône", i['volume']._attr_icon, 'mdi:pool')
    check("volume: toujours désactivé", i['volume']._attr_entity_registry_enabled_default, False)
    check("pin: icône", i['pin']._attr_icon, 'mdi:identifier')
    check("pin: pas de state_class", i['pin']._attr_state_class, None)
    check("liste complète", sorted(i), ['device','filtrationtime','pin','volume'])
    print()

    check.assert_ok()
