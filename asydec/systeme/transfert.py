"""Transfert des données AsyDec vers une autre machine : un seul fichier « .asydec ».

Deux types d'export :
- complet : compte, numéros réservés, modèles, dossiers, licences, références… (nouvelle machine du même
  utilisateur) ; l'import remplace les données de la machine, qui sont d'abord mises de côté dans SAUVEGARDES ;
- kit : seulement les modèles (bibliothèque Word « Modèles de facture », XML de référence, médiathèque XML),
  sans compte, historique ni numéros (poste d'un collègue) ; l'import les ajoute à l'existant.

Les chemins absolus enregistrés dans les bases (« /Users/ancien/… ») sont réécrits pour la nouvelle machine.
L'import complet est préparé pendant que l'application tourne, puis appliqué au redémarrage, lorsque plus
aucune base n'est ouverte.
"""
from collections import Counter
from contextlib import closing
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import sqlite3
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from asydec import chemins
from asydec.systeme import modeles_documents

FORMAT = 2
EXTENSION = '.asydec'
TRAVAIL = 'ESPACE_TRAVAIL'
COMPLET = ('DONNEES', 'CONFIG_LOCAL', 'MODELES_XML', 'XML_LICENCES', 'ETUDES_XML', 'SIMULATIONS',
           'SAISIE.xlsx', 'registre.json', modeles_documents.DOSSIER, TRAVAIL)
SAUVEGARDES = 'SAUVEGARDES'
SAUVEGARDES_MANUELLES = 'DONNEES/sauvegardes_manuelles'
MEDIATHEQUE = 'MEDIATHEQUE'
MANIFESTE = 'manifest.json'
EN_ATTENTE = '.import_en_attente'
BASES = ('.db', '.sqlite')
TEMPORAIRES = ('.db-wal', '.db-shm', '.db-journal', '.sqlite-wal', '.sqlite-shm', '.sqlite-journal', '.tmp')
TAILLE_MAX = 4_000_000_000


def _ignore(p):
    nom = p.name
    return nom.endswith(TEMPORAIRES) or nom == '.DS_Store' or nom.startswith('asydec.log') or nom.startswith(EN_ATTENTE)


def _sha(chemin):
    h = hashlib.sha256()
    with open(chemin, 'rb') as f:
        for bloc in iter(lambda: f.read(1 << 20), b''):
            h.update(bloc)
    return h.hexdigest()


def _copier_base(source, cible):
    """Copie cohérente d'une base SQLite, même ouverte par l'application."""
    cible.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(Path(source).as_uri() + '?mode=ro', uri=True)) as entree, \
         closing(sqlite3.connect(cible)) as sortie:
        entree.backup(sortie)


def _copier(source, cible):
    source = Path(source)
    if source.is_symlink():
        raise ValueError(f'Lien symbolique refusé : {source}')
    cible.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix in BASES:
        _copier_base(source, cible)
    else:
        shutil.copy2(source, cible)


def _copier_element(racine, nom, cible, exclus=()):
    source = racine / nom
    if source.is_symlink():
        raise ValueError(f'« {nom} » est un lien symbolique ; transfert refusé.')
    if source.is_file():
        _copier(source, cible / nom)
    elif source.is_dir():
        for p in sorted(source.rglob('*')):
            relatif = p.relative_to(racine).as_posix()
            if any(relatif == e or relatif.startswith(e + '/') for e in exclus) or _ignore(p):
                continue
            if p.is_symlink():
                raise ValueError(f'Lien symbolique refusé : {relatif}')
            if p.is_file():
                _copier(p, cible / relatif)


def _archive_reelle(racine, archive, empreinte):
    p = Path(archive or '')
    if p.is_file():
        return p
    p = racine / 'DONNEES' / 'sources' / empreinte[:2] / f'{empreinte}.xml'
    return p if p.is_file() else None


