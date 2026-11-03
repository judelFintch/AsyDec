"""Journal des erreurs ignorées : les aides facultatives qui échouent sans bloquer l'utilisateur
y laissent leur trace complète, pour qu'un vrai défaut ne passe pas inaperçu.

Sans `activer()` (tests, scripts), rien n'est écrit ni affiché.
"""
import logging
from logging.handlers import RotatingFileHandler

from asydec import chemins

FICHIER = chemins.DONNEES / 'asydec.log'

journal = logging.getLogger('asydec')
journal.addHandler(logging.NullHandler())
journal.propagate = False


def activer(fichier=None):
    """Écrit le journal dans DONNEES/asydec.log (1 Mo, 3 archives). Sans effet s'il est déjà actif."""
    if any(isinstance(h, RotatingFileHandler) for h in journal.handlers):
        return
    fichier = fichier or FICHIER
    fichier.parent.mkdir(parents=True, exist_ok=True)
    gestionnaire = RotatingFileHandler(fichier, maxBytes=1_000_000, backupCount=3, encoding='utf-8')
    gestionnaire.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s : %(message)s'))
    journal.addHandler(gestionnaire)
    journal.setLevel(logging.INFO)


def erreur_ignoree(contexte):
    """À appeler dans un `except` : note l'exception en cours et sa trace, sans la relancer."""
    journal.warning('Erreur ignorée — %s', contexte, exc_info=True)
