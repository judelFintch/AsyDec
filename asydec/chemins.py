"""Données locales : OUTILS en développement, Application Support dans le .app.

CODE désigne les ressources du programme ; RACINE désigne les données persistantes.
Une mise à jour de l’application ne doit jamais remplacer ces données.
"""
from pathlib import Path
import os
import sys

CODE = Path(__file__).resolve().parent.parent
COMPILE = bool(getattr(sys, 'frozen', False))
# L’application peut être remplacée ; les données ne vivent jamais dans le .app.
RACINE = (Path(os.environ['ASYDEC_HOME']).expanduser() if os.environ.get('ASYDEC_HOME') else
          (Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / 'AsyDec'
           if sys.platform == 'win32' else Path.home() / 'Library' / 'Application Support' / 'AsyDec')
          if COMPILE else CODE)
DEC_FRIPERIE = RACINE.parent

DONNEES = RACINE / 'DONNEES'
CONFIG_LOCAL = RACINE / 'CONFIG_LOCAL'
SAUVEGARDES = RACINE / 'SAUVEGARDES'
MODELES_XML = RACINE / 'MODELES_XML'
ETUDES_XML = RACINE / 'ETUDES_XML'
SIMULATIONS = RACINE / 'SIMULATIONS'
SAISIE = RACINE / 'SAISIE.xlsx'
REGISTRE = RACINE / 'registre.json'
