#!/bin/bash
# Double-cliquez sur ce fichier pour générer les déclarations de SAISIE.xlsx
cd "$(dirname "$0")" || exit 1
./.venv/bin/python generer.py
echo
read -n 1 -s -r -p "Appuyez sur une touche pour fermer..."