def _mediatheque(racine_ou_dossier):
    """(fichier, module, nom) des XML de médiathèque utilisables (ni rejetés ni exclus)."""
    base = racine_ou_dossier / 'DONNEES' / 'asydec.db'
    if not base.is_file():
        return []
    sortie = []
    with closing(sqlite3.connect(base.as_uri() + '?mode=ro', uri=True)) as conn:
        try:
            lignes = conn.execute('SELECT d.sha256, d.archive, d.nom_initial, m.module FROM documents d '
                                  'JOIN xml_mediatheques m ON m.sha256 = d.sha256').fetchall()
            statuts = dict(conn.execute('SELECT document_id, statut FROM document_statuts').fetchall()) \
                if conn.execute("SELECT 1 FROM sqlite_master WHERE name='document_statuts'").fetchone() else {}
            ids = dict(conn.execute('SELECT sha256, id FROM documents').fetchall())
        except sqlite3.Error:
            return []
    for empreinte, archive, nom, module in lignes:
        if statuts.get(ids.get(empreinte)) in ('rejete', 'exclu'):
            continue
        fichier = _archive_reelle(racine_ou_dossier, archive, empreinte)
        if fichier:
            sortie.append((fichier, module, nom or f'{empreinte}.xml'))
    return sortie


# ---------------------------------------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------------------------------------

def _copier_modeles_documents(racine, cible):
    # Un ancien OUTILS peut contenir ses modèles dans ressources ; une application
    # compilée les livre ailleurs, dans CODE. Les copies personnelles ont priorité.
    code = chemins.CODE if racine.resolve() == chemins.RACINE.resolve() else racine
    for cle, (relatif, _) in modeles_documents.MODELES.items():
        source = modeles_documents.chemin(cle, racine=racine, code=code)
        if source.is_file():
            _copier(source, cible / modeles_documents.DOSSIER / relatif)


def _copier_dossier_travail(racine, cible, avec_sauvegardes=False):
    """Reprend les documents générés, même si le dossier de travail est hors d'AsyDec."""
    from asydec.systeme import espace_travail
    origine = None
    try:
        config = json.loads((racine / 'CONFIG_LOCAL/espace_travail.json').read_text(encoding='utf-8'))
        origine = config['racine']
        if not isinstance(origine, str) or not origine.strip():
            raise ValueError('Dossier de travail absent')
        dossier = Path(origine)
    except (OSError, ValueError, KeyError, TypeError):
        origine = None
        dossier = racine / TRAVAIL
    if not dossier.is_dir():
        dossier = racine / TRAVAIL
        if not dossier.is_dir():
            return None
    if dossier.is_symlink():
        raise ValueError('Le dossier de travail est un lien symbolique : transfert refusé.')
    for nom in espace_travail.DOSSIERS:
        if nom == espace_travail.TRANSFERTS or (nom == espace_travail.SAUVEGARDES and not avec_sauvegardes):
            continue
        _copier_element(dossier, nom, cible / TRAVAIL)
    if (dossier / 'LISEZMOI.txt').is_file():
        _copier(dossier / 'LISEZMOI.txt', cible / TRAVAIL / 'LISEZMOI.txt')
    return (origine or str(dossier)) if (cible / TRAVAIL).is_dir() else None

