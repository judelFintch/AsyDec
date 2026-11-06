"""Dossier de travail d'AsyDec : l'unique endroit où l'application range les fichiers qu'elle produit.

Choisi par l'utilisateur au premier lancement (Documents/AsyDec par défaut), il est organisé ainsi :

    <dossier de travail>/
    ├── 1 - FRIPERIE/<IMPORTATEUR>/       fichiers du module Friperie
    │   ├── 1 - BASES SYDONIA/            XML de base reçus pour préparer les déclarations
    │   ├── 2 - DECLARATIONS GENEREES/    sorties du générateur, numérotées
    │   ├── 3 - XML VALIDES/              modèles validés téléchargés, nommés par plaque
    │   ├── 4 - DECLARATIONS REELLES/     déclarations SYDONIA effectives (comparaisons)
    │   ├── 5 - PDF/
    │   └── 6 - FACTURES/
    ├── 2 - DIVERS/<IMPORTATEUR>/         même organisation, module Divers
    ├── 3 - DOCUMENTS FINAUX/<NUMERO DEC>/ créé à l'ouverture d'une licence
    │   ├── 1 - LICENCE/
    │   ├── 2 - XML GENERES/
    │   └── 3 - XML SYDONIA/
    ├── 4 - RAPPORTS/AAAA-MM/             exports Excel (comparaisons, ratios, études, références)
    ├── 5 - A TRIER/                      fichiers anciens dont l'importateur n'a pas pu être reconnu
    └── 6 - SAUVEGARDES/

L'ancienne organisation (1 - IMPORTATEURS, 2 - RAPPORTS, 3 - A TRIER, 4 - SAUVEGARDES) est migrée
automatiquement : les dossiers sont renommés, rien n'est effacé.

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

FRIPERIE, DIVERS, DOCUMENTS_FINAUX = '1 - FRIPERIE', '2 - DIVERS', '3 - DOCUMENTS FINAUX'
RAPPORTS, A_TRIER, SAUVEGARDES = '4 - RAPPORTS', '5 - A TRIER', '6 - SAUVEGARDES'
IMPORTATEURS = FRIPERIE  # ancien nom, gardé pour les appels existants
DOSSIERS = (FRIPERIE, DIVERS, DOCUMENTS_FINAUX, RAPPORTS, A_TRIER, SAUVEGARDES)
MODULES = {'friperie': FRIPERIE, 'divers': DIVERS, 'documents_finaux': DOCUMENTS_FINAUX}
# Organisation précédente du dossier de travail → nouveaux noms.
ANCIENS_DOSSIERS = {'1 - IMPORTATEURS': FRIPERIE, '2 - RAPPORTS': RAPPORTS,
                    '3 - A TRIER': A_TRIER, '4 - SAUVEGARDES': SAUVEGARDES}
RANGEMENT_DEC = {'licence': '1 - LICENCE', 'xml_generes': '2 - XML GENERES', 'xml_sydonia': '3 - XML SYDONIA',
                 'factures': '4 - FACTURES', 'cvi': '5 - CVI', 'declarations': '6 - DECLARATIONS'}
_module = {'cle': 'friperie'}
RANGEMENT = {'sources': '1 - BASES SYDONIA', 'historique': '2 - DECLARATIONS GENEREES',
             'valides': '3 - XML VALIDES', 'reelles': '4 - DECLARATIONS REELLES',
             'pdf': '5 - PDF', 'factures': '6 - FACTURES'}
# Ancienne organisation, directement dans DEC FRIPERIE : encore lue, et utilisée sans dossier de travail.
ANCIEN_RANGEMENT = {'sources': '2 - VOS FICHIERS (bases et SYDONIA)', 'historique': '1 - HISTORIQUE',
                    'valides': '4 - XML VALIDES', 'reelles': 'COMPARAISON', 'pdf': '5 - PDF', 'factures': '6 - FACTURES'}

LISEZMOI = """AsyDec — dossier de travail
===========================

Tous les fichiers produits par AsyDec sont rangés ici, un dossier par module.

