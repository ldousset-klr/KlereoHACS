"""Vérifie le cycle de vie des tâches de confirmation."""
from klereo_stub import Api, Coordinator, Hass, run


def test_tasklife(check):
    from klereo.switch import KlereoOut
    from klereo.number import KlereoWaterSetpoint
    def pool():
        return {'idSystem':115,'poolNickname':'T','probes':[],'IORename':[],'PumpMaxSpeed':3,
                'params':{'ConsigneEau':28.0},
                'outs':[{'index':0,'type':0,'mode':0,'status':0,'realStatus':0,'updateTime':0}]}
    def build(status=9):
        c = Coordinator(pool()); a = Api(); a.wait_status = status
        h = Hass(); h.keep_tasks = True
        sw = KlereoOut(a, c, c.data['outs'][0], 115, {}, None); sw.hass = h
        return c, a, h, sw
    print("== la tâche est confiée au config entry, pas à hass ==")
    c, a, h, sw = build()
    run(sw.async_turn_on())
    check("une tâche de fond enregistrée par l'entrée", len(c.config_entry.tasks), 1)
    check("l'entité la retient", sw._confirm_task is not None, True)
    check("la même", sw._confirm_task, c.config_entry.tasks[0])
    print("== déchargement de l'entrée : la tâche est annulée ==")
    c.config_entry.unload()
    check("annulée", sw._confirm_task.cancelled, True)
    h.run_tasks()
    check("elle n'a pas tourné : optimiste intact", sw._optimistic_state, True)
    check("aucun CommandStatus", [x for x in a.calls if x[0]=='command_status'], [])
    print("== sans config_entry : repli sur hass, pas de plantage ==")
    c2, a2, h2, sw2 = build()
    del c2.config_entry
    run(sw2.async_turn_on())
    check("tâche créée quand même", sw2._confirm_task is not None, True)
    h2.run_tasks()
    check("et elle a tourné", [x[0] for x in a2.calls][-1], 'command_status')
    print("== deux écritures rapprochées : la première est abandonnée ==")
    c3, a3, h3, sw3 = build()
    run(sw3.async_turn_on())
    first = sw3._confirm_task
    run(sw3.async_turn_off())
    second = sw3._confirm_task
    check("deux tâches distinctes", first is not second, True)
    check("la première annulée", first.cancelled, True)
    check("la seconde vivante", second.cancelled, False)
    check("une seule survivra", sum(1 for t in c3.config_entry.tasks if not t.cancelled), 1)
    h3.run_tasks()
    check("un seul CommandStatus", len([x for x in a3.calls if x[0]=='command_status']), 1)
    check("l'optimiste du second tient", sw3._optimistic_state, False)
    print("== c'était le défaut : la 1re confirmation effaçait la valeur de la 2e ==")
    c4, a4, h4, sw4 = build(status=17)          # 1re commande : pod déconnecté
    run(sw4.async_turn_on())
    a4.wait_status = 9                           # 2e commande : appliquée
    run(sw4.async_turn_off())
    h4.run_tasks()
    check("l'échec de la 1re n'efface pas la 2e", sw4._optimistic_state, False)
    print("== retrait de l'entité : annulée aussi ==")
    c5, a5, h5, sw5 = build()
    run(sw5.async_turn_on())
    t = sw5._confirm_task
    run(sw5.async_will_remove_from_hass())
    check("annulée", t.cancelled, True)
    check("référence lâchée", sw5._confirm_task, None)
    print("== la tâche se déréférence une fois finie ==")
    c6, a6, h6, sw6 = build()
    run(sw6.async_turn_on()); h6.run_tasks()
    check("plus de tâche retenue", sw6._confirm_task, None)
    print("== la consigne suit les mêmes règles ==")
    c7 = Coordinator(pool()); a7 = Api(); h7 = Hass(); h7.keep_tasks = True
    sp = KlereoWaterSetpoint(a7, c7, 115, {}); sp.hass = h7
    run(sp.async_set_native_value(26.0))
    check("tâche liée à l'entrée", len(c7.config_entry.tasks), 1)
    run(sp.async_set_native_value(24.0))
    check("la précédente annulée", c7.config_entry.tasks[0].cancelled, True)
    run(sp.async_will_remove_from_hass())
    check("retrait -> annulée", c7.config_entry.tasks[1].cancelled, True)
    print()

    check.assert_ok()