def exporter(destination, kit=False, avec_sauvegardes=False, racine=None):
    """Crée le fichier .asydec ; renvoie (chemin, résumé)."""
    racine = Path(racine) if racine is not None else chemins.RACINE
    destination = Path(destination)
    if destination.suffix != EXTENSION:
        destination = destination.with_name(destination.name + EXTENSION)
    if destination.resolve().is_relative_to(racine.resolve() / 'DONNEES'):
        raise ValueError('Enregistrez l’export hors du dossier des données (par exemple sur le Bureau ou une clé USB).')
    with tempfile.TemporaryDirectory(prefix='asydec-export-') as temp:
        temp = Path(temp)
        mediatheque = []
        dossier_travail = None
        if kit:
            if (racine / 'DONNEES/factures.db').is_file():
                cible = temp / 'DONNEES/factures.db'
                _copier_base(racine / 'DONNEES/factures.db', cible)
                with closing(sqlite3.connect(cible)) as db:
                    # Kit : modèles seulement, jamais les factures émises ni leurs numéros.
                    with db:
                        db.execute('DELETE FROM factures')
                        db.execute('DELETE FROM gabarits WHERE retire IS NOT NULL')
                        db.execute("DELETE FROM sqlite_sequence WHERE name='factures'")
                    db.execute('VACUUM')
            for nom in ('MODELES_XML', 'XML_LICENCES'):
                _copier_element(racine, nom, temp)
            for i, (fichier, module, nom) in enumerate(_mediatheque(racine)):
                relatif = f'{MEDIATHEQUE}/{module}/{_sha(fichier)}.xml'
                if not (temp / relatif).exists():
                    _copier(fichier, temp / relatif)
                mediatheque.append(dict(fichier=relatif, module=module, nom=nom))
        else:
            if not (racine / 'CONFIG_LOCAL/compte.json').is_file():
                raise ValueError('Aucun compte AsyDec dans ces données : rien à exporter.')
            exclus = () if avec_sauvegardes else (SAUVEGARDES_MANUELLES,)
            for nom in COMPLET + ((SAUVEGARDES,) if avec_sauvegardes else ()):
                if nom != TRAVAIL:
                    _copier_element(racine, nom, temp, exclus)
            dossier_travail = _copier_dossier_travail(racine, temp, avec_sauvegardes)
        _copier_modeles_documents(racine, temp)
        fichiers = {p.relative_to(temp).as_posix(): _sha(p) for p in sorted(temp.rglob('*')) if p.is_file()}
        from asydec.systeme.version import courante
        resume = _resume(temp, kit)
        manifeste = dict(format=FORMAT, type='kit' if kit else 'complet', cree_le=datetime.now().astimezone().isoformat(),
                         application=courante().get('version'), systeme=f'{platform.system()} {platform.machine()}',
                         # Le kit part chez une autre personne : aucun chemin de cette machine (nom d'utilisateur).
                         racine=None if kit else str(racine), avec_sauvegardes=bool(avec_sauvegardes and not kit),
                         espace_travail=dossier_travail,
                         resume=resume, mediatheque=mediatheque, fichiers=fichiers)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporaire = destination.with_name(destination.name + '.tmp')
        with ZipFile(temporaire, 'w', ZIP_DEFLATED, allowZip64=True) as z:
            z.writestr(MANIFESTE, json.dumps(manifeste, ensure_ascii=False, indent=1))
            for relatif in fichiers:
                z.write(temp / relatif, relatif)
        os.replace(temporaire, destination)
    return destination, resume


def _compter(base, requete):
    if not base.is_file():
        return 0
    try:
        with closing(sqlite3.connect(base.as_uri() + '?mode=ro', uri=True)) as db:
            return db.execute(requete).fetchone()[0]
    except sqlite3.Error:
        return 0


def _resume(dossier, kit):
    d = Path(dossier)
    resume = dict(
        modeles_word=_compter(d / 'DONNEES/factures.db', 'SELECT COUNT(*) FROM gabarits WHERE retire IS NULL'),
        modeles_documents=sum((d / modeles_documents.DOSSIER / relatif).is_file()
                             for relatif, _ in modeles_documents.MODELES.values()),
        xml_reference=len(list((d / 'MODELES_XML').glob('*.xml'))) if (d / 'MODELES_XML').is_dir() else 0,
        xml_licences=len(list((d / 'XML_LICENCES').glob('*.xml'))) if (d / 'XML_LICENCES').is_dir() else 0)
    if kit:
        resume['xml_mediatheque'] = len(list((d / MEDIATHEQUE).rglob('*.xml'))) if (d / MEDIATHEQUE).is_dir() else 0
    else:
        resume.update(
            documents_travail=sum(p.is_file() for p in (d / TRAVAIL).rglob('*')),
            dossiers_generes=_compter(d / 'DONNEES/modeles_generes.db', 'SELECT COUNT(*) FROM modeles'),
            factures_emises=_compter(d / 'DONNEES/factures.db', 'SELECT COUNT(*) FROM factures WHERE contenu IS NOT NULL'),
            numeros_reserves=_compter(d / 'CONFIG_LOCAL/numeros_factures.db', 'SELECT COUNT(*) FROM numeros'),
            xml_mediatheque=_compter(d / 'DONNEES/asydec.db', 'SELECT COUNT(*) FROM documents'),
            licences=_compter(d / 'DONNEES/licences_ouvertes.sqlite', 'SELECT COUNT(*) FROM licences'))
    return resume


LIBELLES = dict(modeles_word='modèles de facture Word', xml_reference='XML de référence', xml_licences='XML de licence',
                modeles_documents='modèles Word CVI/BL, déclaration et documents commerciaux',
                documents_travail='documents du dossier de travail',
                xml_mediatheque='XML de médiathèque', dossiers_generes='dossiers générés', factures_emises='factures émises',
                numeros_reserves='numéros réservés', licences='licences')


