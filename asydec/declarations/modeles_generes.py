"""Propositions conservées et validation locale, distinctes des références douanières.

Chaque modèle est un instantané immuable (table « modeles »). Tout ce qui lui arrive ensuite
(validation, export, plaque, comparaison, coche, suppression) est un événement ajouté à
l'historique, jamais modifié ni effacé. L'état courant se lit donc dans le dernier événement
de chaque type.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import xml.etree.ElementTree as ET

from asydec import chemins
from asydec.systeme import espace_travail
from asydec.calcul import moteur
from asydec.calcul import variantes
from asydec.declarations import comparaison_prediction
from asydec.references.import_references import extraire

BASE = chemins.DONNEES / 'modeles_generes.db'
STATUTS = {'en_attente': 'En attente', 'valide': 'Validé localement', 'rejete': 'Rejeté localement'}

# Types d'événements de l'historique.
CREATION, VALIDATION, EXPORT = 'creation', 'validation_locale', 'export'
PLAQUE, COMPARAISON = 'plaque', 'comparaison'
SUPPRESSION, RESTAURATION = 'suppression', 'restauration'
BON_MODELE, RETRAIT_BON_MODELE = 'bon_modele', 'retrait_bon_modele'
NOTE = 'note'

# Note donnée par l'utilisateur sur ce qu'il voit du modèle ; 4 et plus = exemple à suivre,
# 2 et moins = à éviter (voir bons_modeles et calcul.anomalies).
NOTES = {5: 'Excellent', 4: 'Bon', 3: 'Acceptable', 2: 'Douteux', 1: 'Mauvais'}
NOTE_BONNE, NOTE_MAUVAISE = 4, 2

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
CREATE TABLE IF NOT EXISTS signalements_references (
 id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL, nom TEXT NOT NULL, date_utc TEXT NOT NULL,
 auteur TEXT NOT NULL, utilise INTEGER NOT NULL CHECK(utilise IN (0,1)));
CREATE TRIGGER IF NOT EXISTS signalements_immuables BEFORE UPDATE ON signalements_references BEGIN SELECT RAISE(ABORT,'Historique immuable'); END;
CREATE TRIGGER IF NOT EXISTS signalements_conserves BEFORE DELETE ON signalements_references BEGIN SELECT RAISE(ABORT,'Historique conservé'); END;
CREATE TABLE IF NOT EXISTS declarations_reelles (
 id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL UNIQUE, chemin TEXT NOT NULL, nom TEXT NOT NULL,
 module TEXT NOT NULL, date_utc TEXT NOT NULL, auteur TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS declarations_reelles_immuables BEFORE UPDATE ON declarations_reelles BEGIN SELECT RAISE(ABORT,'Historique immuable'); END;
CREATE TRIGGER IF NOT EXISTS declarations_reelles_conservees BEFORE DELETE ON declarations_reelles BEGIN SELECT RAISE(ABORT,'Historique conservé'); END;
'''


# =============================================================================
# Connexion, auteur et historique
# =============================================================================
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


def _sha(octets):
    return hashlib.sha256(octets).hexdigest()


def _evenement(conn, identifiant, auteur, action, statut=None, detail=''):
    curseur = conn.execute(
        'INSERT INTO evenements(modele_id,date_utc,auteur,action,statut,detail) VALUES(?,?,?,?,?,?)',
        (identifiant, _maintenant(), auteur, action, statut, detail))
    return curseur.lastrowid


def _exiger_modele(conn, identifiant):
    if not conn.execute('SELECT 1 FROM modeles WHERE id=?', (identifiant,)).fetchone():
        raise ValueError('Modèle introuvable.')


def _statut_courant(conn, identifiant):
    ligne = conn.execute('SELECT statut FROM evenements WHERE modele_id=? AND statut IS NOT NULL '
                         'ORDER BY id DESC LIMIT 1', (identifiant,)).fetchone()
    return ligne['statut'] if ligne else None


def _dernier(evenements, *actions):
    """Dernier événement parmi ces actions, ou None."""
    return next((e for e in reversed(evenements) if e['action'] in actions), None)


def _bascule_active(evenements, active, inactive):
    """État d'une bascule (suppression, coche) : vrai si sa dernière action est « active »."""
    dernier = _dernier(evenements, active, inactive)
    return dernier is not None and dernier['action'] == active


def _basculer(identifiant, auteur, active, inactive, activer, detail, base):
    """Ajoute l'action de bascule seulement si l'état change (aucun doublon d'historique)."""
    auteur = _auteur(auteur)
    with _connexion(base) as conn:
        _exiger_modele(conn, identifiant)
        evenements = [dict(e) for e in conn.execute(
            'SELECT action FROM evenements WHERE modele_id=? ORDER BY id', (identifiant,))]
        if _bascule_active(evenements, active, inactive) != activer:
            _evenement(conn, identifiant, auteur, active if activer else inactive, detail=detail)


# =============================================================================
# Instantanés : enregistrer, lister, consulter
# =============================================================================
def _empreinte(source, lignes, colis, plaque, importateur=None, taux=None):
    """Identité d'une proposition : base, répartition, plaque, importateur et taux choisis (absents des anciennes empreintes)."""
    normaliser = lambda v: str(Decimal(str(v)).normalize())
    contenu = {'base': _sha(source),
               'lignes': [[normaliser(f), normaliser(p), normaliser(c)] for (f, p), c in zip(lignes, colis)]}
    if plaque:
        contenu['plaque'] = moteur.normaliser_plaque(plaque)
    if importateur:
        contenu['importateur'] = importateur['code']
    if taux:
        contenu['taux'] = str(Decimal(str(taux)).normalize())
    return _sha(json.dumps(contenu, sort_keys=True).encode())


