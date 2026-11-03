"""Suite complète, un processus par module pour isoler les cycles natifs de Tk."""
from pathlib import Path
import subprocess
import sys

racine=Path(__file__).resolve().parents[1]
erreurs=[]
for fichier in sorted((racine/'tests').glob('test_*.py')):
    nom='tests.'+fichier.stem
    try:
        resultat=subprocess.run([sys.executable,'-B','-m','unittest',nom],cwd=racine,
                                capture_output=True,text=True,timeout=120)
        if resultat.returncode:
            erreurs.append(nom)
            print(nom+' : ÉCHEC\n'+resultat.stdout+resultat.stderr,flush=True)
        else:
            print(nom+' : OK',flush=True)
    except subprocess.TimeoutExpired:
        erreurs.append(nom)
        print(nom+' : DÉLAI DÉPASSÉ',flush=True)
if erreurs:
    print('Modules en échec : '+', '.join(erreurs))
    sys.exit(1)
print('Tous les modules de tests passent.')
