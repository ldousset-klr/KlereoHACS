"""Vérifie l’options flow, le reconfigure et l’intervalle de rafraîchissement."""
import json
from datetime import timedelta
from pathlib import Path

from klereo_stub import ConfigEntries, ConfigEntryData, Hass, run


COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "klereo"

DATA = {'username': 'u', 'password': 'p', 'poolid': 115,
        'server': 'https://dev.example'}


class FakeAPI:
    """Remplace KlereoAPI : note ce qu’on lui passe, lève ce qu’on lui dit."""
    made = []
    raises = None
    def __init__(self, username, password, poolid=None, server=None):
        FakeAPI.made.append((username, password, poolid, server))
    def get_pool(self):
        if FakeAPI.raises: raise FakeAPI.raises
        return {'idSystem': 115}


def _field(schema, name):
    """The validator a voluptuous schema holds for one key."""
    return next(v for k, v in schema.schema.items() if str(k) == name)


def test_options(check, monkeypatch):
    import klereo
    from klereo import async_entry_updated, async_setup_entry
    from klereo import config_flow
    from klereo.config_flow import KlereoConfigFlow, KlereoOptionsFlow
    from klereo.const import (CONF_SCAN_INTERVAL, DEF_SERVER, SCAN_INTERVAL_MAX,
                              SCAN_INTERVAL_MIN, UPDATE_INTERVAL, scan_interval)
    from klereo.klereo_api import KlereoAuthError, KlereoError

    print("== constantes ==")
    check("clé", CONF_SCAN_INTERVAL, 'scan_interval')
    check("défaut 5 min", UPDATE_INTERVAL, 300)
    check("le plancher est le défaut", SCAN_INTERVAL_MIN, UPDATE_INTERVAL)
    check("bornes", (SCAN_INTERVAL_MIN, SCAN_INTERVAL_MAX), (300, 3600))

    print("== scan_interval() ==")
    for label, options, want in [
        ("options absentes", None, 300),
        ("options vides : entrée d'avant l'options flow", {}, 300),
        ("valeur réglée", {'scan_interval': 900}, 900),
        ("borne basse", {'scan_interval': 300}, 300),
        ("borne haute", {'scan_interval': 3600}, 3600),
        ("sous la borne : ramenée", {'scan_interval': 60}, 300),
        ("juste sous la borne : ramenée", {'scan_interval': 299}, 300),
        ("au-dessus : ramenée", {'scan_interval': 86400}, 3600),
        ("flottant arrondi", {'scan_interval': 900.6}, 901),
        ("chaîne : défaut", {'scan_interval': '900'}, 300),
        ("booléen : défaut", {'scan_interval': True}, 300),
        ("NaN : défaut", {'scan_interval': float('nan')}, 300),
        ("infini : défaut", {'scan_interval': float('inf')}, 300),
        ("None : défaut", {'scan_interval': None}, 300),
    ]:
        check(f"  {label}", scan_interval(options), want)
    check("  toujours un int", type(scan_interval({'scan_interval': 900.6})), int)

    print("== le config flow expose l'options flow ==")
    check("classe", type(KlereoConfigFlow.async_get_options_flow(None)), KlereoOptionsFlow)

    def options_flow(options):
        flow = KlereoOptionsFlow()
        flow.hass = Hass()
        flow.hass.config_entries = ConfigEntries([ConfigEntryData(DATA, options)])
        flow.handler = 'e'
        return flow

    print("== formulaire d'options ==")
    form = run(options_flow({}).async_step_init())
    check("formulaire", (form['type'], form['step_id']), ('form', 'init'))
    check("défaut sans option : 300", form['data_schema']({}), {'scan_interval': 300})
    sel = _field(form['data_schema'], 'scan_interval')
    check("bornes du sélecteur", (sel.config['min'], sel.config['max'], sel.config['step']),
          (SCAN_INTERVAL_MIN, SCAN_INTERVAL_MAX, 1))
    check("unité", sel.config['unit_of_measurement'], 's')
    check("saisie en boîte, pas en curseur", sel.config['mode'].value, 'box')
    form = run(options_flow({'scan_interval': 900}).async_step_init())
    check("défaut = valeur en cours", form['data_schema']({}), {'scan_interval': 900})
    form = run(options_flow({'scan_interval': 5}).async_step_init())
    check("défaut d'une valeur hors bornes : ramenée", form['data_schema']({}),
          {'scan_interval': 300})

    print("== enregistrement ==")
    done = run(options_flow({}).async_step_init({'scan_interval': 600.0}))
    check("entrée créée", done['type'], 'create_entry')
    check("secondes entières", done['data'], {'scan_interval': 600})
    check("un int, pas un float", type(done['data']['scan_interval']), int)
    done = run(options_flow({'autre': 1}).async_step_init({'scan_interval': 1200}))
    check("les autres options sont gardées", done['data'], {'autre': 1, 'scan_interval': 1200})

    print("== reconfigure ==")
    monkeypatch.setattr(config_flow, 'KlereoAPI', FakeAPI)

    def reconf(data=DATA):
        entry = ConfigEntryData(data, unique_id='115')
        hass = Hass(); hass.config_entries = ConfigEntries([entry])
        flow = KlereoConfigFlow(); flow.hass = hass
        flow.context = {'source': 'reconfigure', 'entry_id': 'e'}
        return flow, entry, hass

    flow, entry, hass = reconf()
    form = run(flow.async_step_reconfigure())
    check("formulaire", (form['type'], form['step_id']), ('form', 'reconfigure'))
    filled = form['data_schema']({'password': 'x'})
    check("identifiant et serveur pré-remplis", filled,
          {'username': 'u', 'password': 'x', 'server': 'https://dev.example'})
    try:
        form['data_schema']({})
        check("mot de passe exigé", 'accepté', 'refusé')
    except Exception as err:
        check("mot de passe exigé", 'password' in str(err), True)
    flow, entry, hass = reconf({k: v for k, v in DATA.items() if k != 'server'})
    form = run(flow.async_step_reconfigure())
    check("entrée sans serveur : défaut proposé",
          form['data_schema']({'password': 'x'})['server'], DEF_SERVER)

    FakeAPI.made.clear(); FakeAPI.raises = None
    flow, entry, hass = reconf()
    done = run(flow.async_step_reconfigure(
        {'username': 'u2', 'password': 'p2', 'server': 'https://other.example'}))
    check("abandon réussi", (done['type'], done['reason']),
          ('abort', 'reconfigure_successful'))
    check("validé contre le nouveau serveur, même piscine", FakeAPI.made,
          [('u2', 'p2', 115, 'https://other.example')])
    check("données mises à jour, poolID inchangé", entry.data,
          {'username': 'u2', 'password': 'p2', 'poolid': 115,
           'server': 'https://other.example'})
    check("une mise à jour puis un rechargement",
          [c[0] for c in hass.config_entries.calls], ['update', 'reload'])
    check("unique_id intact", entry.unique_id, '115')

    flow, entry, hass = reconf()
    run(flow.async_step_reconfigure({'username': 'u', 'password': 'p', 'server': ''}))
    check("serveur vidé : production", entry.data['server'], DEF_SERVER)

    for label, err, key in [("identifiants refusés", KlereoAuthError('no'), 'invalid_auth'),
                            ("serveur injoignable", KlereoError('down'), 'cannot_connect')]:
        FakeAPI.raises = err
        flow, entry, hass = reconf()
        form = run(flow.async_step_reconfigure(
            {'username': 'u', 'password': 'bad', 'server': 'https://x'}))
        check(f"{label} : formulaire", (form['type'], form['errors']), ('form', {'base': key}))
        check(f"{label} : entrée intacte", entry.data, DATA)
        check(f"{label} : rien rechargé", hass.config_entries.calls, [])
    FakeAPI.raises = None

    print("== l'écouteur ne recharge que sur un changement d'intervalle ==")
    class Running:
        update_interval = timedelta(seconds=300)
    def listen(options, runtime=True):
        entry = ConfigEntryData(DATA, options)
        hass = Hass(); hass.config_entries = ConfigEntries([entry])
        hass.data = {'klereo': {'e': {'coordinator': Running()}}} if runtime else {}
        run(async_entry_updated(hass, entry))
        return hass.config_entries.calls
    check("options inchangées (reauth, reconfigure) : rien", listen({}), [])
    check("même valeur explicite : rien", listen({'scan_interval': 300}), [])
    check("nouvel intervalle : rechargement", listen({'scan_interval': 600}),
          [('reload', 'e')])
    check("entrée déjà déchargée : rien, sans erreur", listen({'scan_interval': 600}, False), [])

    print("== la mise en place lit l'intervalle et branche l'écouteur ==")
    class Coordinator:
        made = []
        def __init__(self, hass, logger, *, config_entry, name, update_method,
                     update_interval):
            self.update_interval = update_interval
            Coordinator.made.append(self)
        async def async_config_entry_first_refresh(self): pass
    monkeypatch.setattr(klereo, 'DataUpdateCoordinator', Coordinator)
    monkeypatch.setattr(klereo, 'KlereoAPI', FakeAPI)
    for label, options, want in [("sans option", {}, 300),
                                 ("réglée", {'scan_interval': 1200}, 1200)]:
        entry = ConfigEntryData(DATA, options, unique_id='115')
        hass = Hass(); hass.config_entries = ConfigEntries([entry]); hass.data = {}
        Coordinator.made.clear()
        check(f"{label} : mise en place", run(async_setup_entry(hass, entry)), True)
        check(f"{label} : intervalle", Coordinator.made[0].update_interval,
              timedelta(seconds=want))
        check(f"{label} : écouteur branché", entry.listeners, [async_entry_updated])
        check(f"{label} : et retiré au déchargement", len(entry.on_unload), 1)
        entry.on_unload[0]()
        check(f"{label} : retiré", entry.listeners, [])

    print("== textes : chaque étape et chaque abandon est traduit ==")
    strings = json.loads((COMPONENT / 'strings.json').read_text())
    en = json.loads((COMPONENT / 'translations' / 'en.json').read_text())
    fr = json.loads((COMPONENT / 'translations' / 'fr.json').read_text())
    check("en.json = strings.json", en, strings)
    for name, t in (('strings', strings), ('fr', fr)):
        step = t['config']['step'].get('reconfigure', {})
        check(f"{name} : reconfigure", sorted(step.get('data', {})),
              ['password', 'server', 'username'])
        check(f"{name} : abandon reconfigure",
              'reconfigure_successful' in t['config']['abort'], True)
        check(f"{name} : options", sorted(t.get('options', {}).get('step', {})
                                          .get('init', {}).get('data', {})),
              ['scan_interval'])

    def shape(node):
        return {k: shape(v) for k, v in node.items()} if isinstance(node, dict) else None
    check("fr a exactement les clés de strings", shape(fr), shape(strings))
    check.assert_ok()