def archiver_import(source, dossier):
    """Copie datée d'un fichier .asydec importé dans dossier (7 - TRANSFERTS/2 - IMPORTS) ; renvoie la copie.
    Un ancien dossier OUTILS n'est pas copié (trop volumineux) : None."""
    source = Path(source)
    if dossier is None or not source.is_file():
        return None
    dossier = Path(dossier)
    if source.resolve().parent == dossier.resolve():
        return source  # déjà rangé ici
    dossier.mkdir(parents=True, exist_ok=True)
    nom = source.name if source.suffix == EXTENSION else source.name + EXTENSION
    cible, n = dossier / f'{datetime.now():%Y-%m-%d %Hh%M} - {nom}', 2
    while cible.exists():
        cible, n = dossier / f'{datetime.now():%Y-%m-%d %Hh%M} - {Path(nom).stem} ({n}){EXTENSION}', n + 1
    shutil.copy2(source, cible)
    return cible


def decrire(resume):
    return '\n'.join(f'• {v} {LIBELLES.get(k, k)}' for k, v in resume.items())


# ---------------------------------------------------------------------------------------------------------
# Lecture d'un export ou d'un ancien dossier
# ---------------------------------------------------------------------------------------------------------

AUTORISES = set(COMPLET) | {SAUVEGARDES, MEDIATHEQUE}


def lire(source):
    """Manifeste d'un export .asydec (contrôle de forme seulement)."""
    with ZipFile(source) as z:
        try:
            manifeste = json.loads(z.read(MANIFESTE))
        except KeyError:
            raise ValueError('Ce fichier n’est pas un export AsyDec.') from None
    if manifeste.get('format') not in (1, FORMAT) or manifeste.get('type') not in ('complet', 'kit'):
        raise ValueError('Format d’export AsyDec non pris en charge par cette version.')
    return manifeste


def _extraire(source, cible):
    manifeste = lire(source)
    attendus = manifeste.get('fichiers') or {}
    with ZipFile(source) as z:
        if sum(i.file_size for i in z.infolist()) > TAILLE_MAX:
            raise ValueError('Export trop volumineux.')
        for info in z.infolist():
            nom = info.filename
            chemin = PurePosixPath(nom)
            if nom == MANIFESTE or info.is_dir():
                continue
            if chemin.is_absolute() or '..' in chemin.parts or '\\' in nom or chemin.parts[0] not in AUTORISES:
                raise ValueError(f'Contenu refusé dans l’export : {nom}')
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f'Lien symbolique refusé dans l’export : {nom}')
            if nom not in attendus:
                raise ValueError(f'Fichier non déclaré dans l’export : {nom}')
            fichier = cible / nom
            fichier.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as entree, open(fichier, 'wb') as sortie:
                shutil.copyfileobj(entree, sortie)
    for nom, empreinte in attendus.items():
        if not (cible / nom).is_file() or _sha(cible / nom) != empreinte:
            raise ValueError(f'Export endommagé ou incomplet : {nom}. Refaites l’export.')
    return manifeste


def _charger(source, cible):
    """Export .asydec ou ancien dossier (OUTILS, Application Support/AsyDec) → copie autonome dans cible."""
    source = Path(source)
    if source.is_dir():
        if not (source / 'CONFIG_LOCAL/compte.json').is_file():
            raise ValueError('Ce dossier ne contient pas de données AsyDec (CONFIG_LOCAL/compte.json absent). '
                             'Sélectionnez l’ancien dossier OUTILS ou « Application Support/AsyDec ».')
        for nom in COMPLET:
            if nom != TRAVAIL:
                _copier_element(source, nom, cible)
        _copier_modeles_documents(source, cible)
        travail = _copier_dossier_travail(source, cible)
        return dict(format=FORMAT, type='complet', racine=str(source), espace_travail=travail,
                    resume=_resume(cible, False), mediatheque=[])
    return _extraire(source, cible)


def _verifier_bases(dossier):
    for p in dossier.rglob('*'):
        if p.is_file() and p.suffix in BASES:
            try:
                with closing(sqlite3.connect(p.as_uri() + '?mode=ro', uri=True)) as db:
                    if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise ValueError
            except (sqlite3.Error, ValueError):
                raise ValueError(f'Base endommagée dans l’export : {p.relative_to(dossier).as_posix()}') from None


# ---------------------------------------------------------------------------------------------------------
# Chemins de l'ancienne machine
# ---------------------------------------------------------------------------------------------------------