def _snapshot(source, resultat, lignes):
    """XML du modèle recalculé depuis la base, sans écrire dans le fichier d'origine."""
    arbre = ET.ElementTree(ET.fromstring(source))
    if resultat.get('taux_choisi'):
        moteur.ecrire_taux(arbre.getroot(), resultat['taux_choisi'])
    resume = moteur.recalculer(arbre, lignes, resultat['colis'], taux_globales=resultat.get('taux_globales'))
    if resultat.get('plaque'):
        moteur.ecrire_plaque(arbre.getroot(), resultat['plaque'])
    if resultat.get('importateur_choisi'):
        moteur.ecrire_importateur(arbre.getroot(), resultat['importateur_choisi']['code'], resultat['importateur_choisi']['bloc'])
    for cle in ('poids', 'fob', 'cif', 'taxes_totales'):
        if Decimal(str(resume[cle])) != Decimal(str(resultat['resume'][cle])):
            raise ValueError("L'aperçu ne correspond plus à sa base. Vérifiez-le à nouveau avant de le conserver.")
    return ET.tostring(arbre.getroot(), encoding='utf-8', xml_declaration=True)


def _rattacher_export(conn, identifiant, auteur, export):
    """Relie un export existant au modèle (lecture seule du fichier), sans doublon."""
    contenu = Path(export).read_bytes()
    sha = _sha(contenu)
    detail = json.dumps({'chemin': str(Path(export).resolve()), 'sha256': sha}, sort_keys=True)
    precedent = conn.execute("SELECT id FROM evenements WHERE modele_id=? AND action=? AND detail=?",
                             (identifiant, EXPORT, detail)).fetchone()
    evenement = precedent['id'] if precedent else _evenement(conn, identifiant, auteur, EXPORT, detail=detail)
    conn.execute('INSERT OR IGNORE INTO exports_xml(evenement_id,sha256,contenu) VALUES(?,?,?)',
                 (evenement, sha, contenu))


def enregistrer(resultat, chemin_base, auteur, export=None, base=None, reference=None, module=None):
    """Sauvegarde explicite ; un export du même contenu conserve son statut local.

    reference : XML de référence des ratios, mémorisé pour signaler les modèles déjà utilisés.
    """
    auteur = _auteur(auteur)
    module = module or resultat.get('module', 'friperie')
    if module not in ('friperie', 'divers'):
        raise ValueError('Type de dossier inconnu.')
    resultat = {**resultat, 'module':module}
    source = Path(chemin_base).read_bytes()
    if reference:
        resultat = {**resultat, 'reference': {'nom': Path(reference).name, 'sha256': empreinte_fichier(reference)}}
    lignes = [(a['fob'], a['poids']) for a in resultat['resume']['articles']]
    if len(lignes) != len(resultat['colis']):
        raise ValueError('Nombre de colis et articles incohérent.')
    xml = _snapshot(source, resultat, lignes)
    empreinte = _empreinte(source, lignes, resultat['colis'], resultat.get('plaque'), resultat.get('importateur_choisi'),
                          resultat.get('taux_choisi'))
    if module != 'friperie':
        empreinte = _sha((empreinte + ':' + module).encode())
    charge = json.dumps(resultat, ensure_ascii=False, sort_keys=True, allow_nan=False)
    with _connexion(base) as conn:
        existant = conn.execute('SELECT id FROM modeles WHERE empreinte=?', (empreinte,)).fetchone()
        if existant:
            identifiant = existant['id']
        else:
            curseur = conn.execute(
                'INSERT INTO modeles(empreinte,cree_utc,auteur,importateur,nom,resultat_json,base_xml,modele_xml) '
                'VALUES(?,?,?,?,?,?,?,?)',
                (empreinte, _maintenant(), auteur, resultat['info'].get('importateur', ''), resultat['nom'],
                 charge, source, xml))
            identifiant = curseur.lastrowid
            _evenement(conn, identifiant, auteur, CREATION, 'en_attente')
        if export:
            _rattacher_export(conn, identifiant, auteur, export)
    return identifiant


def _derniere(action, colonne='detail'):
    return (f"(SELECT e.{colonne} FROM evenements e WHERE e.modele_id=m.id AND e.action='{action}' "
            f"ORDER BY e.id DESC LIMIT 1)")


def _bascule_sql(active, inactive):
    return (f"COALESCE((SELECT e.action='{active}' FROM evenements e WHERE e.modele_id=m.id "
            f"AND e.action IN ('{active}','{inactive}') ORDER BY e.id DESC LIMIT 1),0)")


LISTE_SQL = f'''SELECT m.id, m.cree_utc, m.auteur, m.importateur, m.nom, m.resultat_json,
    (SELECT e.statut FROM evenements e WHERE e.modele_id=m.id AND e.statut IS NOT NULL
     ORDER BY e.id DESC LIMIT 1) statut,
    EXISTS(SELECT 1 FROM evenements e WHERE e.modele_id=m.id AND e.action='{EXPORT}') exporte,
    (SELECT e.date_utc FROM evenements e WHERE e.modele_id=m.id ORDER BY e.id DESC LIMIT 1) modifie_utc,
    {_derniere(PLAQUE)} plaque_saisie,
    (SELECT COUNT(*) FROM evenements e WHERE e.modele_id=m.id AND e.action='{COMPARAISON}') comparaisons,
    {_bascule_sql(BON_MODELE, RETRAIT_BON_MODELE)} bon,
    {_derniere(EXPORT)} export_detail,
    {_bascule_sql(SUPPRESSION, RESTAURATION)} supprime,
    {_derniere(COMPARAISON, 'date_utc')} compare_utc,
    {_derniere(COMPARAISON)} compare_detail,
    {_derniere(NOTE)} note_detail
    FROM modeles m ORDER BY m.id DESC'''


def _plaque_affichee(saisie, resultat):
    return saisie or resultat.get('info', {}).get('camion') or ''


