"""Vérifie la 1.5.1 : erreurs d'écriture lisibles, sections absentes, lien de l'appareil."""
from requests import ConnectionError as RequestsConnectionError

from klereo_stub import Api, Coordinator, Hass, run


class FailingApi(Api):
    """Un serveur qui refuse toute écriture."""
    error = None
    def set_out(self, outIdx, state, mode):
        self.calls.append(('set_out', outIdx, state, mode))
        raise self.error
    def set_param(self, paramID, value, label=None):
        self.calls.append(('set_param', paramID, value, label))
        raise self.error


def test_robust(check):
    from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
    from klereo.entity import (klereo_configuration_url, klereo_device_info,
                               klereo_item, klereo_items)
    from klereo.klereo_api import KlereoAuthError, KlereoError
    from klereo.number import KlereoFiltrationSpeed, KlereoWaterSetpoint
    from klereo.number import async_setup_entry as number_setup
    from klereo.select import KlereoOutMode, async_setup_entry as select_setup
    from klereo.sensor import KlereoSensor, async_setup_entry as sensor_setup
    from klereo.switch import KlereoOut, async_setup_entry as switch_setup

    print("== lien de l'appareil : le serveur de l'entrée ==")
    for server, want in [
        (None, 'https://connect.klereo.fr'),
        ('', 'https://connect.klereo.fr'),
        ('https://connect.klereo.fr', 'https://connect.klereo.fr'),
        ('https://dev.example', 'https://dev.example'),
        ('https://dev.example/', 'https://dev.example'),
        ('https://dev.example/php', 'https://dev.example'),
        ('https://dev.example/php/', 'https://dev.example'),
        ('  http://10.0.0.5:8080/php  ', 'http://10.0.0.5:8080'),
        ('dev.example', 'https://connect.klereo.fr'),      # sans schéma : refusé par HA
        ('ftp://dev.example', 'https://connect.klereo.fr'),
    ]:
        check(f"  {server!r}", klereo_configuration_url(server), want)
    check("device_info sans serveur : production",
          klereo_device_info({}, 115)['configuration_url'], 'https://connect.klereo.fr')
    check("device_info avec serveur de dev",
          klereo_device_info({}, 115, 'https://dev.example/php')['configuration_url'],
          'https://dev.example')

    print("== klereo_items / klereo_item ==")
    check("section absente", klereo_items({}, 'outs'), [])
    check("section nulle", klereo_items({'outs': None}, 'outs'), [])
    check("sans index ni dict : ignorés",
          klereo_items({'outs': [{'index': 0}, {'mode': 1}, 'x', None]}, 'outs'),
          [{'index': 0}])
    check("par index", klereo_item({'outs': [{'index': 3, 'mode': 2}]}, 'outs', 3),
          {'index': 3, 'mode': 2})
    check("index inconnu", klereo_item({'outs': [{'index': 3}]}, 'outs', 4), None)
    check("section absente : None", klereo_item({}, 'probes', 0), None)

    print("== mise en place : une section absente ne fait rien planter ==")
    def setup(fn, pool):
        c = Coordinator(pool); added = []
        class H(Hass): data = {'klereo': {'e': {'coordinator': c, 'api': Api()}}}
        class E: entry_id = 'e'; data = {'server': 'https://dev.example/php'}
        run(fn(H(), E(), lambda es: added.extend(es)))
        return added
    for label, pool in [("sans probes ni outs", {'idSystem': 115}),
                        ("probes et outs nuls", {'idSystem': 115, 'probes': None,
                                                 'outs': None})]:
        for name, fn in [('sensor', sensor_setup), ('switch', switch_setup),
                         ('number', number_setup), ('select', select_setup)]:
            try:
                added = setup(fn, dict(pool))
                check(f"{label} : {name} sans entité de sonde/sortie",
                      [e for e in added if isinstance(e, (KlereoSensor, KlereoOut,
                                                          KlereoOutMode,
                                                          KlereoFiltrationSpeed))], [])
            except Exception as err:
                check(f"{label} : {name}", repr(err), 'pas d’exception')
    added = setup(switch_setup, {'idSystem': 115, 'outs': [{'index': 0, 'mode': 0,
                                                             'status': 0}]})
    check("le lien de l'appareil suit l'entrée",
          added[0]._attr_device_info['configuration_url'], 'https://dev.example')

    print("== entités : champs absents, pas de KeyError ==")
    c = Coordinator({'idSystem': 115, 'outs': [{'index': 0}, {'index': 1}],
                     'probes': [{'index': 2}], 'PumpMaxSpeed': 3})
    sw = KlereoOut(Api(), c, c.data['outs'][0], 115, {}, None)
    check("switch : sans status, inconnu", sw.is_on, None)
    check("switch : attributs à None", sw.extra_state_attributes,
          {'Time': None, 'Type': None, 'Mode': None, 'ModeName': None,
           'RealStatus': None})
    filt = KlereoOut(Api(), c, c.data['outs'][1], 115, {}, None)
    check("filtration sans status : inconnu, pas « en marche »", filt.is_on, None)
    sp = KlereoFiltrationSpeed(Api(), c, 115, {}, 3, None)
    check("vitesse sans status", sp.native_value, None)
    se = KlereoSensor(c, c.data['probes'][0], 115, {})
    check("sonde sans valeur", se.native_value, None)
    check("sonde : attributs", se.extra_state_attributes['Time'], None)
    c.data['outs'] = None; c.data['probes'] = None
    check("section disparue : switch", (sw.is_on, sw.extra_state_attributes), (None, None))
    check("section disparue : vitesse", sp.native_value, None)
    check("section disparue : sonde", se.native_value, None)

    print("== une écriture refusée par Klereo devient un message, pas une trace ==")
    def pool():
        return {'idSystem': 115, 'PumpMaxSpeed': 3, 'params': {'ConsigneEau': 28.0},
                'outs': [{'index': 0, 'mode': 0, 'status': 0},
                         {'index': 1, 'mode': 0, 'status': 2}]}
    errors = [("KlereoError", KlereoError("SetOut.php failed: error=Désolé")),
              ("KlereoAuthError", KlereoAuthError("SetOut.php refused the JWT")),
              ("réseau", RequestsConnectionError("connection refused"))]
    for label, error in errors:
        c = Coordinator(pool()); a = FailingApi(); a.error = error
        h = Hass(); h.keep_tasks = True
        sw = KlereoOut(a, c, c.data['outs'][0], 115, {}, None); sw.hass = h
        sp = KlereoFiltrationSpeed(a, c, 115, {}, 3, None); sp.hass = h
        st = KlereoWaterSetpoint(a, c, 115, {}); st.hass = h
        mo = KlereoOutMode(a, c, c.data['outs'][0], 115, {}, None); mo.hass = h
        for what, call, optimistic in [
            ("switch on", lambda: sw.async_turn_on(), lambda: sw._optimistic_state),
            ("switch off", lambda: sw.async_turn_off(), lambda: sw._optimistic_state),
            ("vitesse", lambda: sp.async_set_native_value(3), lambda: sp._optimistic_speed),
            ("consigne", lambda: st.async_set_native_value(27.0),
             lambda: st._optimistic_value),
            ("mode", lambda: mo.async_select_option('Minuterie'),
             lambda: mo._optimistic_mode),
        ]:
            try:
                run(call())
                check(f"{label} / {what} : levée", 'rien', 'HomeAssistantError')
                continue
            except ServiceValidationError as err:
                check(f"{label} / {what} : pas une erreur de saisie", err.key, 'command_failed')
                continue
            except HomeAssistantError as err:
                check(f"{label} / {what} : clé", err.key, 'command_failed')
                check(f"{label} / {what} : raison du serveur",
                      str(error) in err.placeholders['error'], True)
                check(f"{label} / {what} : nom", bool(err.placeholders['name']), True)
                check(f"{label} / {what} : cause gardée", err.__cause__ is error, True)
            except Exception as err:
                check(f"{label} / {what} : type", type(err).__name__, 'HomeAssistantError')
                continue
            check(f"{label} / {what} : pas d'état optimiste", optimistic(), None)
            check(f"{label} / {what} : pas de confirmation", h.tasks, [])
    check.assert_ok()
