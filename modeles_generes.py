"""Propositions conservées et validation locale, distinctes des références douanières."""
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import xml.etree.ElementTree as ET
import moteur

BASE = Path(__file__).resolve().parent / 'DONNEES' / 'modeles_generes.db'
STATUTS = {'en_attente':'En attente', 'valide':'Validé localement', 'rejete':'Rejeté localement'}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS modeles (
 id INTEGER PRIMARY KEY, empreinte TEXT NOT NULL UNIQUE, cree_utc TEXT NOT NULL,
 auteur TEXT NOT NULL, importateur TEXT NOT NULL, nom TEXT NOT NULL,
 resultat_json TEXT NOT NULL, base_xml BLOB NOT NULL, modele_xml BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS evenements (
 id INTEGER PRIMARY KEY, modele_id INTEGER NOT NULL REFERENCES modeles(id),
 date_utc TEXT NOT NULL, auteur TEXT NOT NULL, action TEXT NOT NULL,
 statut TEXT CHECK(statut IN ('en_attente','valide','rejete')), detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS exports_xml (
 evenement_id INTEGER PRIMARY KEY REFERENCES evenements(id),
 sha256 TEXT NOT NULL, contenu BLOB NOT NULL);
CREATE TRIGGER IF NOT EXISTS exports_immuables BEFORE UPDATE ON exports_xml BEGIN SELECT RAISE(ABORT,'Export immuable'); END;
CREATE TRIGGER IF NOT EXISTS exports_conserves BEFORE DELETE ON exports_xml BEGIN SELECT RAISE(ABORT,'Export conservé'); END;
CREATE TRIGGER IF NOT EXISTS modeles_immuables BEFORE UPDATE ON modeles BEGIN SELECT RAISE(ABORT,'Snapshot immuable'); END;
CREATE TRIGGER IF NOT EXISTS modeles_conserves BEFORE DELETE ON modeles BEGIN SELECT RAISE(ABORT,'Snapshot conservé'); END;
CREATE TRIGGER IF NOT EXISTS evenements_immuables BEFORE UPDATE ON evenements BEGIN SELECT RAISE(ABORT,'Historique immuable'); END;
CREATE TRIGGER IF NOT EXISTS evenements_conserves BEFORE DELETE ON evenements BEGIN SELECT RAISE(ABORT,'Historique conservé'); END;
'''


@contextmanager
def _connexion(base=None):
    chemin = Path(base) if base is not None else BASE
    chemin.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(chemin, timeout=3)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA foreign_keys=ON')
        conn.executescript(SCHEMA)
        with conn:
            yield conn
    finally:
        conn.close()


def _maintenant():
    return datetime.now(timezone.utc).isoformat()


def _auteur(auteur):
    if not auteur or not auteur.strip():
        raise ValueError('Une session identifiée est nécessaire.')
    return auteur.strip()


def _evenement(conn, identifiant, auteur, action, statut=None, detail=''):
    curseur = conn.execute('INSERT INTO evenements(modele_id,date_utc,auteur,action,statut,detail) VALUES(?,?,?,?,?,?)',
                 (identifiant, _maintenant(), auteur, action, statut, detail))
    return curseur.lastrowid


def enregistrer(resultat, chemin_base, auteur, export=None, base=None):
    """Sauvegarde explicite ; un export du même contenu conserve son statut local."""
    auteur = _auteur(auteur)
    source = Path(chemin_base).read_bytes()
    arbre = ET.ElementTree(ET.fromstring(source))
    articles = resultat['resume']['articles']
    lignes = [(a['fob'], a['poids']) for a in articles]
    if len(lignes) != len(resultat['colis']):
        raise ValueError('Nombre de colis et articles incohérent.')
    # Reconstruit le snapshot sans écrire dans le fichier d'origine.
    resume = moteur.recalculer(arbre, lignes, resultat['colis'])
    for cle in ('poids', 'fob', 'cif', 'taxes_totales'):
        if Decimal(str(resume[cle])) != Decimal(str(resultat['resume'][cle])):
            raise ValueError("L'aperçu ne correspond plus à sa base. Vérifiez-le à nouveau avant de le conserver.")
    xml = ET.tostring(arbre.getroot(), encoding='utf-8', xml_declaration=True)
    normaliser = lambda v: str(Decimal(str(v)).normalize())
    contenu = {'base': hashlib.sha256(source).hexdigest(),
               'lignes': [[normaliser(f), normaliser(p), normaliser(c)]
                          for (f,p),c in zip(lignes,resultat['colis'])]}
    empreinte = hashlib.sha256(json.dumps(contenu, sort_keys=True).encode()).hexdigest()
    charge = json.dumps(resultat, ensure_ascii=False, sort_keys=True, allow_nan=False)
    with _connexion(base) as conn:
        existant = conn.execute('SELECT id FROM modeles WHERE empreinte=?', (empreinte,)).fetchone()
        if existant:
            identifiant = existant['id']
        else:
            curseur = conn.execute('INSERT INTO modeles(empreinte,cree_utc,auteur,importateur,nom,resultat_json,base_xml,modele_xml) VALUES(?,?,?,?,?,?,?,?)',
                (empreinte,_maintenant(),auteur,resultat['info'].get('importateur',''),resultat['nom'],charge,source,xml))
            identifiant = curseur.lastrowid
            _evenement(conn, identifiant, auteur, 'creation', 'en_attente')
        if export:
            chemin = str(Path(export).resolve())
            # Lecture de l'export existant : l'événement ne prétend pas créer le XML.
            contenu_export = Path(export).read_bytes()
            sha = hashlib.sha256(contenu_export).hexdigest()
            detail = json.dumps({'chemin':chemin,'sha256':sha},sort_keys=True)
            precedent = conn.execute("SELECT id FROM evenements WHERE modele_id=? AND action='export' AND detail=?", (identifiant,detail)).fetchone()
            evenement = precedent['id'] if precedent else _evenement(conn,identifiant,auteur,'export',detail=detail)
            conn.execute('INSERT OR IGNORE INTO exports_xml(evenement_id,sha256,contenu) VALUES(?,?,?)',
                         (evenement,sha,contenu_export))
    return identifiant


def lister(statut=None, base=None):
    if statut is not None and statut not in STATUTS:
        raise ValueError('Statut local inconnu.')
    with _connexion(base) as conn:
        lignes = conn.execute('''SELECT m.id,m.cree_utc,m.auteur,m.importateur,m.nom,m.resultat_json,
            (SELECT e.statut FROM evenements e WHERE e.modele_id=m.id AND e.statut IS NOT NULL ORDER BY e.id DESC LIMIT 1) statut,
            EXISTS(SELECT 1 FROM evenements e WHERE e.modele_id=m.id AND e.action='export') exporte,
            (SELECT e.date_utc FROM evenements e WHERE e.modele_id=m.id ORDER BY e.id DESC LIMIT 1) modifie_utc
            FROM modeles m ORDER BY m.id DESC''').fetchall()
    sortie = []
    for ligne in lignes:
        d = dict(ligne)
        if statut is None or d['statut'] == statut:
            d['resultat'] = json.loads(d.pop('resultat_json'))
            sortie.append(d)
    return sortie


def detail(identifiant, base=None):
    with _connexion(base) as conn:
        ligne = conn.execute('SELECT * FROM modeles WHERE id=?',(identifiant,)).fetchone()
        if ligne is None:
            raise ValueError('Modèle introuvable.')
        sortie = dict(ligne)
        sortie['resultat'] = json.loads(sortie.pop('resultat_json'))
        sortie['evenements'] = [dict(e) for e in conn.execute('SELECT * FROM evenements WHERE modele_id=? ORDER BY id',(identifiant,))]
        sortie['statut'] = next(e['statut'] for e in reversed(sortie['evenements']) if e['statut'])
        return sortie


def changer_statut(identifiant, statut, auteur, commentaire='', base=None):
    auteur = _auteur(auteur)
    if statut not in STATUTS:
        raise ValueError('Statut local inconnu.')
    if statut == 'rejete' and not commentaire.strip():
        raise ValueError('Indiquez le motif du rejet local.')
    with _connexion(base) as conn:
        if not conn.execute('SELECT 1 FROM modeles WHERE id=?',(identifiant,)).fetchone():
            raise ValueError('Modèle introuvable.')
        courant = conn.execute('SELECT statut FROM evenements WHERE modele_id=? AND statut IS NOT NULL ORDER BY id DESC LIMIT 1',(identifiant,)).fetchone()
        if courant['statut'] != statut:
            _evenement(conn,identifiant,auteur,'validation_locale',statut,commentaire.strip())


def lire_export(identifiant, base=None):
    """Dernier export réel ; anciens événements : fichier original et SHA exigés."""
    with _connexion(base) as conn:
        evenement = conn.execute("SELECT e.id,e.detail,x.sha256,x.contenu FROM evenements e LEFT JOIN exports_xml x ON x.evenement_id=e.id WHERE e.modele_id=? AND e.action='export' ORDER BY e.id DESC LIMIT 1", (identifiant,)).fetchone()
    if evenement is None:
        raise ValueError('Cette proposition n’a pas encore été exportée. Générez le XML avant de comparer.')
    if evenement['contenu'] is not None:
        contenu = bytes(evenement['contenu'])
        sha = evenement['sha256']
    else:
        details = json.loads(evenement['detail'])
        sha = details.get('sha256')
        try:
            contenu = Path(details['chemin']).read_bytes()
        except (KeyError,OSError):
            raise ValueError('Cet ancien export ne possède pas de copie archivée et son fichier est introuvable. La comparaison nécessite le XML exporté original.') from None
    if not sha or hashlib.sha256(contenu).hexdigest() != sha:
        raise ValueError('Le XML exporté a été modifié ou son empreinte est absente. Comparaison refusée.')
    return contenu


def nom_export(modele):
    """Nom portable ; aucune plaque ou identité ne peut introduire un chemin."""
    import re
    def nettoyer(valeur, defaut):
        texte = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '-', str(valeur or ''))
        return ' '.join(texte.split()).strip(' .-') or defaut
    plaque = nettoyer(modele['resultat'].get('info', {}).get('camion'), 'SANS-PLAQUE')[:80]
    nom = nettoyer(modele.get('nom'), f"Modele-{modele['id']}")
    if nom.lower().endswith('.xml'):
        nom = nom[:-4]
    return f'{plaque} - {nom}'[:210].rstrip(' .') + '.xml'


class ErreurSuiviExport(OSError):
    """Le fichier a été écrit, mais sa trace n'a pas pu être enregistrée."""


def exporter_xml(identifiant, destination, auteur, ecraser=False, base=None):
    """Télécharge un modèle validé, sans sa source et sans nouveau calcul fiscal."""
    import os
    import tempfile
    auteur = _auteur(auteur)
    destination = Path(destination).expanduser().resolve()
    if destination.suffix.lower() != '.xml':
        raise ValueError('Choisissez un fichier avec extension .xml.')
    if destination == Path(base if base is not None else BASE).resolve():
        raise ValueError('La base de données ne peut pas servir de destination XML.')
    modele = detail(identifiant, base=base)
    if modele['statut'] != 'valide':
        raise ValueError('Seul un modèle Validé localement peut être téléchargé en XML.')
    exporte = any(e['action'] == 'export' for e in modele['evenements'])
    contenu = lire_export(identifiant, base=base) if exporte else bytes(modele['modele_xml'])
    temporaire = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.asydec-', delete=False) as fichier:
            temporaire = Path(fichier.name)
            fichier.write(contenu)
            fichier.flush()
            os.fsync(fichier.fileno())
        if ecraser:
            os.replace(temporaire, destination)
        else:
            # Un lien créé exclusivement évite une course d'écrasement sur un fichier apparu entre-temps.
            os.link(temporaire, destination)
    finally:
        if temporaire is not None and temporaire.exists():
            temporaire.unlink()
    sha = hashlib.sha256(contenu).hexdigest()
    trace = json.dumps({'chemin': str(destination), 'sha256': sha}, sort_keys=True)
    try:
        with _connexion(base) as conn:
            evenement = _evenement(conn, identifiant, auteur, 'export', detail=trace)
            conn.execute('INSERT INTO exports_xml(evenement_id,sha256,contenu) VALUES(?,?,?)',
                         (evenement, sha, contenu))
    except Exception as exc:
        raise ErreurSuiviExport(f'Le XML a été enregistré dans {destination}, mais son suivi a échoué : {exc}') from exc
    return str(destination)