def _anciennes_racines(dossier, manifeste):
    racines = Counter()
    if manifeste.get('racine'):
        racines[manifeste['racine'].rstrip('/\\')] += 1
    base = dossier / 'DONNEES/asydec.db'
    if base.is_file():
        with closing(sqlite3.connect(base.as_uri() + '?mode=ro', uri=True)) as db:
            try:
                for (archive,) in db.execute('SELECT archive FROM documents'):
                    for marque in ('/DONNEES/sources/', '\\DONNEES\\sources\\'):
                        if archive and marque in archive:
                            racines[archive.split(marque)[0]] += 1
            except sqlite3.Error:
                pass
    return [r for r in racines if r]


def _reecrire_texte(valeur, paires):
    """Réécrit les valeurs JSON avant sérialisation : les antislashs Windows restent échappés."""
    if not isinstance(valeur, str) or not any(a in valeur or json.dumps(a)[1:-1] in valeur for a, _ in paires):
        return valeur

    def chaine(s):
        for ancienne, neuve in paires:
            if s.startswith(ancienne):
                return neuve + s[len(ancienne):].replace('\\', neuve[-1]).replace('/', neuve[-1])
            s = s.replace(ancienne, neuve)
        return s

    def convertir(objet):
        if isinstance(objet, str):
            return chaine(objet)
        if isinstance(objet, list):
            return [convertir(v) for v in objet]
        if isinstance(objet, dict):
            return {chaine(k): convertir(v) for k, v in objet.items()}
        return objet

    try:
        original = json.loads(valeur)
    except ValueError:
        return chaine(valeur)
    modifie = convertir(original)
    return json.dumps(modifie, ensure_ascii=False) if modifie != original else valeur


def _reecrire_chemins(dossier, anciennes, nouvelle, correspondances=None):
    """Remplace les débuts de chemins de l'ancienne machine dans les bases et fichiers JSON."""
    nouvelle = str(nouvelle).rstrip('/\\')
    paires = []
    racines = {variante for r in anciennes for variante in (r, r.replace('\\', '/'), r.replace('/', '\\'))}
    for ancienne in sorted(racines, key=len, reverse=True):
        if ancienne == nouvelle:
            continue
        for sep in ('/', '\\'):
            paires.append((ancienne + sep, nouvelle + os.sep))
    for origine, cible in (correspondances or {}).items():
        for ancienne in {origine, origine.replace('\\', '/'), origine.replace('/', '\\')}:
            for sep in ('/', '\\'):
                paires.append((ancienne.rstrip('/\\') + sep, str(cible).rstrip('/\\') + os.sep))
    paires.sort(key=lambda paire: len(paire[0]), reverse=True)
    if not paires:
        return 0
    modifies = 0
    for p in dossier.rglob('*'):
        if not p.is_file():
            continue
        if p.suffix in BASES:
            with closing(sqlite3.connect(p)) as db:
                db.create_function('asydec_reecrire', 1, lambda v: _reecrire_texte(v, paires))
                tables = [t for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                                   "AND name NOT LIKE 'sqlite_%'")]
                with db:
                    for table in tables:
                        table_sql = '"' + table.replace('"', '""') + '"'
                        colonnes = [c[1] for c in db.execute(f'PRAGMA table_info({table_sql})')
                                    if 'BLOB' not in (c[2] or '').upper()]
                        for colonne in colonnes:
                            c = '"' + colonne.replace('"', '""') + '"'
                            modifies += db.execute(
                                f'UPDATE {table_sql} SET {c}=asydec_reecrire({c}) '
                                f'WHERE typeof({c})=\'text\' AND CAST({c} AS BLOB) != '
                                f'CAST(asydec_reecrire({c}) AS BLOB)').rowcount
        elif p.suffix == '.json':
            try:
                texte = p.read_text(encoding='utf-8')
            except UnicodeError:
                continue  # conserver les comptes illisibles pour la récupération au login
            origine = texte
            texte = _reecrire_texte(texte, paires)
            if texte != origine:
                p.write_text(texte, encoding='utf-8')
                modifies += 1
    # Dossier de travail de l'ancienne machine introuvable ici : AsyDec en demandera un au démarrage.
    espace = dossier / 'CONFIG_LOCAL/espace_travail.json'
    if espace.is_file():
        try:
            racine_travail = json.loads(espace.read_text(encoding='utf-8')).get('racine')
        except ValueError:
            racine_travail = None
        if not racine_travail or not Path(racine_travail).is_dir():
            espace.unlink()
    return modifies