def lister(statut=None, base=None, supprimes=False, module=None):
    """supprimes : False masque les modèles retirés, True ne montre qu'eux."""
    if module is not None and module not in ('friperie', 'divers'):
        raise ValueError('Type de dossier inconnu.')
    if statut is not None and statut not in STATUTS:
        raise ValueError('Statut local inconnu.')
    with _connexion(base) as conn:
        lignes = conn.execute(LISTE_SQL).fetchall()
    sortie = []
    for ligne in lignes:
        d = dict(ligne)
        if (statut is not None and d['statut'] != statut) or bool(d['supprime']) != supprimes:
            continue
        d['resultat'] = json.loads(d.pop('resultat_json'))
        if module is not None and d['resultat'].get('module', 'friperie') != module:
            continue
        d['plaque'] = _plaque_affichee(d.pop('plaque_saisie'), d['resultat'])
        d['chemin_xml'] = _chemin_export(d.pop('export_detail'))
        d['dernier_ecart'] = _dernier_ecart(d.pop('compare_detail'))
        d.update(_note(d.pop('note_detail')))
        sortie.append(d)
    return sortie


def detail(identifiant, base=None):
    with _connexion(base) as conn:
        ligne = conn.execute('SELECT * FROM modeles WHERE id=?', (identifiant,)).fetchone()
        if ligne is None:
            raise ValueError('Modèle introuvable.')
        sortie = dict(ligne)
        evenements = [dict(e) for e in conn.execute(
            'SELECT * FROM evenements WHERE modele_id=? ORDER BY id', (identifiant,))]
    sortie['resultat'] = json.loads(sortie.pop('resultat_json'))
    sortie['evenements'] = evenements
    sortie['statut'] = next(e['statut'] for e in reversed(evenements) if e['statut'])
    sortie['supprime'] = _bascule_active(evenements, SUPPRESSION, RESTAURATION)
    sortie['bon'] = _bascule_active(evenements, BON_MODELE, RETRAIT_BON_MODELE)
    saisie = _dernier(evenements, PLAQUE)
    sortie['plaque'] = _plaque_affichee(saisie and saisie['detail'], sortie['resultat'])
    note = _dernier(evenements, NOTE)
    sortie.update(_note(note and note['detail']))
    return sortie


def resume_evenement(e):
    """Libellé lisible d'un événement d'historique."""
    action, detail_ = e['action'], e['detail']
    if action in ('correction_dossier', 'version_corrigee'):
        infos = json.loads(detail_)
        return (f"Correction du modèle n° {infos['modele_initial']} → n° {infos['modele_corrige']}"
                f" · {infos['motif']}")
    if action in (BON_MODELE, RETRAIT_BON_MODELE):
        return 'Coché bon modèle ★' if action == BON_MODELE else 'Coche bon modèle retirée'
    if action in (SUPPRESSION, RESTAURATION):
        libelle = 'Supprimé de la liste' if action == SUPPRESSION else 'Restauré dans la liste'
        return f'{libelle} · {detail_}' if detail_ else libelle
    if action == NOTE:
        n = _note(detail_)
        libelle = f"Noté {n['note']}/5 ({NOTES[n['note']]})"
        return f"{libelle} · {n['note_commentaire']}" if n['note_commentaire'] else libelle
    if action == PLAQUE:
        return f'Plaque : {detail_}'
    if action == COMPARAISON:
        infos = json.loads(detail_)
        ecart = infos.get('ecart_total')
        return f"Comparé avec {Path(infos['fichier']).name}" + (
            f' · écart total déclaration {ecart} CDF' if ecart is not None else '')
    if action == EXPORT:
        chemin = _chemin_export(detail_)
        if chemin:
            return f'XML exporté : {Path(chemin).name}'
    libelle = STATUTS.get(e['statut'], action)
    return f'{libelle} · {detail_}' if detail_ else libelle


# =============================================================================
# Validation locale, suppression, coche « bon modèle »
# =============================================================================
def changer_statut(identifiant, statut, auteur, commentaire='', base=None):
    auteur = _auteur(auteur)
    if statut not in STATUTS:
        raise ValueError('Statut local inconnu.')
    if statut == 'rejete' and not commentaire.strip():
        raise ValueError('Indiquez le motif du rejet local.')
    with _connexion(base) as conn:
        _exiger_modele(conn, identifiant)
        if _statut_courant(conn, identifiant) != statut:
            _evenement(conn, identifiant, auteur, VALIDATION, statut, commentaire.strip())


def supprimer(identifiant, auteur, motif='', base=None):
    """Retire le modèle de la liste. Rien n'est effacé : snapshot, exports et historique restent (restauration possible)."""
    _basculer(identifiant, auteur, SUPPRESSION, RESTAURATION, True, (motif or '').strip(), base)


def restaurer(identifiant, auteur, base=None):
    _basculer(identifiant, auteur, SUPPRESSION, RESTAURATION, False, '', base)


def marquer_bon(identifiant, auteur, bon=True, base=None):
    """Coche « bon modèle » : sert seulement à orienter les prochaines répartitions, sans valeur de validation."""
    _basculer(identifiant, auteur, BON_MODELE, RETRAIT_BON_MODELE, bon, '', base)


def _note(detail_):
    """{'note': 1..5 ou None, 'note_commentaire': texte} depuis le détail d'un événement de note."""
    try:
        infos = json.loads(detail_) if detail_ else {}
        return {'note': int(infos['note']), 'note_commentaire': infos.get('commentaire', '')}
    except (ValueError, KeyError, TypeError):
        return {'note': None, 'note_commentaire': ''}


def noter(identifiant, note, auteur, commentaire='', base=None):
    """Note de 1 à 5 donnée sur ce que l'utilisateur voit du modèle, avec un commentaire facultatif.
    Chaque note est ajoutée à l'historique ; la dernière fait foi."""
    auteur = _auteur(auteur)
    if isinstance(note, bool) or note not in NOTES:
        raise ValueError('Choisissez une note de 1 (mauvais) à 5 (excellent).')
    commentaire = ' '.join(str(commentaire or '').split())[:300]
    with _connexion(base) as conn:
        _exiger_modele(conn, identifiant)
        evenements = [dict(e) for e in conn.execute(
            'SELECT action FROM evenements WHERE modele_id=? ORDER BY id', (identifiant,))]
        if _bascule_active(evenements, SUPPRESSION, RESTAURATION):
            raise ValueError('Restaurez le modèle avant de le noter.')
        _evenement(conn, identifiant, auteur, NOTE,
                   detail=json.dumps({'note': note, 'commentaire': commentaire}, ensure_ascii=False))
    return note


