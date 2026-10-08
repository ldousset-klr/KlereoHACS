"""Vérifie la consigne d’eau."""
from klereo_stub import Api, Coordinator, Hass, ServiceValidationError, run


def test_setpoint(check):
    from klereo.number import (KlereoWaterSetpoint, KlereoFiltrationSpeed,
                               async_setup_entry as number_setup)
    from klereo.const import SETPOINT_MIN, SETPOINT_MAX, SETPOINT_STEP
    def pool(params=None, outs=None, max_speed=3):
        return {'idSystem':115,'poolNickname':'T','probes':[],'IORename':[],
                'PumpMaxSpeed':max_speed,
                'params':{'ConsigneEau':28.0} if params is None else params,
                'outs':[{'index':1,'type':0,'mode':0,'status':2,'realStatus':2,
                         'updateTime':0}] if outs is None else outs}
    def build(p):
        c = Coordinator(p); added=[]
        class H(Hass): data={'klereo':{'e':{'coordinator':c,'api':Api()}}}
        class E: entry_id='e'; data={}
        run(number_setup(H(), E(), lambda es: added.extend(es)))
        return c, added
    print("== l'entité existe et affiche la consigne ==")
    c, ents = build(pool())
    sp = [e for e in ents if isinstance(e, KlereoWaterSetpoint)]
    check("une consigne créée", len(sp), 1)
    sp = sp[0]
    check("valeur", sp.native_value, 28.0)
    check("nom", sp._name, 'Water setpoint')
    check("unique_id", sp.unique_id, 'id_klereo115watersetpoint')
    check("device_class", sp._attr_device_class, 'temperature')
    check("unité", sp._attr_native_unit_of_measurement, '°C')
    check("bornes", (sp._attr_native_min_value, sp._attr_native_max_value,
                     sp._attr_native_step), (SETPOINT_MIN, SETPOINT_MAX, SETPOINT_STEP))
    check("pas d'icône (device_class prime)", '_attr_icon' in sp.__dict__, False)
    check("pas diagnostic : c'est une commande",
          getattr(sp, '_attr_entity_category', None), None)
    check("activée", getattr(sp, '_attr_entity_registry_enabled_default', True), True)
    print("== elle suit le payload ==")
    for v in (12, 31.5, 0):
        c.data['params']['ConsigneEau'] = v
        check(f"  {v}", sp.native_value, v)
    print("== la valeur affichée n'est pas bornée par le curseur ==")
    c.data['params']['ConsigneEau'] = 215        # si jamais c'était des dixièmes
    check("215 affiché tel quel", sp.native_value, 215)
    print("== l'écriture est désormais branchée ==")
    sp.hass = Hass()                      # l'entité vient de async_setup_entry
    c.data['params']['ConsigneEau'] = 28.0
    run(sp.async_set_native_value(26.0))
    check("part vers SetParam", sp._api.calls[-1], ('set_param', 'ConsigneEau', 26.0, None))
    check("valeur optimiste", sp.native_value, 26.0)
    print("== pas de ConsigneEau : pas d'entité ==")
    for label, params in (("clé absente", {}), ("None", {'ConsigneEau':None}),
                          ("texte", {'ConsigneEau':'28'}), ("booléen", {'ConsigneEau':True}),
                          ("params absent", None)):
        _, e = build(pool(params=params if params is not None else {}))
        check(label, any(isinstance(x, KlereoWaterSetpoint) for x in e), False)
    _, e = build(pool(params={'ConsigneEau':0}))
    check("0 est une vraie consigne", any(isinstance(x, KlereoWaterSetpoint) for x in e), True)
    print("== la vitesse de filtration n'est pas perdue dans le remaniement ==")
    _, e = build(pool())
    check("les deux entités", sorted(type(x).__name__ for x in e),
          ['KlereoFiltrationSpeed','KlereoWaterSetpoint'])
    _, e = build(pool(outs=[]))            # pas de sortie filtration
    check("sans out 1 : consigne seule", [type(x).__name__ for x in e], ['KlereoWaterSetpoint'])
    _, e = build(pool(max_speed=1))        # pompe mono-vitesse
    check("mono-vitesse : consigne seule", [type(x).__name__ for x in e], ['KlereoWaterSetpoint'])
    _, e = build(pool(params={}, outs=[]))
    check("ni l'une ni l'autre", e, [])
    _, e = build(pool(params={}))
    check("vitesse seule", [type(x).__name__ for x in e], ['KlereoFiltrationSpeed'])
    print()

    check.assert_ok()
