"""Compte administrateur, préférences locales et remise à zéro des données de travail.

Indépendant du schéma et des services du module de références.
"""
import datetime
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile
import time

RACINE = Path(__file__).resolve().parent
CONFIGURATION = RACINE / 'CONFIG_LOCAL'
MIN_MOT_DE_PASSE = 8
ITERATIONS = 600_000
MAX_ECHECS = 5
DELAI_BLOCAGE = 60
PHRASE_RESET = 'REINITIALISER'
DEFAUTS = {
    'organisation': '', 'memoriser_recents': True, 'dossier_xml': '',
    'page_demarrage': 'dossier', 'verrouillage_minutes': 15,
}
PAGES_DEMARRAGE = ('dossier', 'repartitions', 'ratios', 'etude', 'historique', 'parametres')
# Ne jamais parcourir le dossier parent ni supprimer les historiques d'exports.
DONNEES_RESET = ('DONNEES/asydec.db', 'DONNEES/asydec.db-wal', 'DONNEES/asydec.db-shm', 'DONNEES/asydec.db-journal',
                 'DONNEES/sources', 'MODELES_XML', 'ETUDES_XML', 'registre.json', 'SAISIE.xlsx')


class ErreurCompte(ValueError):
    pass


def _ecrire_json(chemin, contenu):
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporaire = tempfile.mkstemp(dir=chemin.parent, prefix='.ecriture-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fichier:
            json.dump(contenu, fichier, ensure_ascii=False, indent=2, allow_nan=False)
            fichier.flush()
            os.fsync(fichier.fileno())
        os.replace(temporaire, chemin)
    finally:
        if os.path.exists(temporaire):
            os.unlink(temporaire)


def compte_existe(configuration=None):
    return ((Path(configuration) if configuration is not None else CONFIGURATION) / 'compte.json').exists()


def _lire_compte(configuration=None):
    chemin = (Path(configuration) if configuration is not None else CONFIGURATION) / 'compte.json'
    try:
        compte = json.loads(chemin.read_text(encoding='utf-8'))
        if not isinstance(compte, dict):
            raise ValueError('Format de compte non reconnu')
        if (compte.get('algorithme') != 'pbkdf2_sha256' or compte.get('iterations') != ITERATIONS or
                len(bytes.fromhex(compte['sel'])) != 32 or len(bytes.fromhex(compte['empreinte'])) != 32 or
                not isinstance(compte['identifiant'], str) or not isinstance(compte.get('echecs', 0), int) or
                not isinstance(compte.get('bloque_jusqua', 0), (int, float)) or
                not math.isfinite(compte.get('bloque_jusqua', 0)) or not 0 <= compte.get('echecs', 0) < MAX_ECHECS):
            raise ValueError('Format de compte non reconnu')
        return compte
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ErreurCompte('Le compte local est illisible. Restaurez une copie du compte ; il ne sera pas recréé automatiquement.') from exc


def _verifier_mot_de_passe(mot_de_passe):
    if not isinstance(mot_de_passe, str) or len(mot_de_passe) < MIN_MOT_DE_PASSE:
        raise ErreurCompte(f'Choisissez un mot de passe d’au moins {MIN_MOT_DE_PASSE} caractères.')


def _empreinte(mot_de_passe, sel):
    return hashlib.pbkdf2_hmac('sha256', mot_de_passe.encode('utf-8'), sel, ITERATIONS).hex()


def creer_compte(identifiant, mot_de_passe, configuration=None):
    configuration = Path(configuration) if configuration is not None else CONFIGURATION
    identifiant = identifiant.strip()
    if not re.fullmatch(r'[\w.-]{3,64}', identifiant):
        raise ErreurCompte('Identifiant : 3 à 64 lettres, chiffres, points, tirets ou traits de soulignement.')
    _verifier_mot_de_passe(mot_de_passe)
    sel = secrets.token_bytes(32)
    compte = {'version': 1, 'identifiant': identifiant, 'algorithme': 'pbkdf2_sha256',
              'iterations': ITERATIONS, 'sel': sel.hex(), 'empreinte': _empreinte(mot_de_passe, sel),
              'echecs': 0, 'bloque_jusqua': 0, 'cree_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    configuration.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Création exclusive : un lancement concurrent ne peut pas remplacer un compte existant.
    chemin = configuration / 'compte.json'
    fd = os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fichier:
            json.dump(compte, fichier, ensure_ascii=False, indent=2)
            fichier.flush()
            os.fsync(fichier.fileno())
    except Exception:
        chemin.unlink(missing_ok=True)
        raise
    return identifiant


def authentifier(identifiant, mot_de_passe, configuration=None, maintenant=None):
    configuration = Path(configuration) if configuration is not None else CONFIGURATION
    if not isinstance(identifiant, str) or not isinstance(mot_de_passe, str):
        raise ErreurCompte('Identifiant et mot de passe requis.')
    compte = _lire_compte(configuration)
    maintenant = time.time() if maintenant is None else maintenant
    if compte.get('bloque_jusqua', 0) > maintenant:
        raise ErreurCompte('Trop de tentatives. Attendez une minute avant de réessayer.')
    valide = hmac.compare_digest(_empreinte(mot_de_passe, bytes.fromhex(compte['sel'])), compte['empreinte'])
    valide = valide and identifiant.strip().casefold() == compte['identifiant'].casefold()
    if valide:
        compte.update(echecs=0, bloque_jusqua=0)
    else:
        echecs = compte.get('echecs', 0) + 1
        compte['echecs'] = echecs if echecs < MAX_ECHECS else 0
        compte['bloque_jusqua'] = maintenant + DELAI_BLOCAGE if echecs >= MAX_ECHECS else 0
    _ecrire_json(configuration / 'compte.json', compte)
    return valide


def identifiant_compte(configuration=None):
    return _lire_compte(configuration)['identifiant']


def changer_mot_de_passe(ancien, nouveau, configuration=None):
    configuration = Path(configuration) if configuration is not None else CONFIGURATION
    _verifier_mot_de_passe(nouveau)
    compte = _lire_compte(configuration)
    if not authentifier(compte['identifiant'], ancien, configuration):
        raise ErreurCompte('Le mot de passe actuel est incorrect.')
    sel = secrets.token_bytes(32)
    compte.update(sel=sel.hex(), empreinte=_empreinte(nouveau, sel), echecs=0, bloque_jusqua=0)
    _ecrire_json(configuration / 'compte.json', compte)


def lire_reglages(configuration=None):
    configuration = Path(configuration) if configuration is not None else CONFIGURATION
    chemin = configuration / 'reglages.json'
    if not chemin.exists():
        return dict(DEFAUTS)
    try:
        valeurs = json.loads(chemin.read_text(encoding='utf-8'))
        return valider_reglages(valeurs)
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError('Les paramètres locaux sont illisibles. Restaurez-les ou remettez les paramètres par défaut.') from exc


def valider_reglages(valeurs):
    if not isinstance(valeurs, dict):
        raise ValueError('Paramètres non reconnus.')
    reglages = dict(DEFAUTS)
    reglages.update({cle: valeurs[cle] for cle in DEFAUTS if cle in valeurs})
    if not isinstance(reglages['organisation'], str) or len(reglages['organisation']) > 100:
        raise ValueError('Le nom de l’organisation est limité à 100 caractères.')
    if type(reglages['memoriser_recents']) is not bool:
        raise ValueError('Le choix de mémorisation des fichiers récents est invalide.')
    if reglages['page_demarrage'] not in PAGES_DEMARRAGE:
        raise ValueError('Page de démarrage inconnue.')
    if type(reglages['verrouillage_minutes']) is not int or not 0 <= reglages['verrouillage_minutes'] <= 240:
        raise ValueError('Le verrouillage doit être compris entre 0 et 240 minutes ; 0 le désactive.')
    if not isinstance(reglages['dossier_xml'], str) or (reglages['dossier_xml'] and not Path(reglages['dossier_xml']).is_dir()):
        raise ValueError('Le dossier XML choisi n’existe pas.')
    return reglages


def enregistrer_reglages(valeurs, configuration=None):
    configuration = Path(configuration) if configuration is not None else CONFIGURATION
    valeurs = valider_reglages(valeurs)
    _ecrire_json(configuration / 'reglages.json', valeurs)
    return valeurs


def apercu_reset(racine=None):
    racine = Path(racine) if racine is not None else RACINE
    resultat = []
    for nom in ('DONNEES', 'CONFIG_LOCAL'):
        if (racine / nom).is_symlink():
            raise ValueError(f'Reset refusé : {nom} est un lien symbolique.')
    for nom in DONNEES_RESET:
        chemin = racine / nom
        if chemin.exists() or chemin.is_symlink():
            if chemin.is_symlink():
                raise ValueError(f'Reset refusé : {nom} est un lien symbolique.')
            resultat.append(nom)
    for nom in ('reglages.json', 'preferences.json'):
        if (racine / 'CONFIG_LOCAL' / nom).exists():
            resultat.append('CONFIG_LOCAL/' + nom)
    return resultat


def reinitialiser(mot_de_passe, confirmation, racine=None, avant_reset=None):
    """Archive les seules données gérées par l'application. Ne touche jamais aux exports.

    Aucune fonction de ce module n'appelle le reset au chargement ou au démarrage.
    """
    racine = Path(racine) if racine is not None else RACINE
    configuration = racine / 'CONFIG_LOCAL'
    if confirmation != PHRASE_RESET:
        raise ValueError('Saisissez exactement REINITIALISER pour confirmer.')
    if not authentifier(identifiant_compte(configuration), mot_de_passe, configuration):
        raise ErreurCompte('Mot de passe incorrect ; aucune donnée de travail réinitialisée.')
    apercu_reset(racine)
    if avant_reset is not None:
        avant_reset()
    # Stabilise la base SQLite sans dépendre de son schéma. Un import actif doit être arrêté.
    base = racine / 'DONNEES' / 'asydec.db'
    if base.exists():
        conn = sqlite3.connect(base, timeout=0)
        try:
            resultat = conn.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
            if resultat and resultat[0] != 0:
                raise ValueError('Base utilisée par une autre fenêtre. Fermez les autres sessions avant le reset.')
            conn.execute('BEGIN EXCLUSIVE')
            conn.rollback()
        except sqlite3.Error as exc:
            raise ValueError('Base occupée ou illisible. Fermez les autres sessions avant le reset.') from exc
        finally:
            conn.close()
    plan = apercu_reset(racine)
    sauvegardes = racine / 'SAUVEGARDES'
    if sauvegardes.is_symlink() or configuration.is_symlink():
        raise ValueError('Les dossiers de configuration et de sauvegarde ne doivent pas être des liens symboliques.')
    sauvegardes.mkdir(exist_ok=True, mode=0o700)
    date = datetime.datetime.now(datetime.timezone.utc)
    sauvegarde = sauvegardes / ('reset-' + date.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3))
    sauvegarde.mkdir(mode=0o700)
    deplaces = []
    try:
        for nom in plan:
            source = racine / nom
            cible = sauvegarde / nom
            cible.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.replace(source, cible)
            deplaces.append(nom)
        _ecrire_json(sauvegarde / 'manifest.json', {
            'version': 1, 'reset_utc': date.isoformat(), 'compte': identifiant_compte(configuration),
            'elements_archives': deplaces,
            'conserves': ['compte administrateur', 'XML originaux externes', 'exports et simulations Excel', 'code du projet'],
        })
    except Exception:
        for nom in reversed(deplaces):
            os.replace(sauvegarde / nom, racine / nom)
        raise
    return sauvegarde