def _repartition(m):
    r = m['resultat']
    return {'id': m['id'], 'poids': [a['poids'] for a in r['resume']['articles']],
            'fob': list(r['fob']), 'colis': list(r['colis'])}


def bons_modeles(signature, base=None, module=None):
    """Répartitions des modèles cochés ★ ou bien notés (4 ou 5), non supprimés, dont les articles sont
    ceux de cette signature."""
    return [_repartition(m) for m in lister(base=base, module=module)
            if (m['bon'] or (m['note'] or 0) >= NOTE_BONNE) and _signature_modele(m['id'], base) == signature]


def modeles_a_eviter(signature, base=None, module=None):
    """Répartitions des modèles rejetés localement ou notés 1-2, aux articles de cette signature."""
    return [_repartition(m) for m in lister(base=base, module=module)
            if (m['statut'] == 'rejete' or (m['note'] is not None and m['note'] <= NOTE_MAUVAISE))
            and _signature_modele(m['id'], base) == signature]


def declarations_comparees(base=None, module=None):
    """XML réels qui ont servi à comparer un modèle (non supprimé) du module, encore présents et intacts :
    [{'chemin', 'nom', 'sha256', 'modele', 'date_utc'}], un par contenu, le plus récent d'abord.
    Ce sont des déclarations SYDONIA effectives : les références les plus sûres pour générer."""
    gardes = {m['id'] for m in lister(base=base, module=module)}
    with _connexion(base) as conn:
        traces = conn.execute('SELECT modele_id, date_utc, detail FROM evenements WHERE action=? ORDER BY id DESC',
                              (COMPARAISON,)).fetchall()
    sortie, vus = [], set()
    for t in traces:
        if t['modele_id'] not in gardes:
            continue
        try:
            infos = json.loads(t['detail'])
            chemin, attendu = Path(espace_travail.chemin_actuel(infos['fichier'])), infos['sha256']
            if attendu in vus or _sha(chemin.read_bytes()) != attendu:
                continue
        except (ValueError, KeyError, TypeError, OSError):
            continue
        vus.add(attendu)
        sortie.append({'chemin': str(chemin), 'nom': chemin.name, 'sha256': attendu,
                       'modele': t['modele_id'], 'date_utc': t['date_utc']})
    return sortie


def observations_reelles(base=None, module=None, connues=()):
    """Articles des déclarations réelles comparées, au format de service_references.observations
    (pour anomalies.references_par_groupe). connues : empreintes déjà présentes dans les références."""
    sortie = []
    for d in declarations_reelles(base=base, module=module):
        if d['sha256'] in connues:
            continue
        try:
            donnees = extraire(Path(espace_travail.chemin_actuel(d['chemin'])).read_bytes())
        except (ValueError, OSError):
            continue
        devise = donnees['document']['devise'] or 'NON RENSEIGNEE'
        for a in donnees['articles']:
            if a['ratio'] is None or a['poids_brut'] is None or a['fob'] is None:
                continue
            sortie.append({'document_id': f"reel:{d['sha256']}", 'fichier': d['nom'], 'statut': 'reelle',
                           'importateur': donnees['document']['importateur'] or '', 'devise': devise,
                           'position': a['position'], 'code': a['code'] or '', 'designation': a['designation'] or '',
                           'poids': float(a['poids_brut']), 'fob': float(a['fob']), 'ratio': float(a['ratio']),
                           'groupe': (devise, a['code'] or '', a['designation_normalisee'] or '')})
    return sortie


def ajouter_declaration_reelle(chemin, auteur, module='friperie', base=None):
    """Retient un XML SYDONIA réel sans modèle correspondant (le fichier n'est ni copié ni modifié)."""
    if module not in ('friperie', 'divers'):
        raise ValueError('Type de dossier inconnu.')
    auteur, chemin = _auteur(auteur), Path(chemin).resolve()
    sha = _sha(chemin.read_bytes())
    with _connexion(base) as conn:
        conn.execute('INSERT OR IGNORE INTO declarations_reelles (sha256, chemin, nom, module, date_utc, auteur) '
                     'VALUES (?,?,?,?,?,?)', (sha, str(chemin), chemin.name, module, _maintenant(), auteur))
    return sha


def declarations_reelles(base=None, module=None):
    """Toutes les déclarations réelles connues et intactes : celles comparées à un modèle, puis celles
    retenues sans modèle. Même format que declarations_comparees (modele = None pour les secondes)."""
    sortie = declarations_comparees(base=base, module=module)
    vus = {d['sha256'] for d in sortie}
    with _connexion(base) as conn:
        lignes = conn.execute('SELECT * FROM declarations_reelles ORDER BY id DESC').fetchall()
    for l in lignes:
        if l['sha256'] in vus or (module is not None and l['module'] != module):
            continue
        chemin = espace_travail.chemin_actuel(l['chemin'])
        try:
            if _sha(Path(chemin).read_bytes()) != l['sha256']:
                continue
        except OSError:
            continue
        vus.add(l['sha256'])
        sortie.append({'chemin': chemin, 'nom': l['nom'], 'sha256': l['sha256'], 'modele': None,
                       'date_utc': l['date_utc']})
    return sortie


def empreintes_exports(base=None):
    """Empreintes de tous les XML exportés par AsyDec (archivés ou anciens exports)."""
    with _connexion(base) as conn:
        archives = {r['sha256'] for r in conn.execute('SELECT sha256 FROM exports_xml')}
        details = [r['detail'] for r in conn.execute('SELECT detail FROM evenements WHERE action=?', (EXPORT,))]
    for detail_ in details:
        try:
            archives.add(json.loads(detail_)['sha256'])
        except (ValueError, KeyError, TypeError):
            continue
    return archives


