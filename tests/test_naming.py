"""Vérifie que chaque entité se nomme d'après sa piscine (has_entity_name),
et que les noms traduits existent dans chaque fichier de traduction."""
import json
import re
from pathlib import Path

COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "klereo"


def test_naming(check):
    from klereo.number import KlereoFiltrationSpeed, KlereoWaterSetpoint
    from klereo.select import KlereoOutMode
    from klereo.sensor import INFO_SENSORS, KlereoInfoSensor, KlereoSensor
    from klereo.switch import KlereoOut
    # Home Assistant then shows "<pool> <name>" and builds the entity_id from
    # both; an entity class without it would be the one bare sensor.pin left.
    for cls in (KlereoSensor, KlereoInfoSensor, KlereoOut, KlereoOutMode,
                KlereoFiltrationSpeed, KlereoWaterSetpoint):
        check(cls.__name__, getattr(cls, '_attr_has_entity_name', False), True)

    print("== noms traduits : une clé, et pas de name qui la masquerait ==")
    wanted = {('sensor', info.key): set() for info in INFO_SENSORS}
    for platform, cls, placeholders in (('number', KlereoWaterSetpoint, set()),
                                        ('number', KlereoFiltrationSpeed, {'out'}),
                                        ('select', KlereoOutMode, {'out'})):
        wanted[(platform, cls._attr_translation_key)] = placeholders
        check(f"{cls.__name__} : pas de propriété name", 'name' in vars(cls), False)
    check("KlereoInfoSensor : pas de propriété name", 'name' in vars(KlereoInfoSensor), False)
    for path in ('strings.json', 'translations/en.json', 'translations/fr.json'):
        entity = json.loads((COMPONENT / path).read_text()).get('entity', {})
        for (platform, key), placeholders in wanted.items():
            name = entity.get(platform, {}).get(key, {}).get('name')
            check(f"{path} : {platform}.{key}", bool(name), True)
            check(f"{path} : {platform}.{key} placeholders",
                  set(re.findall(r'\{(\w+)\}', name or '')), placeholders)
    check.assert_ok()
