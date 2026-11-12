"""Prépare l'environnement local et télécharge les dépendances du projet."""
from pathlib import Path
import subprocess
import sys
import venv

RACINE = Path(__file__).resolve().parents[1]


def main():
    if sys.version_info < (3, 10):
        raise SystemExit('Installez Python 3.10 ou plus récent, puis relancez l’installation.')
    environnement = RACINE / '.venv'
    python = environnement / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if not python.is_file():
        print('Préparation de l’environnement Python…', flush=True)
        venv.EnvBuilder(with_pip=True).create(environnement)
    print('Téléchargement et installation des dépendances (connexion Internet nécessaire)…', flush=True)
    try:
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(RACINE / 'requirements.txt')],
                       cwd=RACINE, check=True)
        subprocess.run([str(python), '-c', 'import tkinter; import PIL; import pymupdf; import asydec.declarations.sceau'],
                       cwd=RACINE, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print('Installation incomplète. Vérifiez la connexion Internet et les erreurs ci-dessus, '
              'puis relancez ce programme. Python doit inclure Tkinter.', file=sys.stderr)
        raise SystemExit(1) from exc
    print('Installation terminée. Le sceau bleu est disponible. Lancez AsyDec avec ASYDEC.command '
          'sur Mac, ou .venv\\Scripts\\python.exe -m asydec sur Windows.')


if __name__ == '__main__':
    main()