# Taxes globales : les XML n'en donnent que le total, mais les déclarations réelles montrent une part
# fixe du CIF. Elle n'est apprise que si au moins 2 déclarations concordent à 0,02 point près.
GLOBALES_MINIMUM, GLOBALES_DISPERSION = 2, Decimal('0.0002')


def taux_taxes_globales(base=None, module=None):
    """Part du CIF prise par les taxes globales dans les déclarations réelles comparées :
    {'taux' (Σ globales / Σ CIF), 'n', 'min', 'max', 'ecart_max' (CDF)} ou None si trop peu
    de déclarations ou si elles ne concordent pas (règle différente, à ne pas deviner)."""
    observations = []
    for d in declarations_reelles(base=base, module=module):
        try:
            v = extraire(Path(espace_travail.chemin_actuel(d['chemin'])).read_bytes())['valorisation']
            cif, globales = Decimal(v['cif_total']), Decimal(v['taxes_globales'])
        except (ValueError, OSError, TypeError, ArithmeticError):
            continue
        if cif > 0 and globales > 0:
            observations.append((cif, globales))
    if len(observations) < GLOBALES_MINIMUM:
        return None
    parts = [g / c for c, g in observations]
    if max(parts) - min(parts) > GLOBALES_DISPERSION:
        return None
    taux = sum(g for _, g in observations) / sum(c for c, _ in observations)
    return {'taux': taux, 'n': len(observations), 'min': min(parts), 'max': max(parts),
            'ecart_max': max(abs(g - (c * taux).to_integral_value()) for c, g in observations)}


def confiance_generation(signature, base=None, module=None):
    """Argument « confiance » de variantes.construire_profil : déclarations réelles comparées,
    bons modèles et modèles à éviter du module."""
    return {'reelles': [d['chemin'] for d in declarations_reelles(base=base, module=module)],
            'bons': bons_modeles(signature, base=base, module=module),
            'a_eviter': modeles_a_eviter(signature, base=base, module=module),
            'taxes_globales': taux_taxes_globales(base=base, module=module)}


def nombre_generes(signature, poids, fob, colis, base=None, module=None):
    """Modèles enregistrés (non supprimés) aux mêmes articles et aux mêmes totaux poids / FOB / colis."""
    compte = 0
    for m in lister(base=base, module=module):
        r = m['resultat']
        if (round(r['resume']['poids']) == round(poids) and round(r['resume']['fob'], 2) == round(fob, 2)
                and sum(r['colis']) == colis and _signature_modele(m['id'], base) == signature):
            compte += 1
    return compte


def _signature_modele(identifiant, base):
    with _connexion(base) as conn:
        source = conn.execute('SELECT base_xml FROM modeles WHERE id=?', (identifiant,)).fetchone()['base_xml']
    try:
        return variantes.signature_racine(ET.fromstring(bytes(source)))
    except ET.ParseError:
        return None


# =============================================================================
# Modèles de référence déjà utilisés
# =============================================================================
def empreinte_fichier(chemin):
    """Identité d'un XML de référence : son contenu, quels que soient son nom et son dossier."""
    return _sha(Path(chemin).read_bytes())


def signaler_reference(chemin, auteur, utilise=True, base=None):
    """Signale qu'un modèle de référence a déjà servi (même hors AsyDec), ou retire ce signalement."""
    auteur = _auteur(auteur)
    sha = empreinte_fichier(chemin)
    with _connexion(base) as conn:
        dernier = conn.execute('SELECT utilise FROM signalements_references WHERE sha256=? ORDER BY id DESC LIMIT 1',
                               (sha,)).fetchone()
        if bool(dernier and dernier['utilise']) != utilise:
            conn.execute('INSERT INTO signalements_references(sha256,nom,date_utc,auteur,utilise) VALUES(?,?,?,?,?)',
                         (sha, Path(chemin).name, _maintenant(), auteur, int(utilise)))


def usages_references(base=None):
    """Par empreinte de modèle de référence : modèles générés qui l'ont utilisé et signalement manuel.

    Un modèle enregistré avant le suivi de sa référence est rattaché au XML de son dossier,
    référence par défaut de la génération. Les modèles supprimés ne comptent pas.
    """
    with _connexion(base) as conn:
        modeles = conn.execute(f'SELECT m.id, m.cree_utc, m.resultat_json, m.base_xml, '
                               f'{_bascule_sql(SUPPRESSION, RESTAURATION)} supprime FROM modeles m ORDER BY m.id').fetchall()
        signalements = conn.execute('SELECT sha256, date_utc, auteur, utilise FROM signalements_references '
                                    'ORDER BY id').fetchall()
    usages = {}
    usage = lambda sha: usages.setdefault(sha, {'modeles': [], 'dernier_utc': None, 'signale': None})
    for m in modeles:
        if m['supprime']:
            continue
        reference = json.loads(m['resultat_json']).get('reference') or {}
        u = usage(reference.get('sha256') or _sha(bytes(m['base_xml'])))
        u['modeles'].append(m['id'])
        u['dernier_utc'] = m['cree_utc']
    for s in signalements:  # le dernier signalement de chaque modèle l'emporte
        usage(s['sha256'])['signale'] = {'date_utc': s['date_utc'], 'auteur': s['auteur']} if s['utilise'] else None
    return {sha: u for sha, u in usages.items() if u['modeles'] or u['signale']}


# =============================================================================
# Plaque
# =============================================================================
def _plaque(valeur):
    return moteur.normaliser_plaque(valeur)


def definir_plaque(identifiant, plaque, auteur, base=None):
    """Plaque saisie sur un modèle généré, quel que soit son statut ; tracée dans l'historique,
    le snapshot reste intact. Un modèle supprimé doit d'abord être restauré."""
    auteur = _auteur(auteur)
    plaque = _plaque(plaque)
    with _connexion(base) as conn:
        statut = _statut_courant(conn, identifiant)
        if statut is None:
            raise ValueError('Modèle introuvable.')
        evenements = [dict(e) for e in conn.execute(
            'SELECT action FROM evenements WHERE modele_id=? ORDER BY id', (identifiant,))]
        if _bascule_active(evenements, SUPPRESSION, RESTAURATION):
            raise ValueError('Restaurez le modèle avant de changer sa plaque.')
        precedente = conn.execute('SELECT detail FROM evenements WHERE modele_id=? AND action=? '
                                  'ORDER BY id DESC LIMIT 1', (identifiant, PLAQUE)).fetchone()
        if precedente is None or precedente['detail'] != plaque:
            _evenement(conn, identifiant, auteur, PLAQUE, detail=plaque)
    return plaque