1 - FRIPERIE/<IMPORTATEUR>/     module Friperie
    1 - BASES SYDONIA          XML de base reçus pour préparer les déclarations
    2 - DECLARATIONS GENEREES  déclarations produites par le générateur, numérotées
    3 - XML VALIDES            modèles validés téléchargés, nommés par plaque
    4 - DECLARATIONS REELLES   déclarations SYDONIA effectives, comparées aux modèles
    5 - PDF                    impressions des modèles et des comparaisons
    6 - FACTURES               factures Word
2 - DIVERS/<IMPORTATEUR>/       module Divers, même organisation
3 - DOCUMENTS FINAUX/<DEC>/     un dossier par numéro DEC, créé à l'ouverture de la licence
    1 - LICENCE                licence importée (PDF ou photo)
    2 - XML GENERES            XML générés à l'étape 6
    3 - XML SYDONIA            XML récupérés de SYDONIA à l'étape 7
    4 - FACTURES               facture et packing list de la part 1 (étape 5)
4 - RAPPORTS/AAAA-MM/          exports Excel, classés par mois
5 - A TRIER/                   anciens fichiers dont l'importateur n'a pas été reconnu
6 - SAUVEGARDES/

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
    migrer(dossier)
    for nom in DOSSIERS:
        (dossier / nom).mkdir(parents=True, exist_ok=True)
    lisezmoi = dossier / 'LISEZMOI.txt'
    # Le LISEZMOI d'AsyDec est tenu à jour ; un fichier écrit par l'utilisateur n'est pas touché.
    if not lisezmoi.exists() or (lisezmoi.read_text(encoding='utf-8', errors='ignore').startswith('AsyDec — dossier de travail')
                                 and lisezmoi.read_text(encoding='utf-8', errors='ignore') != LISEZMOI):
        lisezmoi.write_text(LISEZMOI, encoding='utf-8')
    return dossier


def migrer(dossier):
    """Renomme les dossiers de l'ancienne organisation, sans rien effacer ni écraser.

    Un élément déjà présent sous le nouveau nom reste dans l'ancien dossier (signalé dans le retour).
    Les chemins enregistrés dans les historiques sont traduits à la lecture (chemin_actuel).
    Retourne {'deplaces': [(ancien, nouveau)], 'conflits': [chemins restés en place]}.
    """
    dossier = Path(dossier)
    deplaces, conflits = [], []
    for ancien, nouveau in ANCIENS_DOSSIERS.items():
        source, cible = dossier / ancien, dossier / nouveau
        if not source.is_dir():
            continue
        if not cible.exists():
            source.rename(cible)
            deplaces.append((source, cible))
            continue
        for element in sorted(source.iterdir()):
            if element.name == '.DS_Store':
                continue
            if (cible / element.name).exists():
                conflits.append(element)
            else:
                element.rename(cible / element.name)
                deplaces.append((element, cible / element.name))
        try:
            (source / '.DS_Store').unlink(missing_ok=True)
            source.rmdir()
        except OSError:
            pass  # dossier non vide : un conflit à régler à la main
    return {'deplaces': deplaces, 'conflits': conflits}


def chemin_actuel(chemin):
    """Chemin enregistré avant la réorganisation par module (« 1 - IMPORTATEURS/… ») → emplacement actuel.

    Les historiques internes sont immuables : on ne réécrit pas les chemins, on les traduit à la lecture.
    Le chemin d'origine est renvoyé s'il existe encore ou si aucun équivalent n'est trouvé.
    """
    if not chemin:
        return chemin
    texte = str(chemin)
    if os.path.exists(texte):
        return chemin
    for ancien, nouveau in ANCIENS_DOSSIERS.items():
        segment = os.sep + ancien + os.sep
        if segment in texte:
            candidat = texte.replace(segment, os.sep + nouveau + os.sep, 1)
            if os.path.exists(candidat):
                return type(chemin)(candidat) if isinstance(chemin, Path) else candidat
    return chemin


