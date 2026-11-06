"""Détection d'une nouvelle version du code sur le disque, pour le bouton « Recharger » (sources uniquement)."""
import sys

from asydec import chemins

PAQUET = chemins.CODE / 'asydec'


def empreinte(racine=PAQUET):
    """Date et taille de chaque module de l'application, sous-paquets compris ; les tests sont ignorés."""
    if getattr(sys, 'frozen', False):
        return {}
    sortie = {}
    for fichier in sorted(racine.rglob('*.py')):
        if fichier.name.startswith('test_'):
            continue
        try:
            etat = fichier.stat()
        except OSError:
            continue
        sortie[fichier.relative_to(racine).as_posix()] = (etat.st_mtime_ns, etat.st_size)
    return sortie


def commande():
    """Arguments de relance : même interpréteur, paquet principal (à lancer depuis chemins.CODE)."""
    return [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, '-m', 'asydec']
