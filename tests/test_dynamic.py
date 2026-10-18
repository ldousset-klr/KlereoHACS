"""Vérifie qu'un poll qui apporte une sonde, une sortie ou un réglage crée l'entité."""
import copy
import logging

from klereo_stub import Coordinator, run, entry_for


def test_dynamic(check, caplog):
    from klereo.number import async_setup_entry as number_setup
    from klereo.select import async_setup_entry as select_setup
    from klereo.sensor import async_setup_entry as sensor_setup
    from klereo.switch import async_setup_entry as switch_setup
    from klereo.const import HEATER_NONE, HEATER_NORMAL

    base = {'idSystem': 115, 'poolNickname': 'T', 'IORename': [],
            'probes': [{'index': 16, 'type': 5, 'filteredValue': 26.0}],
            'outs': [{'index': 0, 'mode': 0, 'status': 0}],
            'params': {'HeaterMode': HEATER_NONE}}

    def setup(fn, data):
        c = Coordinator(copy.deepcopy(data))
        entry = entry_for(c)
        batches = []
        run(fn(None, entry, batches.append))
        return c, entry, batches

    def keys(batch):
        return sorted(e._key for e in batch)

    print("== une sonde apparue après l'installation ==")
    c, entry, added = setup(sensor_setup, base)
    check("au démarrage", keys(added[0]), ['klereo115probe16'])
    check("écoute le coordinateur", len(c.listeners), 1)
    check("  et cesse au déchargement", len(entry.on_unload), 1)
    entry.on_unload[0]()
    check("  écouteur retiré", c.listeners, [])
    c, entry, added = setup(sensor_setup, base)
    c.poll(copy.deepcopy(base))
    check("même payload : rien d'ajouté", len(added), 1)
    more = copy.deepcopy(base)
    more['probes'].append({'index': 17, 'type': 3, 'filteredValue': 7.2})
    c.poll(more)
    check("la nouvelle seule", keys(added[1]), ['klereo115probe17'])
    c.poll(copy.deepcopy(more))
    check("  une seule fois", len(added), 2)
    gone = copy.deepcopy(base); gone['probes'] = []
    c.poll(gone)
    c.poll(more)
    check("partie puis revenue : pas recréée", len(added), 2)

    print("== une valeur d'identité qui arrive ==")
    more = copy.deepcopy(base); more['register'] = {'pin': 1234}
    c.poll(more)
    check("le PIN", keys(added[2]), ['klereo115pin'])

    print("== une sortie : interrupteur, et sélecteur si ses modes sont connus ==")
    c, _, sw = setup(switch_setup, base)
    c2, _, sel = setup(select_setup, base)
    more = copy.deepcopy(base)
    more['outs'].append({'index': 5, 'mode': 0, 'status': 0})
    c.poll(more); c2.poll(copy.deepcopy(more))
    check("interrupteur", keys(sw[1]), ['klereo115out5'])
    check("sélecteur", keys(sel[1]), ['klereo115out5mode'])

    print("== le chauffage : son sélecteur attend que HeaterMode dise ce qu'il est ==")
    heat = copy.deepcopy(base)
    heat['outs'].append({'index': 4, 'mode': 0, 'status': 0})
    c, _, sel = setup(select_setup, heat)
    check("HEATER_NONE : pas de sélecteur", keys(sel[0]), ['klereo115out0mode'])
    heat['params']['HeaterMode'] = HEATER_NORMAL
    c.poll(copy.deepcopy(heat))
    check("HeaterMode renseigné : il arrive", keys(sel[1]), ['klereo115out4mode'])

    print("== consigne et vitesse ==")
    c, _, num = setup(number_setup, base)
    check("rien au départ", num, [])
    more = copy.deepcopy(base)
    more['params']['ConsigneEau'] = 27.0
    more['outs'].append({'index': 1, 'mode': 0, 'status': 0})
    more['PumpMaxSpeed'] = 3
    c.poll(more)
    check("les deux", keys(num[0]), ['klereo115out1speed', 'klereo115watersetpoint'])
    c.poll(copy.deepcopy(more))
    check("  une seule fois", len(num), 1)

    print("== ce qui manque se dit au démarrage, pas à chaque poll ==")
    caplog.set_level(logging.DEBUG, logger='custom_components.klereo')
    caplog.set_level(logging.DEBUG, logger='klereo')
    caplog.clear()
    c, _, num = setup(number_setup, base)
    first = len([r for r in caplog.records if 'no ' in r.getMessage()])
    check("au démarrage, le dit", first >= 2, True)
    caplog.clear()
    c.poll(copy.deepcopy(base))
    check("au poll suivant, se tait",
          [r.getMessage() for r in caplog.records if 'no ' in r.getMessage()], [])

    print("== PumpMaxSpeed illisible : averti une fois, à la création ==")
    odd = copy.deepcopy(base)
    odd['outs'].append({'index': 1, 'mode': 0, 'status': 0})
    caplog.clear()
    c, _, num = setup(number_setup, odd)
    c.poll(copy.deepcopy(odd)); c.poll(copy.deepcopy(odd))
    warned = [r for r in caplog.records if r.levelno == logging.WARNING
              and 'PumpMaxSpeed' in r.getMessage()]
    check("un seul avertissement", len(warned), 1)
    print()

    check.assert_ok()