# ---------------------------------------------------------------------------------------------------------
# Import complet : préparé maintenant, appliqué au prochain démarrage
# ---------------------------------------------------------------------------------------------------------

def preparer_import_complet(source, racine=None):
    """Vérifie l'export (ou l'ancien dossier) et le prépare pour le prochain démarrage ; renvoie le manifeste."""
    racine = Path(racine) if racine is not None else chemins.RACINE
    racine.mkdir(parents=True, exist_ok=True)
    annuler_en_attente(racine)
    temporaire = Path(tempfile.mkdtemp(prefix=EN_ATTENTE + '-', dir=racine))
    try:
        manifeste = _charger(source, temporaire)
        if manifeste['type'] != 'complet':
            raise ValueError('Ce fichier est un kit de modèles : utilisez « Importer des modèles ».')
        if not (temporaire / 'CONFIG_LOCAL/compte.json').is_file():
            raise ValueError('Cet export ne contient pas de compte AsyDec.')
        _verifier_bases(temporaire)
        correspondances = {}
        if (temporaire / TRAVAIL).is_dir() and manifeste.get('espace_travail'):
            correspondances[manifeste['espace_travail']] = racine / TRAVAIL
        _reecrire_chemins(temporaire, _anciennes_racines(temporaire, manifeste), racine, correspondances)
        if (temporaire / TRAVAIL).is_dir():
            config = temporaire / 'CONFIG_LOCAL/espace_travail.json'
            config.write_text(json.dumps({'racine': str(racine / TRAVAIL)}, ensure_ascii=False), encoding='utf-8')
        (temporaire / 'attente.json').write_text(json.dumps(dict(
            source=str(source), prepare_le=datetime.now().astimezone().isoformat(),
            cree_le=manifeste.get('cree_le'), resume=manifeste.get('resume', {})), ensure_ascii=False), encoding='utf-8')
        os.replace(temporaire, racine / EN_ATTENTE)
    except BaseException:
        shutil.rmtree(temporaire, ignore_errors=True)
        raise
    return manifeste


