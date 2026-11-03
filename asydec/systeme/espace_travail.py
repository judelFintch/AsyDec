"""Dossier de travail d'AsyDec : l'unique endroit où l'application range les fichiers qu'elle produit.

Choisi par l'utilisateur au premier lancement (Documents/AsyDec par défaut), il est organisé ainsi :

    <dossier de travail>/
    ├── 1 - IMPORTATEURS/<IMPORTATEUR>/
    │   ├── 1 - BASES SYDONIA/            XML de base reçus pour préparer les déclarations
    │   ├── 2 - DECLARATIONS GENEREES/    sorties du générateur, numérotées
    │   ├── 3 - XML VALIDES/              modèles validés téléchargés, nommés par plaque
    │   ├── 4 - DECLARATIONS REELLES/     déclarations SYDONIA effectives (comparaisons)
    │   ├── 5 - PDF/
    │   └── 6 - FACTURES/
    ├── 2 - RAPPORTS/AAAA-MM/             exports Excel (comparaisons, ratios, études, références)
    ├── 3 - A TRIER/                      fichiers anciens dont l'importateur n'a pas pu être reconnu
    └── 4 - SAUVEGARDES/

Les données internes (bases SQLite, compte, médiathèque archivée) restent dans OUTILS : elles
appartiennent au logiciel, pas à l'utilisateur. Tant qu'aucun dossier de travail n'est choisi
(tests, scripts), l'ancienne organisation DEC FRIPERIE/<IMPORTATEUR>/ est utilisée.
"""
import hashlib
import json
import os
from datetime import date
from pathlib import Path
import shutil

from asydec import chemins

FICHIER = chemins.CONFIG_LOCAL / 'espace_travail.json'
DEFAUT = Path.home() / 'Documents' / 'AsyDec'

IMPORTATEURS, RAPPORTS, A_TRIER, SAUVEGARDES = '1 - IMPORTATEURS', '2 - RAPPORTS', '3 - A TRIER', '4 - SAUVEGARDES'
RANGEMENT = {'sources': '1 - BASES SYDONIA', 'historique': '2 - DECLARATIONS GENEREES',
             'valides': '3 - XML VALIDES', 'reelles': '4 - DECLARATIONS REELLES',
             'pdf': '5 - PDF', 'factures': '6 - FACTURES'}
# Ancienne organisation, directement dans DEC FRIPERIE : encore lue, et utilisée sans dossier de travail.
ANCIEN_RANGEMENT = {'sources': '2 - VOS FICHIERS (bases et SYDONIA)', 'historique': '1 - HISTORIQUE',
                    'valides': '4 - XML VALIDES', 'reelles': 'COMPARAISON', 'pdf': '5 - PDF', 'factures': '6 - FACTURES'}

LISEZMOI = """AsyDec — dossier de travail
===========================

Tous les fichiers produits par AsyDec sont rangés ici.

1 - IMPORTATEURS/<IMPORTATEUR>/
    1 - BASES SYDONIA          XML de base reçus pour préparer les déclarations
    2 - DECLARATIONS GENEREES  déclarations produites par le générateur, numérotées
    3 - XML VALIDES            modèles validés téléchargés, nommés par plaque
    4 - DECLARATIONS REELLES   déclarations SYDONIA effectives, comparées aux modèles
    5 - PDF                    impressions des modèles et des comparaisons
    6 - FACTURES               factures Word
2 - RAPPORTS/AAAA-MM/          exports Excel, classés par mois
3 - A TRIER/                   anciens fichiers dont l'importateur n'a pas été reconnu
4 - SAUVEGARDES/

Ne renommez pas ces dossiers : AsyDec les recrée au besoin, mais ne retrouverait plus les fichiers
rangés sous un autre nom.
"""


# =============================================================================
# Choix du dossier
# =============================================================================
def racine(fichier=None):
    """Dossier de travail choisi, ou None s'il n'a pas encore été choisi."""
    try:
        valeur = json.loads(Path(fichier or FICHIER).read_text(encoding='utf-8')).get('racine')
    except (OSError, ValueError, AttributeError):
        return None
    return Path(valeur) if valeur else None


def preparer(dossier):
    """Crée l'arborescence (sans rien effacer) et le fichier LISEZMOI. Renvoie le chemin absolu."""
    dossier = Path(dossier).expanduser().resolve()
    if dossier == chemins.RACINE or chemins.RACINE in dossier.parents:
        raise ValueError('Choisissez un dossier en dehors du logiciel (OUTILS) : il serait effacé avec lui.')
    if dossier.exists() and not dossier.is_dir():
        raise ValueError(f'{dossier} est un fichier, pas un dossier.')
    for nom in (IMPORTATEURS, RAPPORTS, A_TRIER, SAUVEGARDES):
        (dossier / nom).mkdir(parents=True, exist_ok=True)
    lisezmoi = dossier / 'LISEZMOI.txt'
    if not lisezmoi.exists():
        lisezmoi.write_text(LISEZMOI, encoding='utf-8')
    return dossier