_CHAMPS_PLAQUE = (b'Departure_arrival_information', b'Border_information')


def appliquer_plaque(contenu, plaque):
    """Inscrit la plaque dans Transport/Means_of_transport (arrivée et frontière), sans réécrire le reste du XML."""
    plaque = _plaque(plaque).encode('ascii')
    remplacees = []

    def remplacer_identites(bloc):
        # Seule la valeur d'Identity change ; les autres octets du fichier restent identiques.
        for nom in _CHAMPS_PLAQUE:
            motif = rb'(<%s>(?:(?!</%s>).)*?)<Identity(?:\s*/>|>.*?</Identity>)' % (nom, nom)
            bloc, n = re.subn(motif, lambda m: m.group(1) + b'<Identity>' + plaque + b'</Identity>',
                              bloc, count=1, flags=re.S)
            remplacees.append(n)
        return bloc

    nouveau = re.sub(rb'<Means_of_transport>.*?</Means_of_transport>', lambda m: remplacer_identites(m.group(0)),
                     bytes(contenu), count=1, flags=re.S)
    if not any(remplacees):
        raise ValueError('Le XML ne contient pas de champ Identity dans Transport/Means_of_transport : plaque non inscrite.')
    valeurs = [e.text for e in ET.fromstring(nouveau).findall('Transport/Means_of_transport/*/Identity')]
    if not valeurs or any(v != plaque.decode() for v in valeurs):
        raise ValueError('La plaque n’a pas pu être inscrite correctement dans le XML.')
    return nouveau


# =============================================================================
# Export XML
# =============================================================================
class ErreurSuiviExport(OSError):
    """Le fichier a été écrit, mais sa trace n'a pas pu être enregistrée."""


def _chemin_export(detail_):
    try:
        return espace_travail.chemin_actuel(json.loads(detail_)['chemin']) if detail_ else ''
    except (ValueError, KeyError, TypeError):
        return ''


def lire_export(identifiant, base=None):
    """Dernier export réel ; anciens événements : fichier original et SHA exigés."""
    with _connexion(base) as conn:
        evenement = conn.execute(
            'SELECT e.id,e.detail,x.sha256,x.contenu FROM evenements e '
            'LEFT JOIN exports_xml x ON x.evenement_id=e.id '
            'WHERE e.modele_id=? AND e.action=? ORDER BY e.id DESC LIMIT 1', (identifiant, EXPORT)).fetchone()
    if evenement is None:
        raise ValueError('Cette proposition n’a pas encore été exportée. Générez le XML avant de comparer.')
    if evenement['contenu'] is not None:
        contenu, sha = bytes(evenement['contenu']), evenement['sha256']
    else:
        details = json.loads(evenement['detail'])
        sha = details.get('sha256')
        try:
            contenu = Path(details['chemin']).read_bytes()
        except (KeyError, OSError):
            raise ValueError('Cet ancien export ne possède pas de copie archivée et son fichier est introuvable. '
                             'La comparaison nécessite le XML exporté original.') from None
    if not sha or _sha(contenu) != sha:
        raise ValueError('Le XML exporté a été modifié ou son empreinte est absente. Comparaison refusée.')
    return contenu


def nom_export(modele):
    """Nom portable ; aucune plaque ou identité ne peut introduire un chemin."""
    def nettoyer(valeur, defaut):
        texte = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '-', str(valeur or ''))
        return ' '.join(texte.split()).strip(' .-') or defaut
    plaque = nettoyer(modele.get('plaque') or modele['resultat'].get('info', {}).get('camion'), 'SANS-PLAQUE')[:80]
    nom = nettoyer(modele.get('nom'), f"Modele-{modele['id']}")
    if nom.lower().endswith('.xml'):
        nom = nom[:-4]
    return f'{plaque} - {nom}'[:210].rstrip(' .') + '.xml'


def _contenu_a_exporter(identifiant, modele, base):
    """Dernier export (ou snapshot), avec la plaque saisie dans Modèles générés si elle existe."""
    exporte = _dernier(modele['evenements'], EXPORT) is not None
    contenu = lire_export(identifiant, base=base) if exporte else bytes(modele['modele_xml'])
    saisie = _dernier(modele['evenements'], PLAQUE)
    return appliquer_plaque(contenu, saisie['detail']) if saisie else contenu


def _ecrire_atomique(contenu, destination, ecraser):
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


def exporter_xml(identifiant, destination, auteur, ecraser=False, base=None):
    """Télécharge un modèle validé, sans sa source et sans nouveau calcul fiscal."""
    auteur = _auteur(auteur)
    destination = Path(destination).expanduser().resolve()
    if destination.suffix.lower() != '.xml':
        raise ValueError('Choisissez un fichier avec extension .xml.')
    if destination == Path(base if base is not None else BASE).resolve():
        raise ValueError('La base de données ne peut pas servir de destination XML.')
    modele = detail(identifiant, base=base)
    if modele['statut'] != 'valide':
        raise ValueError('Seul un modèle Validé localement peut être téléchargé en XML.')
    contenu = _contenu_a_exporter(identifiant, modele, base)
    _ecrire_atomique(contenu, destination, ecraser)
    _tracer_export(identifiant, auteur, destination, contenu, base)
    return str(destination)


