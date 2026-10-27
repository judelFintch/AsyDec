"""Détection d'une nouvelle version du code sur le disque, pour le bouton « Recharger »."""
from pathlib import Path
import sys

RACINE = Path(__file__).resolve().parent


def empreinte(racine=RACINE):
    """Date et taille de chaque module de l'application ; les tests sont ignorés."""
    sortie = {}
    for dossier in (racine, racine / 'ui'):
        for fichier in sorted(dossier.glob('*.py')):
            if fichier.name.startswith('test_'):
                continue
            try:
                etat = fichier.stat()
            except OSError:
                continue
            sortie[str(fichier.relative_to(racine))] = (etat.st_mtime_ns, etat.st_size)
    return sortie


def commande(racine=RACINE):
    """Arguments de relance : même interpréteur, point d'entrée principal."""
    return [sys.executable, str(racine / 'asydec.py')]
