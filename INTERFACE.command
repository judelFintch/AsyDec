#!/bin/bash
# Double-cliquez sur ce fichier pour ouvrir l'interface du générateur
cd "$(dirname "$0")" || exit 1
./.venv/bin/python -m asydec
