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
    conn.execute('INSERT INTO evenements(modele_id,date_utc,auteur,action,statut,detail) VALUES(?,?,?,?,?,?)',
                 (identifiant, _maintenant(), auteur, action, statut, detail))


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
            detail = json.dumps({'chemin':chemin,'sha256':hashlib.sha256(Path(export).read_bytes()).hexdigest()},sort_keys=True)
            if not conn.execute("SELECT 1 FROM evenements WHERE modele_id=? AND action='export' AND detail=?", (identifiant,detail)).fetchone():
                _evenement(conn,identifiant,auteur,'export',detail=detail)
    return identifiant


def lister(statut=None, base=None):
    if statut is not None and statut not in STATUTS:
        raise ValueError('Statut local inconnu.')
    with _connexion(base) as conn:
        lignes = conn.execute('''SELECT m.id,m.cree_utc,m.auteur,m.importateur,m.nom,m.resultat_json,
            (SELECT e.statut FROM evenements e WHERE e.modele_id=m.id AND e.statut IS NOT NULL ORDER BY e.id DESC LIMIT 1) statut,
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
