"""Vérifie les infos de l’appareil."""
from klereo_stub import run


def test_device(check):
    from klereo.entity import klereo_device_info
    print("== la version matérielle apparaît ==")
    d = klereo_device_info({'poolNickname':'Bassin','tabSW':'212D','tabHW':'3B',
                            'podSerial':'KLR0001'}, 115)
    check("hw_version", d.get('hw_version'), '3B')
    check("sw_version", d.get('sw_version'), '212D')
    check("serial_number", d.get('serial_number'), 'KLR0001')
    check("nom", d.get('name'), 'Bassin')
    check("identifiants toujours sur le poolID", d.get('identifiers'), {('klereo','115')})
    print("== un champ absent reste absent, pas la chaîne 'None' ==")
    d = klereo_device_info({'poolNickname':'B'}, 115)
    for f in ('hw_version','sw_version','serial_number'):
        check(f"{f} absent", f in d, False)
    d = klereo_device_info({'tabHW':'3B'}, 115)
    check("hw seul", (d.get('hw_version'), 'sw_version' in d), ('3B', False))
    check("nom de repli", d.get('name'), 'Klereo pool #115')
    print("== valeurs fausses : vide, None, 0 ==")
    for bad in ('', None, 0):
        d = klereo_device_info({'tabHW':bad}, 115)
        check(f"tabHW={bad!r} ignoré", 'hw_version' in d, False)
    d = klereo_device_info({'tabHW':3}, 115)
    check("entier converti en texte", d.get('hw_version'), '3')
    print()

    check.assert_ok()
