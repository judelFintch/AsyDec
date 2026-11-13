"""Export complet protégé par mot de passe ; aucun secret enregistré dans le programme.

AES-256-GCM authentifie l'en-tête et l'intégralité de l'archive. La clé est dérivée
par scrypt avec un sel aléatoire. Le clair temporaire n'est utilisé qu'après
vérification du tag GCM et est supprimé à la sortie du contexte.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from asydec.systeme import transfert

EXTENSION = '.asydec.enc'
MAGIE = b'ASYDECENC\x01'
ENTETE = len(MAGIE) + 16 + 12
MIN_MOT_DE_PASSE = 12
LIMITE = 1_900_000_000  # compatible avec la limite des fichiers GitHub Releases
BLOC = 1024 * 1024


def verifier_mot_de_passe(mot_de_passe):
    if not isinstance(mot_de_passe, str) or len(mot_de_passe) < MIN_MOT_DE_PASSE:
        raise ValueError(f'Choisissez un mot de passe de sauvegarde d’au moins {MIN_MOT_DE_PASSE} caractères.')


def _cle(mot_de_passe, sel):
    verifier_mot_de_passe(mot_de_passe)
    return Scrypt(salt=sel, length=32, n=2**17, r=8, p=1).derive(mot_de_passe.encode('utf-8'))


def verifier_fichier(source):
    source = Path(source)
    if not source.is_file() or not ENTETE + 16 <= source.stat().st_size <= LIMITE:
        raise ValueError('Taille de sauvegarde chiffrée invalide (maximum 1,9 Go).')
    with source.open('rb') as f:
        if f.read(len(MAGIE)) != MAGIE:
            raise ValueError('Ce fichier n’est pas une sauvegarde AsyDec chiffrée reconnue.')


def chiffrer(source, destination, mot_de_passe):
    verifier_mot_de_passe(mot_de_passe)
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError('Le fichier chiffré doit être distinct de l’export source.')
    if source.stat().st_size + ENTETE + 16 > LIMITE:
        raise ValueError('Sauvegarde trop volumineuse pour GitHub (maximum 1,9 Go).')
    sel, nonce = os.urandom(16), os.urandom(12)
    entete = MAGIE + sel + nonce
    chiffreur = Cipher(algorithms.AES(_cle(mot_de_passe, sel)), modes.GCM(nonce)).encryptor()
    chiffreur.authenticate_additional_data(entete)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporaire = tempfile.mkstemp(prefix='.chiffrement-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as sortie, source.open('rb') as entree:
            sortie.write(entete)
            taille = ENTETE + 16
            for bloc in iter(lambda: entree.read(BLOC), b''):
                taille += len(bloc)
                if taille > LIMITE:
                    raise ValueError('Sauvegarde trop volumineuse (maximum 1,9 Go).')
                sortie.write(chiffreur.update(bloc))
            sortie.write(chiffreur.finalize())
            sortie.write(chiffreur.tag)
            sortie.flush()
            os.fsync(sortie.fileno())
        os.replace(temporaire, destination)
    finally:
        Path(temporaire).unlink(missing_ok=True)
    return destination


def exporter(destination, mot_de_passe, racine=None, avec_sauvegardes=False):
    verifier_mot_de_passe(mot_de_passe)
    destination = Path(destination)
    if not destination.name.endswith(EXTENSION):
        destination = destination.with_name(destination.name + EXTENSION)
    with tempfile.TemporaryDirectory(prefix='asydec-export-prive-') as d:
        archive, resume = transfert.exporter(Path(d) / 'donnees.asydec', racine=racine,
                                            avec_sauvegardes=avec_sauvegardes)
        chiffrer(archive, destination, mot_de_passe)
    return destination, resume


@contextmanager
def ouvrir(source, mot_de_passe):
    """Expose l'archive seulement après authentification complète ; nettoie aussi les échecs."""
    verifier_mot_de_passe(mot_de_passe)
    verifier_fichier(source)
    source = Path(source)
    with tempfile.TemporaryDirectory(prefix='asydec-dechiffrement-') as d:
        archive = Path(d) / 'donnees.asydec'
        with source.open('rb') as entree:
            entete = entree.read(ENTETE)
            sel, nonce = entete[len(MAGIE):len(MAGIE) + 16], entete[-12:]
            entree.seek(-16, os.SEEK_END)
            tag = entree.read(16)
            entree.seek(ENTETE)
            restant = source.stat().st_size - ENTETE - 16
            dechiffreur = Cipher(algorithms.AES(_cle(mot_de_passe, sel)), modes.GCM(nonce, tag)).decryptor()
            dechiffreur.authenticate_additional_data(entete)
            # mkstemp : fichier clair privé, y compris avant la vérification finale.
            fd = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, 'wb') as sortie:
                    while restant:
                        bloc = entree.read(min(BLOC, restant))
                        if not bloc:
                            raise ValueError('Sauvegarde chiffrée tronquée.')
                        restant -= len(bloc)
                        sortie.write(dechiffreur.update(bloc))
                    sortie.write(dechiffreur.finalize())
            except InvalidTag as exc:
                raise ValueError('Mot de passe incorrect ou sauvegarde endommagée. Aucune donnée chargée.') from exc
        manifeste = transfert.lire(archive)
        if manifeste['type'] != 'complet':
            raise ValueError('Cette sauvegarde ne contient pas un export complet.')
        yield archive


def preparer_import(source, mot_de_passe, racine=None):
    with ouvrir(source, mot_de_passe) as archive:
        return transfert.preparer_import_complet(archive, racine=racine)
