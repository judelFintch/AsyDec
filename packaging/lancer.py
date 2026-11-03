"""Entrée PyInstaller et diagnostic rapide sans ouvrir l’interface."""
import json
import sys
from pathlib import Path

if len(sys.argv) == 5 and sys.argv[1] == '--installer':
    from asydec.systeme.mises_a_jour import installer
    installer(sys.argv[2],sys.argv[3],int(sys.argv[4]))
    sys.exit(0)

if '--diagnostic' in sys.argv:
    from asydec import chemins
    from asydec.systeme.version import courante
    import tkinter
    import openpyxl
    print(json.dumps({'version': courante(), 'donnees': str(chemins.RACINE), 'tk': tkinter.TkVersion}))
    sys.exit(0)

if '--test-interface' in sys.argv:
    from asydec.ui.app import AsyDec
    from asydec.systeme import espace_travail
    from asydec import chemins
    espace_travail.definir(chemins.RACINE.parent/'asydec-test-documents')
    app = AsyDec('diagnostic')
    app.after(800, app.quitter)
    app.mainloop()
    print('Interface initialisée et fermée correctement')
else:
    from asydec.ui.app import main
    main()
