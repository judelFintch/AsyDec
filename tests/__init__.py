"""Tests unitaires : `.venv/bin/python -m unittest discover -s tests -t .`"""
import tempfile
from pathlib import Path

from asydec.systeme import espace_travail
from asydec.systeme import journal

# Sécurité : les tests ne lisent jamais le dossier de travail réel de l'utilisateur. Sans dossier
# choisi, le rangement retombe sur generer.DEC, que les tests redirigent vers un dossier temporaire.
_CONFIGURATION = tempfile.TemporaryDirectory(prefix='asydec-tests-')
espace_travail.FICHIER = Path(_CONFIGURATION.name) / 'espace_travail.json'
# Le journal d'erreurs des tests (fausses applications) ne va jamais dans DONNEES/asydec.log.
journal.FICHIER = Path(_CONFIGURATION.name) / 'asydec.log'
