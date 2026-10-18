"""Vérifie la disponibilité des entités et les modes recalculés à chaque poll."""
import copy

import pytest

from klereo_stub import Api, Coordinator, Hass, run


def test_available(check):
    from klereo.const import HEATER_NONE, HEATER_NORMAL, HEATER_PAC_KLINK
    from klereo.number import KlereoFiltrationSpeed, KlereoWaterSetpoint
    from klereo.select import KlereoOutMode
    from klereo.sensor import INFO_SENSORS, KlereoInfoSensor, KlereoSensor
    from klereo.switch import KlereoOut

    base = {'idSystem': 115, 'poolNickname': 'T', 'IORename': [], 'PumpMaxSpeed': 3,
            'register': {'pin': 1234},
            'probes': [{'index': 16, 'type': 5, 'filteredValue': 26.0}],
            'outs': [{'index': 0, 'mode': 0, 'status': 0},
                     {'index': 1, 'mode': 0, 'status': 2},
                     {'index': 4, 'mode': 0, 'status': 0}],
            'params': {'HeaterMode': HEATER_NORMAL, 'ConsigneEau': 27.0}}
    pin = next(i for i in INFO_SENSORS if i.key == 'pin')

    def entities(c):
        return {
            'sonde': KlereoSensor(c, c.data['probes'][0], 115, {}),
            'pin': KlereoInfoSensor(c, 115, {}, pin),
            'sortie': KlereoOut(Api(), c, c.data['outs'][0], 115, {}),
            'mode': KlereoOutMode(Api(), c, c.data['outs'][2], 115, {}),
            'vitesse': KlereoFiltrationSpeed(Api(), c, 115, {}, 3, None),
            'consigne': KlereoWaterSetpoint(Api(), c, 115, {}),
        }

    print("== tout est là : tout est disponible ==")
    c = Coordinator(copy.deepcopy(base))
    ents = entities(c)
    for name, e in ents.items():
        check(f"  {name}", e.available, True)

    print("== l'équipement disparaît : indisponible, pas inconnu ==")
    gone = copy.deepcopy(base)
    gone['probes'] = []; gone['outs'] = []; gone['params'] = {}; del gone['register']
    c.data = gone
    for name, e in ents.items():
        check(f"  {name}", e.available, False)
    print("== il revient : disponible à nouveau ==")
    c.data = copy.deepcopy(base)
    for e in ents.values(): e._handle_coordinator_update()
    for name, e in ents.items():
        check(f"  {name}", e.available, True)

    print("== un poll en échec : indisponible, comme le veut Home Assistant ==")
    c.last_update_success = False
    check("  sonde", ents['sonde'].available, False)
    c.last_update_success = True

    print("== la vitesse : indisponible quand la pompe n'a plus de vitesses ==")
    one = copy.deepcopy(base); one['PumpMaxSpeed'] = 1
    c.data = one
    check("  PumpMaxSpeed 1", ents['vitesse'].available, False)
    print("== et sa plage suit PumpMaxSpeed ==")
    five = copy.deepcopy(base); five['PumpMaxSpeed'] = 5
    c.data = five; ents['vitesse']._handle_coordinator_update()
    check("  max 5", ents['vitesse']._attr_native_max_value, 5)

    print("== le sélecteur de mode suit HeaterMode sans rechargement ==")
    c = Coordinator(copy.deepcopy(base))
    sel = KlereoOutMode(Api(), c, c.data['outs'][2], 115, {})
    check("réchauffeur", sel._attr_options, ['Manuel', 'Régulé'])
    pac = copy.deepcopy(base); pac['params']['HeaterMode'] = HEATER_PAC_KLINK
    c.data = pac; sel._handle_coordinator_update()
    check("PAC", sel._attr_options, ['Manuel', 'Auto', 'Refroidit', 'Réchauffe'])
    none = copy.deepcopy(base); none['params']['HeaterMode'] = HEATER_NONE
    c.data = none; sel._handle_coordinator_update()
    check("plus de chauffage établi : aucun mode", sel._attr_options, [])
    check("  et indisponible", sel.available, False)
    sel.hass = Hass()
    with pytest.raises(Exception) as err:
        run(sel.async_select_option('Manuel'))
    check("  une option périmée est refusée", getattr(err.value, 'key', None), 'out_read_only')
    check("  rien n'est envoyé", sel._api.calls, [])
    print()

    check.assert_ok()
