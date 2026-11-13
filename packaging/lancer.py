"""Entrée PyInstaller et diagnostic rapide sans ouvrir l’interface."""
import json
import sys
from pathlib import Path

def main():
    if len(sys.argv) == 5 and sys.argv[1] == '--installer':
        from asydec.systeme.mises_a_jour import installer
        installer(sys.argv[2],sys.argv[3],int(sys.argv[4]))
        sys.exit(0)

    if '--diagnostic' in sys.argv:
        from asydec import chemins
        from asydec.systeme.version import courante
        from asydec.systeme.sauvegarde_chiffree import verifier_moteur
        import tkinter
        import openpyxl
        if not verifier_moteur():
            raise RuntimeError('Le diagnostic du chiffrement a échoué.')
        print(json.dumps({'version': courante(), 'donnees': str(chemins.RACINE), 'tk': tkinter.TkVersion, 'chiffrement': True}))
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


if __name__ == '__main__':
    if '--diagnostic' in sys.argv or '--test-interface' in sys.argv:
        import os
        import traceback
        dossier = Path(os.environ.get('ASYDEC_HOME', str(Path.home() / '.asydec-diagnostic')))
        dossier.mkdir(parents=True, exist_ok=True)
        with (dossier / 'diagnostic.log').open('a', encoding='utf-8') as journal:
            sys.stdout = sys.stderr = journal
            try:
                main()
            except Exception:
                traceback.print_exc()
                sys.exit(1)
    else:
        main()