def _tracer_export(identifiant, auteur, destination, contenu, base):
    sha = _sha(contenu)
    trace = json.dumps({'chemin': str(destination), 'sha256': sha}, sort_keys=True)
    try:
        with _connexion(base) as conn:
            evenement = _evenement(conn, identifiant, auteur, EXPORT, detail=trace)
            conn.execute('INSERT INTO exports_xml(evenement_id,sha256,contenu) VALUES(?,?,?)',
                         (evenement, sha, contenu))
    except Exception as exc:
        raise ErreurSuiviExport(f'Le XML a été enregistré dans {destination}, mais son suivi a échoué : {exc}') from exc


def mettre_a_jour_export(identifiant, auteur, base=None):
    """Réinscrit la plaque saisie dans le dernier XML exporté, à la même place, quel que soit le statut.

    Seule la plaque change dans le fichier. Refusé si le fichier a disparu ou a été modifié depuis
    l'export : rien n'est alors écrasé. Renvoie le chemin réécrit, ou None sans export ni plaque saisie."""
    auteur = _auteur(auteur)
    modele = detail(identifiant, base=base)
    export, saisie = _dernier(modele['evenements'], EXPORT), _dernier(modele['evenements'], PLAQUE)
    chemin = _chemin_export(export['detail']) if export else ''
    if not chemin or not saisie:
        return None
    contenu = lire_export(identifiant, base=base)
    destination = Path(chemin)
    try:
        actuel = destination.read_bytes()
    except OSError:
        raise ValueError(f'Le XML généré est introuvable : {chemin}. Utilisez « Télécharger le XML… » '
                         'pour en créer un nouveau avec la plaque.') from None
    if actuel != contenu:
        raise ValueError(f'Le XML généré a été modifié depuis sa création : {chemin}. Il n’est pas réécrit ; '
                         'utilisez « Télécharger le XML… » pour en créer un nouveau avec la plaque.')
    nouveau = appliquer_plaque(contenu, saisie['detail'])
    if nouveau != contenu:
        _ecrire_atomique(nouveau, destination, ecraser=True)
        _tracer_export(identifiant, auteur, destination, nouveau, base)
    return str(destination)


def modele_par_export(contenu, base=None):
    """Modèle dont un export archivé a exactement ces octets, sinon None."""
    with _connexion(base) as conn:
        ligne = conn.execute('SELECT e.modele_id FROM exports_xml x JOIN evenements e ON e.id=x.evenement_id '
                             'WHERE x.sha256=? ORDER BY e.id DESC LIMIT 1', (_sha(contenu),)).fetchone()
    return ligne['modele_id'] if ligne else None


def fichier_xml_genere(d):
    """Dernier XML généré pour ce modèle : (chemin, état) ; état relu sur le disque, empreinte comprise."""
    trace = _dernier(d['evenements'], EXPORT)
    if trace is None:
        return '', 'Aucun XML généré pour ce modèle'
    try:
        infos = json.loads(trace['detail'])
        chemin = Path(infos['chemin'])
    except (ValueError, KeyError, TypeError):
        return '', 'Trace d’export illisible'
    try:
        octets = chemin.read_bytes()
    except OSError:
        return str(chemin), 'introuvable (déplacé ou supprimé)'
    if _sha(octets) != infos.get('sha256'):
        return str(chemin), 'MODIFIÉ depuis la génération : ce n’est plus le fichier généré'
    return str(chemin), 'présent et identique au XML généré'


# =============================================================================
# Comparaisons
# =============================================================================
def _texte_decimal(valeur):
    if isinstance(valeur, Decimal):
        return {'__decimal__': str(valeur)}
    raise TypeError(f'Valeur non enregistrable : {type(valeur).__name__}')


def _lire_decimal(objet):
    return Decimal(objet['__decimal__']) if set(objet) == {'__decimal__'} else objet


def _decimal_ou_rien(valeur):
    return Decimal(valeur) if valeur is not None else None


def _total_des_taxes(rapport):
    return next((l for l in rapport['lignes'] if l['position'] == 'Total global' and l['metrique'] == 'taxes'), {})


def noter_comparaison(identifiant, chemin_fourni, rapport, auteur, base=None):
    """Trace qu'un modèle exporté a été comparé ; le fichier fourni n'est ni copié ni modifié."""
    auteur = _auteur(auteur)
    contenu = Path(chemin_fourni).read_bytes()
    from asydec.declarations.verification_xml import est_verification
    if est_verification(contenu):
        raise ValueError('Ce fichier est un XML de vérification produit par AsyDec, pas une déclaration SYDONIA réelle : '
                         'il ne peut pas servir de comparaison.')
    total = _total_des_taxes(rapport)
    texte = lambda v: None if v is None else str(v)
    detail_ = json.dumps({'fichier': str(Path(chemin_fourni).resolve()), 'sha256': _sha(contenu),
                          'plaque_fournie': rapport.get('plaque_fournie') or '',
                          'total_estime': texte(total.get('prevu')), 'total_compare': texte(total.get('fourni')),
                          'ecart_total': texte(total.get('ecart')),
                          # Rapport complet conservé : la comparaison reste consultable sans le fichier.
                          'rapport': rapport},
                         ensure_ascii=False, sort_keys=True, default=_texte_decimal)
    with _connexion(base) as conn:
        _exiger_modele(conn, identifiant)
        return _evenement(conn, identifiant, auteur, COMPARAISON, detail=detail_)


def comparaisons(d):
    """Comparaisons enregistrées d'un modèle (detail()), de la plus récente à la plus ancienne."""
    sortie = []
    for e in reversed(d['evenements']):
        if e['action'] != COMPARAISON:
            continue
        infos = json.loads(e['detail'], object_hook=_lire_decimal)
        sortie.append({'evenement': e['id'], 'date_utc': e['date_utc'], 'auteur': e['auteur'],
                       'fichier': infos['fichier'], 'total_estime': _decimal_ou_rien(infos.get('total_estime')),
                       'total_compare': _decimal_ou_rien(infos.get('total_compare')),
                       'ecart_total': _decimal_ou_rien(infos.get('ecart_total')), 'rapport': infos.get('rapport')})
    return sortie


