"""Vérifie le volume d’eau."""
from klereo_stub import Api, Coordinator, Hass, run


def test_volume(check):
    from klereo.sensor import INFO_SENSORS, KlereoInfoSensor, async_setup_entry as sensor_setup
    def pool(**over):
        d = {'idSystem':115,'poolNickname':'T','outs':[],'probes':[],'IORename':[],
             'params':{'VolumeEau':45},'register':{'pin':'1234'},'device':0}
        d.update(over); return d
    def build(p):
        c = Coordinator(p); added=[]
        class H(Hass): data={'klereo':{'e':{'coordinator':c,'api':Api()}}}
        class E: entry_id='e'; data={}
        run(sensor_setup(H(), E(), lambda es: added.extend(es)))
        return c, {e._key.replace('klereo115',''): e for e in added if isinstance(e, KlereoInfoSensor)}
    print("== le capteur est créé et rapporte la valeur ==")
    c, info = build(pool())
    check("capteurs diagnostiques", sorted(info), ['device','pin','volume'])
    v = info['volume']
    check("valeur", v.native_value, 45)
    check("nom", v._name, 'Water volume')
    check("unité", v._attr_native_unit_of_measurement, 'm³')
    check("icône", v._attr_icon, 'mdi:pool')
    check("unique_id", v.unique_id, 'id_klereo115volume')
    check("catégorie diagnostic", str(v._attr_entity_category), 'EntityCategory.DIAGNOSTIC')
    check("pas de device_class", getattr(v, '_attr_device_class', None), None)
    print("== désactivé par défaut ==")
    check("volume désactivé", v._attr_entity_registry_enabled_default, False)
    check("pin actif",    info['pin']._attr_entity_registry_enabled_default, True)
    check("device actif", info['device']._attr_entity_registry_enabled_default, True)
    check("l'entité existe quand même", v.native_value, 45)
    print("== lecture seule : aucune écriture possible ==")
    check("pas de async_set_native_value", hasattr(v, 'async_set_native_value'), False)
    check("pas de async_turn_on", hasattr(v, 'async_turn_on'), False)
    print("== il suit le payload ==")
    c.data['params']['VolumeEau'] = 72
    check("nouvelle valeur", v.native_value, 72)
    c.data['params']['VolumeEau'] = 0
    check("0 est une vraie valeur", v.native_value, 0)
    print("== absent du payload : pas d'entité, pas de 'None' affiché ==")
    for label, p in (("params sans VolumeEau", pool(params={})),
                     ("params absent", pool(params=None))):
        _, i = build(p)
        check(label, 'volume' in i, False)
    _, i = build(pool(params={'VolumeEau': 0}))
    check("VolumeEau=0 -> entité créée quand même", 'volume' in i, True)
    print("== les deux capteurs existants sont intacts ==")
    _, i = build(pool())
    check("pin", (i['pin'].native_value, i['pin']._attr_icon,
                  i['pin']._attr_native_unit_of_measurement), ('1234','mdi:identifier',None))
    check("device", (i['device'].native_value, i['device']._attr_icon,
                     i['device']._attr_native_unit_of_measurement), (0,'mdi:identifier',None))
    _, i = build(pool(register={}, device=None))
    check("pin/device absents -> seul volume", sorted(i), ['volume'])
    print()

    check.assert_ok()
