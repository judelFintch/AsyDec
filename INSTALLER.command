#!/bin/bash
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
    python3 scripts/installer.py
    resultat=$?
else
    echo 'Python 3 est absent. Installez Python 3.10 ou plus récent avec Tkinter, puis relancez ce fichier.'
    resultat=1
fi
read -n 1 -s -r -p 'Appuyez sur une touche pour fermer…'
exit "$resultat"