def en_attente(racine=None):
    racine = Path(racine) if racine is not None else chemins.RACINE
    fichier = racine / EN_ATTENTE / 'attente.json'
    try:
        return json.loads(fichier.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def annuler_en_attente(racine=None):
    racine = Path(racine) if racine is not None else chemins.RACINE
    if (racine / EN_ATTENTE).exists():
        shutil.rmtree(racine / EN_ATTENTE)


def appliquer_en_attente(racine=None):
    """À appeler au démarrage, aucune base ouverte. Met les données actuelles de côté puis installe l'import.
    Renvoie le dossier de mise de côté (None si rien n'était en attente)."""
    racine = Path(racine) if racine is not None else chemins.RACINE
    attente = racine / EN_ATTENTE
    if not (attente / 'attente.json').is_file():
        return None
    from asydec.systeme import journal
    actifs = [h for h in journal.journal.handlers if hasattr(h, 'baseFilename')]
    for h in actifs:  # libère DONNEES/asydec.log (indispensable sous Windows)
        journal.journal.removeHandler(h)
        h.close()
    date = datetime.now().strftime('%Y%m%d-%H%M%S')
    mise_de_cote = racine / SAUVEGARDES / f'avant-import-{date}'
    mise_de_cote.mkdir(parents=True, exist_ok=True)
    deplaces, installes = [], []
    elements = [nom for nom in COMPLET if nom not in (modeles_documents.DOSSIER, TRAVAIL) or (attente / nom).exists()]
    try:
        for nom in elements:
            if (racine / nom).exists():
                os.replace(racine / nom, mise_de_cote / nom)
                deplaces.append(nom)
        for nom in elements:
            if (attente / nom).exists():
                os.replace(attente / nom, racine / nom)
                installes.append(nom)
        if (attente / SAUVEGARDES).exists():
            os.replace(attente / SAUVEGARDES, racine / SAUVEGARDES / f'importees-{date}')
        (mise_de_cote / 'manifest.json').write_text(json.dumps(dict(
            raison='Données remplacées par un import', import_=json.loads((attente / 'attente.json').read_text('utf-8')),
            elements=deplaces), ensure_ascii=False, indent=1), encoding='utf-8')
    except Exception:
        for nom in reversed(installes):
            os.replace(racine / nom, attente / nom)
        for nom in reversed(deplaces):
            os.replace(mise_de_cote / nom, racine / nom)
        raise
    finally:
        if actifs:
            journal.activer()
    shutil.rmtree(attente, ignore_errors=True)
    return mise_de_cote


# ---------------------------------------------------------------------------------------------------------
# Import des modèles (kit, ou modèles d'un export complet) : ajout sans rien remplacer
# ---------------------------------------------------------------------------------------------------------

def importer_modeles(source, racine=None, conn_references=None):
    """Ajoute les modèles Word, XML de référence et XML de médiathèque absents ; renvoie les compteurs."""
    racine = Path(racine) if racine is not None else chemins.RACINE
    with tempfile.TemporaryDirectory(prefix='asydec-kit-') as temp:
        temp = Path(temp)
        manifeste = _charger(source, temp)
        _verifier_bases(temp)
        bilan = dict(modeles_word=0, modeles_documents=0, xml_reference=0, xml_licences=0, xml_mediatheque=0, deja_presents=0)
        for cle, (relatif, _) in modeles_documents.MODELES.items():
            fichier = temp / modeles_documents.DOSSIER / relatif
            if not fichier.is_file():
                continue
            cible = racine / modeles_documents.DOSSIER / relatif
            if cible.exists():
                bilan['deja_presents'] += 1
                continue
            modeles_documents.enregistrer(cle, fichier, racine=racine)
            bilan['modeles_documents'] += 1
        # 1. Bibliothèque « Modèles de facture »
        source_db = temp / 'DONNEES/factures.db'
        if source_db.is_file():
            from asydec.declarations import factures
            with closing(sqlite3.connect(source_db)) as src:
                src.row_factory = sqlite3.Row
                gabarits = src.execute('SELECT nom,contenu,articles_json,prix_base FROM gabarits '
                                       'WHERE retire IS NULL ORDER BY id').fetchall()
            with factures.connexion(racine / 'DONNEES/factures.db') as db:
                for g in gabarits:
                    existant = db.execute('SELECT id FROM gabarits WHERE contenu=?', (g['contenu'],)).fetchone()
                    if existant:
                        bilan['deja_presents'] += 1
                        continue
                    db.execute('INSERT INTO gabarits(nom,contenu,articles_json,prix_base) VALUES(?,?,?,?)',
                               (g['nom'], g['contenu'], g['articles_json'], g['prix_base']))
                    bilan['modeles_word'] += 1
        # 2. Dossiers de XML de référence
        for nom, cle in (('MODELES_XML', 'xml_reference'), ('XML_LICENCES', 'xml_licences')):
            dossier = temp / nom
            if not dossier.is_dir():
                continue
            cible = racine / nom
            cible.mkdir(parents=True, exist_ok=True)
            presents = {_sha(p) for p in cible.glob('*.xml')}
            for p in sorted(dossier.glob('*.xml')):
                empreinte = _sha(p)
                if empreinte in presents:
                    bilan['deja_presents'] += 1
                    continue
                arrivee, n = cible / p.name, 2
                while arrivee.exists():
                    arrivee, n = cible / f'{p.stem} ({n}){p.suffix}', n + 1
                shutil.copy2(p, arrivee)
                presents.add(empreinte)
                bilan[cle] += 1
        # 3. Médiathèque XML (Friperie / Divers)
        if manifeste.get('type') == 'kit':
            elements = [(temp / m['fichier'], m['module'], m['nom']) for m in manifeste.get('mediatheque', [])]
        else:
            elements = _mediatheque(temp)
        if elements:
            from asydec.references import base_references, catalogue_xml
            conn = conn_references or base_references.ouvrir(racine / 'DONNEES/asydec.db')
            try:
                deja = {e for (e,) in conn.execute('SELECT sha256 FROM xml_mediatheques')}
                with tempfile.TemporaryDirectory(prefix='asydec-xml-') as noms:
                    for fichier, module, nom in elements:
                        if _sha(fichier) in deja:
                            bilan['deja_presents'] += 1
                            continue
                        lisible = Path(noms) / module / Path(nom).name
                        lisible.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(fichier, lisible)  # le nom d'origine reste visible dans la médiathèque
                        ajoutes, erreurs = catalogue_xml.partager(conn, [lisible], module)
                        bilan['xml_mediatheque'] += len(ajoutes)
            finally:
                if conn_references is None:
                    conn.close()
    return bilan