def definir(dossier, fichier=None):
    """Prépare le dossier et le retient comme dossier de travail."""
    dossier = preparer(dossier)
    fichier = Path(fichier or FICHIER)
    fichier.parent.mkdir(parents=True, exist_ok=True)
    temporaire = fichier.with_suffix('.tmp')
    temporaire.write_text(json.dumps({'racine': str(dossier)}, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporaire, fichier)
    return dossier


# =============================================================================
# Où ranger
# =============================================================================
def dossier_importateur(importateur, cle, creer=True, ancienne=None):
    """Sous-dossier d'un importateur pour un type de fichier (clé de RANGEMENT).
    ancienne : racine de l'ancienne organisation (DEC FRIPERIE par défaut)."""
    if cle not in RANGEMENT:
        raise ValueError(f'Type de fichier inconnu : {cle}')
    base = racine()
    if base is None:
        chemin = Path(ancienne or chemins.DEC_FRIPERIE) / importateur / ANCIEN_RANGEMENT[cle]
    else:
        chemin = base / IMPORTATEURS / importateur / RANGEMENT[cle]
    if creer:
        chemin.mkdir(parents=True, exist_ok=True)
    return chemin


def dossier_rapports(creer=True, jour=None):
    """2 - RAPPORTS/AAAA-MM du dossier de travail, ou None sans dossier de travail."""
    base = racine()
    if base is None:
        return None
    chemin = base / RAPPORTS / f'{(jour or date.today()):%Y-%m}'
    if creer:
        chemin.mkdir(parents=True, exist_ok=True)
    return chemin


def options_rapport():
    """Options de filedialog.asksaveasfilename pour un export : 2 - RAPPORTS/AAAA-MM, s'il existe."""
    try:
        dossier = dossier_rapports()
    except OSError:
        return {}
    return {'initialdir': str(dossier)} if dossier is not None else {}


def dossier_ouverture():
    """Dossier proposé pour ouvrir un fichier : le dossier des importateurs, sinon DEC FRIPERIE."""
    base = racine()
    return str(base / IMPORTATEURS) if base is not None and (base / IMPORTATEURS).is_dir() else str(chemins.DEC_FRIPERIE)


def emplacements_lecture(ancienne=None):
    """Dossiers où chercher les fichiers existants : le dossier de travail, puis l'ancienne organisation."""
    sortie = [Path(p) for p in (racine(), ancienne or chemins.DEC_FRIPERIE) if p is not None and Path(p).is_dir()]
    return list(dict.fromkeys(sortie))


def relatif(chemin):
    """Chemin lisible : relatif au dossier de travail ou à DEC FRIPERIE, sinon complet."""
    chemin = Path(chemin)
    for base in emplacements_lecture():
        try:
            return str(chemin.resolve().relative_to(base.resolve()))
        except ValueError:
            continue
    return str(chemin)


def dans_espace(chemin):
    base = racine()
    chemin = Path(chemin).resolve()
    return base is not None and (chemin == base or base in chemin.parents)


def _empreinte(chemin):
    return hashlib.sha256(Path(chemin).read_bytes()).hexdigest()


def destination_libre(dossier, nom, source=None):
    """(chemin, deja) : chemin de rangement sous ce nom, suffixé « (2) »… si le nom est pris par un autre
    contenu ; deja = True si un fichier identique à source s'y trouve déjà."""
    dossier, nom = Path(dossier), Path(nom)
    for k in range(1, 1000):
        candidat = dossier / (nom.name if k == 1 else f'{nom.stem} ({k}){nom.suffix}')
        if not candidat.exists():
            return candidat, False
        if source is not None and _empreinte(candidat) == _empreinte(source):
            return candidat, True
    raise ValueError(f'Trop de fichiers nommés {nom.name} dans {dossier}.')


def ranger_copie(source, importateur, cle, ancienne=None):
    """Copie un fichier reçu (base, déclaration réelle) dans le dossier de travail, s'il n'y est pas déjà
    et n'appartient pas au logiciel. Renvoie le chemin rangé ; sinon le fichier d'origine."""
    source = Path(source)
    interne = chemins.RACINE in source.resolve().parents  # médiathèque archivée, compositions…
    if racine() is None or interne or dans_espace(source):
        return source
    destination, deja = destination_libre(dossier_importateur(importateur, cle, ancienne=ancienne), source.name, source)
    if not deja:
        shutil.copy2(source, destination)
    return destination
