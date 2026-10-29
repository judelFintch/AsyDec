"""Emplacements des données locales, tous rattachés au dossier OUTILS (racine du projet).

Les modules vivent dans le paquet asydec/, mais les données restent à la racine :
les déplacer dans le code ne doit jamais déplacer les données de l'utilisateur.
"""
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DEC_FRIPERIE = RACINE.parent

DONNEES = RACINE / 'DONNEES'
CONFIG_LOCAL = RACINE / 'CONFIG_LOCAL'
SAUVEGARDES = RACINE / 'SAUVEGARDES'
MODELES_XML = RACINE / 'MODELES_XML'
ETUDES_XML = RACINE / 'ETUDES_XML'
SIMULATIONS = RACINE / 'SIMULATIONS'
SAISIE = RACINE / 'SAISIE.xlsx'
REGISTRE = RACINE / 'registre.json'
