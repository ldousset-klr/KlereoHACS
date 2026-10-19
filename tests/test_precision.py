"""Vérifie l'arrondi des capteurs selon leur unité."""
from klereo_stub import Coordinator


def test_precision(check):
    from klereo.sensor import KlereoSensor

    def sensor(ptype, value):
        c = Coordinator({'idSystem': 115, 'probes': [
            {'index': 16, 'type': ptype, 'filteredValue': value}]})
        return KlereoSensor(c, c.data['probes'][0], 115, {})

    print("== précision d'affichage ==")
    for ptype, unit, digits in ((0, '°C', 1), (1, '°C', 1), (5, '°C', 1),
                                (3, 'pH', 1), (4, 'mV', 0), (6, 'mbar', 0)):
        check(f"  type {ptype} ({unit})",
              getattr(sensor(ptype, 1.0), '_attr_suggested_display_precision', None), digits)
    check("  type 10 (générique) : telle quelle",
          getattr(sensor(10, 1.0), '_attr_suggested_display_precision', None), None)

    print("== les mbar à la dizaine, dans l'état ==")
    check("  1234", sensor(6, 1234).native_value, 1230)
    check("  1237", sensor(6, 1237.4).native_value, 1240)
    print("== les autres gardent la mesure, seul l'affichage arrondit ==")
    check("  26.37 °C", sensor(5, 26.37).native_value, 26.37)
    check("  712.6 mV", sensor(4, 712.6).native_value, 712.6)
    check("  -1000 reste inconnu", sensor(6, -1000).native_value, None)
    print()

    check.assert_ok()
