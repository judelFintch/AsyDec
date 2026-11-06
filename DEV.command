#!/bin/bash
# Mode développeur : sans mot de passe ni verrouillage auto, bouton « Recharger » actif.
cd "$(dirname "$0")" || exit 1
ASYDEC_DEV=1 ./.venv/bin/python -m asydec
