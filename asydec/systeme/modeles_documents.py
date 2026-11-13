"""Modèles Word persistants, utilisables après transfert et mise à jour du programme."""
import os
from pathlib import Path
import tempfile
from xml.parsers.expat import ExpatError

from asydec import chemins

DOSSIER = 'MODELES_DOCUMENTS'
MODELES = {
    'cvi_bl': ('cvi/CVI-modele.docx', 'CVI et BL'),
    'declaration': ('declaration/Declaration-modele.docx', 'Déclaration DEC'),
    'facture_kinshop': ('factures/kinshop/facture.docx', 'Facture KINSHOP'),
    'packing_kinshop': ('factures/kinshop/packing.docx', 'Packing list KINSHOP'),
}


def chemin(cle, racine=None, code=None):
    """Le modèle personnel prime sur celui éventuellement livré avec le programme."""
    racine = Path(racine) if racine is not None else chemins.RACINE
    code = Path(code) if code is not None else chemins.CODE
    relatif = MODELES[cle][0]
    personnel = racine / DOSSIER / relatif
    return personnel if personnel.is_file() else code / 'ressources' / relatif


def enregistrer(cle, source, racine=None):
    """Copie autonome du Word choisi : aucun chemin de l'ancienne machine n'est requis."""
    from asydec.declarations import factures
    source = Path(source)
    if source.suffix.lower() != '.docx':
        raise ValueError('Choisissez un modèle Word .docx.')
    contenu = source.read_bytes()
    try:
        archive, _ = factures._parties(contenu)
    except ExpatError as exc:
        raise ValueError('Le modèle Word contient un document illisible.') from exc
    archive.close()
    racine = Path(racine) if racine is not None else chemins.RACINE
    cible = racine / DOSSIER / MODELES[cle][0]
    if cible.is_symlink() or any(p.is_symlink() for p in cible.parents if p.is_relative_to(racine)):
        raise ValueError('Un dossier de modèles ne doit pas être un lien symbolique.')
    cible.parent.mkdir(parents=True, exist_ok=True)
    fd, temporaire = tempfile.mkstemp(prefix='.modele-', suffix='.tmp', dir=cible.parent)
    try:
        with os.fdopen(fd, 'wb') as sortie:
            sortie.write(contenu)
            sortie.flush()
            os.fsync(sortie.fileno())
        os.replace(temporaire, cible)
    finally:
        Path(temporaire).unlink(missing_ok=True)
    return cible
