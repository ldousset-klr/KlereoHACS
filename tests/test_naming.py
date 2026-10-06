"""Vérifie que chaque entité se nomme d'après sa piscine (has_entity_name)."""


def test_naming(check):
    from klereo.number import KlereoFiltrationSpeed, KlereoWaterSetpoint
    from klereo.select import KlereoOutMode
    from klereo.sensor import KlereoInfoSensor, KlereoSensor
    from klereo.switch import KlereoOut
    # Home Assistant then shows "<pool> <name>" and builds the entity_id from
    # both; an entity class without it would be the one bare sensor.pin left.
    for cls in (KlereoSensor, KlereoInfoSensor, KlereoOut, KlereoOutMode,
                KlereoFiltrationSpeed, KlereoWaterSetpoint):
        check(cls.__name__, getattr(cls, '_attr_has_entity_name', False), True)
    check.assert_ok()