def definir_module(cle):
    """Module ouvert : les fichiers d'importateurs sont rangés dans son dossier (Friperie ou Divers)."""
    if cle in ('friperie', 'divers'):
        _module['cle'] = cle


def module_courant():
    return _module['cle']


def nom_dossier_dec(numero_dec):
    import re
    nom = re.sub(r'[^A-Za-z0-9._ -]', '-', str(numero_dec or '').strip()).strip(' .-')
    if not nom:
        raise ValueError('Numéro DEC manquant : dossier non créé.')
    return nom


def dossier_dec(numero_dec, cle=None, creer=True):
    """3 - DOCUMENTS FINAUX/<DEC>[/sous-dossier] ; None sans dossier de travail."""
    base = racine()
    if base is None:
        return None
    chemin = base / DOCUMENTS_FINAUX / nom_dossier_dec(numero_dec)
    if creer:
        for sous in RANGEMENT_DEC.values():
            (chemin / sous).mkdir(parents=True, exist_ok=True)
    return chemin / RANGEMENT_DEC[cle] if cle else chemin


LICENCES_SUPPRIMEES = 'LICENCES SUPPRIMEES'


def archiver_dossier_dec(numero_dec, garder=()):
    """Déplace le dossier DEC dans 6 - SAUVEGARDES/LICENCES SUPPRIMEES (jamais effacé).

    La même DEC repart ainsi d'un dossier vide, sans fichiers « (2) » mélangés aux anciens.
    garder : sous-dossiers recopiés dans le nouveau dossier DEC (ex. ('licence',) pour recommencer).
    Renvoie le chemin de l'archive, ou None s'il n'y avait pas de dossier.
    """
    from datetime import datetime
    base = racine()
    if base is None or not str(numero_dec or '').strip():
        return None
    source = dossier_dec(numero_dec, creer=False)
    if not source.is_dir():
        return None
    archives = base / SAUVEGARDES / LICENCES_SUPPRIMEES
    archives.mkdir(parents=True, exist_ok=True)
    nom = f"{source.name} - supprimee le {datetime.now():%Y-%m-%d %H%M}"
    destination = archives / nom
    k = 2
    while destination.exists():
        destination, k = archives / f'{nom} ({k})', k + 1
    shutil.move(str(source), str(destination))
    for cle in garder:
        if (destination / RANGEMENT_DEC[cle]).is_dir():
            cible = dossier_dec(numero_dec, cle)
            shutil.copytree(destination / RANGEMENT_DEC[cle], cible, dirs_exist_ok=True)
    return destination


def ranger_dans_dec(source, numero_dec, cle):
    """Copie un fichier dans le dossier DEC (sans doublon) ; renvoie le chemin rangé, ou None."""
    dossier = dossier_dec(numero_dec, cle)
    if dossier is None:
        return None
    source = Path(source)
    if dossier.resolve() == source.resolve().parent:
        return source
    destination, deja = destination_libre(dossier, source.name, source)
    if not deja:
        shutil.copy2(source, destination)
    return destination


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
def dossier_importateur(importateur, cle, creer=True, ancienne=None, module=None):
    """Sous-dossier d'un importateur pour un type de fichier (clé de RANGEMENT), dans le dossier
    du module (Friperie ou Divers ; par défaut le module ouvert).
    ancienne : racine de l'ancienne organisation (DEC FRIPERIE par défaut)."""
    if cle not in RANGEMENT:
        raise ValueError(f'Type de fichier inconnu : {cle}')
    base = racine()
    if base is None:
        chemin = Path(ancienne or chemins.DEC_FRIPERIE) / importateur / ANCIEN_RANGEMENT[cle]
    else:
        chemin = base / MODULES.get(module or _module['cle'], FRIPERIE) / importateur / RANGEMENT[cle]
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
    if base is None:
        return str(chemins.DEC_FRIPERIE)
    dossier = base / MODULES.get(_module['cle'], FRIPERIE)
    return str(dossier) if dossier.is_dir() else str(base)


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