def reconstituer_comparaison(d, comparaison, base=None):
    """Rapport d'une ancienne comparaison enregistrée sans lui (comparaisons()) : export archivé face au
    fichier comparé, seulement s'il est encore sur le disque et inchangé. None sinon."""
    trace = next(e for e in d['evenements'] if e['id'] == comparaison['evenement'])
    attendu = json.loads(trace['detail']).get('sha256')
    try:
        genere = lire_export(d['id'], base=base)
        fourni = Path(comparaison['fichier']).read_bytes()
    except (ValueError, OSError):
        return None
    if not attendu or _sha(fourni) != attendu:
        return None
    try:
        return comparaison_prediction.comparer_octets(
            genere, fourni, _chemin_export(_dernier(d['evenements'], EXPORT)['detail']), comparaison['fichier'])
    except ValueError:
        return None


def _dernier_ecart(detail_):
    try:
        ecart = json.loads(detail_).get('ecart_total') if detail_ else None
        return _decimal_ou_rien(ecart)
    except (ValueError, TypeError, ArithmeticError):
        return None


def detail_taxes_modele(d, base=None):
    """Détail des taxes d'un modèle (resultat de detail()) : estimé seul, ou face au dernier XML comparé.

    Priorité au détail enregistré lors de la comparaison ; sinon le XML comparé est relu sur le
    disque et son empreinte vérifiée (il n'est jamais copié). Renvoie (lignes, explication).
    """
    try:
        octets, origine = lire_export(d['id'], base=base), 'XML exporté archivé'
    except ValueError:
        octets, origine = bytes(d['modele_xml']), 'proposition non exportée'
    genere = extraire(octets)
    estime_seul = lambda raison: (comparaison_prediction.detail_taxes(genere, {'articles': [], 'taxes_globales': []}),
                                  raison)
    trace = _dernier(d['evenements'], COMPARAISON)
    if trace is None:
        return estime_seul(f'Estimé seul ({origine}) : ce dossier n’a jamais été comparé avec un XML.')
    infos = json.loads(trace['detail'], object_hook=_lire_decimal)
    nom = Path(infos['fichier']).name
    enregistre = infos.get('rapport') or {}
    if enregistre.get('taxes_detail'):
        return enregistre['taxes_detail'], f'Estimé face au XML comparé {nom} (détail enregistré lors de la comparaison).'
    try:
        octets = Path(espace_travail.chemin_actuel(infos['fichier'])).read_bytes()
    except OSError:
        return estime_seul(f'Estimé seul : le XML comparé {nom} est introuvable (déplacé ou supprimé).')
    if _sha(octets) != infos['sha256']:
        return estime_seul(f'Estimé seul : le XML comparé {nom} a été modifié depuis la comparaison.')
    return comparaison_prediction.detail_taxes(genere, extraire(octets)), \
        f'Estimé ({origine}) face au dernier XML comparé : {nom}.'


# =============================================================================
# Données pour l'analyse des anomalies
# =============================================================================
def articles_identifies(base_xml, poids, fob, colis, ajustables=None):
    """Articles valorisés du XML de base avec leur groupe (devise, code, désignation), comme dans les
    références, et les valeurs données. ajustables : rangs (0 = premier article) dont le ratio absorbe l'écart."""
    donnees = extraire(bytes(base_xml))
    devise = donnees['document']['devise'] or 'NON RENSEIGNEE'
    sources = [a for a in donnees['articles'] if a['fob'] is not None and Decimal(a['fob']) != 0]
    sortie = []
    for k, (s, p, f, c) in enumerate(zip(sources, poids, fob, colis)):
        article = {'position': s['position'], 'code': s['code'] or '', 'designation': s['designation'] or '',
                   'groupe': (devise, s['code'] or '', s['designation_normalisee'] or ''),
                   'poids': float(p), 'fob': float(f), 'colis': float(c)}
        if ajustables is not None:
            article['ajustable'] = k in ajustables
        sortie.append(article)
    return sortie


def _articles_identifies(d):
    r = d['resultat']
    return articles_identifies(d['base_xml'], [a['poids'] for a in r['resume']['articles']],
                               [a['fob'] for a in r['resume']['articles']], r['colis'])


def donnees_proposition(base_xml, proposition, ajustables=()):
    """Proposition non enregistrée au format d'anomalies.analyser."""
    return {'id': None, 'statut': 'en_attente', 'motif': '', 'ecart_comparaison_pct': None,
            'articles': articles_identifies(base_xml, proposition['poids'], proposition['fob'],
                                            proposition['colis'], set(ajustables))}


def _ecart_derniere_comparaison_pct(d):
    derniere = next(iter(comparaisons(d)), None)
    if derniere and derniere['ecart_total'] is not None and derniere['total_estime']:
        return float(derniere['ecart_total'] / abs(derniere['total_estime']) * 100)
    return None


def donnees_analyse(base=None, module=None):
    """Modèles non supprimés au format d'anomalies.analyser (articles identifiés comme dans les références)."""
    sortie = []
    for m in lister(base=base, module=module):
        d = detail(m['id'], base=base)
        try:
            articles = _articles_identifies(d)
        except ValueError:
            continue
        motif = next((e['detail'] for e in reversed(d['evenements']) if e['statut'] == 'rejete'), '')
        sortie.append({'id': d['id'], 'statut': d['statut'], 'motif': motif, 'articles': articles,
                       'note': d['note'], 'note_commentaire': d['note_commentaire'],
                       'ecart_comparaison_pct': _ecart_derniere_comparaison_pct(d)})
    return sortie


def modules_exports(base=None):
    """Classement de chaque export historique, y compris après un autre téléchargement du modèle."""
    with _connexion(base) as conn:
        lignes = conn.execute('SELECT e.detail, m.resultat_json FROM evenements e '
                              'JOIN modeles m ON m.id=e.modele_id WHERE e.action=? ORDER BY e.id', (EXPORT,)).fetchall()
    sortie = {}
    for ligne in lignes:
        chemin = _chemin_export(ligne['detail'])
        if chemin:
            sortie[str(Path(chemin).resolve())] = json.loads(ligne['resultat_json']).get('module', 'friperie')
    return sortie
