"""Proposition de numéros de conteneur (ISO 6346) et de scellés, une paire par part.

Conteneur : 3 lettres propriétaire + U (catégorie) + 6 chiffres de série + 1 chiffre de contrôle.
Le chiffre de contrôle est calculé selon ISO 6346 ; les numéros proposés sont donc valides.
Scellé : préfixe G915 suivi de 4 chiffres, comme les scellés fournis en exemple.
"""
import re
import secrets

PROPRIETAIRE = 'MRSU'
PREFIXE_SCELLE = 'G915'
FORMAT_CONTENEUR = r'[A-Z]{3}[UJZ] \d{7}'
FORMAT_SCELLE = r'[A-Z]\d{7}'


def _valeurs_lettres():
    # ISO 6346 : A=10, puis on saute les multiples de 11 (11, 22, 33).
    valeurs, valeur = {}, 10
    for lettre in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        if valeur % 11 == 0:
            valeur += 1
        valeurs[lettre] = valeur
        valeur += 1
    return valeurs


VALEURS = _valeurs_lettres()


def chiffre_controle(code):
    """Chiffre de contrôle pour les 10 premiers caractères (ex. 'MRSU608351')."""
    code = code.replace(' ', '').upper()
    if not re.fullmatch(r'[A-Z]{4}\d{6}', code):
        raise ValueError('Code conteneur attendu : 4 lettres et 6 chiffres.')
    total = sum((VALEURS[c] if c.isalpha() else int(c)) * 2 ** i for i, c in enumerate(code))
    return total % 11 % 10


def est_valide(numero):
    if not isinstance(numero, str) or not re.fullmatch(FORMAT_CONTENEUR, numero):
        return False
    code = numero.replace(' ', '')
    return chiffre_controle(code[:10]) == int(code[10])


def nouveau_conteneur(proprietaire=PROPRIETAIRE):
    serie = f'{secrets.randbelow(1_000_000):06d}'
    return f'{proprietaire} {serie}{chiffre_controle(proprietaire + serie)}'


def nouveau_scelle(prefixe=PREFIXE_SCELLE):
    return prefixe + f'{secrets.randbelow(10 ** (8 - len(prefixe))):0{8 - len(prefixe)}d}'


def proposer(nombre, existants=()):
    """Une paire {conteneur, scelle} par part : conserve les paires valides, complète sans doublon."""
    resultat = [None] * nombre
    conteneurs, scelles = set(), set()
    for i, paire in enumerate(list(existants)[:nombre]):
        if not isinstance(paire, dict):
            continue
        conteneur, scelle = paire.get('conteneur'), paire.get('scelle')
        if (est_valide(conteneur) and isinstance(scelle, str) and re.fullmatch(FORMAT_SCELLE, scelle)
                and conteneur not in conteneurs and scelle not in scelles):
            resultat[i] = dict(conteneur=conteneur, scelle=scelle)
            conteneurs.add(conteneur)
            scelles.add(scelle)
    for i, paire in enumerate(resultat):
        if paire is None:
            conteneur = nouveau_conteneur()
            while conteneur in conteneurs:
                conteneur = nouveau_conteneur()
            scelle = nouveau_scelle()
            while scelle in scelles:
                scelle = nouveau_scelle()
            conteneurs.add(conteneur)
            scelles.add(scelle)
            resultat[i] = dict(conteneur=conteneur, scelle=scelle)
    return resultat


def completer(parts):
    """Ajoute ou corrige conteneur et scellé sur chaque part. Retourne True si modifié."""
    anciens = [dict(conteneur=p.get('conteneur'), scelle=p.get('scelle')) for p in parts]
    nouveaux = proposer(len(parts), anciens)
    for part, paire in zip(parts, nouveaux):
        part.update(paire)
    return anciens != nouveaux
