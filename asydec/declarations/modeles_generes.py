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
def _empreinte(source, lignes, colis, plaque):
    """Identité d'une proposition : base, répartition et plaque (absente des anciennes empreintes)."""
    normaliser = lambda v: str(Decimal(str(v)).normalize())
    contenu = {'base': _sha(source),
               'lignes': [[normaliser(f), normaliser(p), normaliser(c)] for (f, p), c in zip(lignes, colis)]}
    if plaque:
        contenu['plaque'] = moteur.normaliser_plaque(plaque)
    return _sha(json.dumps(contenu, sort_keys=True).encode())


def _snapshot(source, resultat, lignes):
    """XML du modèle recalculé depuis la base, sans écrire dans le fichier d'origine."""
    arbre = ET.ElementTree(ET.fromstring(source))
    resume = moteur.recalculer(arbre, lignes, resultat['colis'])
    if resultat.get('plaque'):
        moteur.ecrire_plaque(arbre.getroot(), resultat['plaque'])
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


def enregistrer(resultat, chemin_base, auteur, export=None, base=None, reference=None):
    """Sauvegarde explicite ; un export du même contenu conserve son statut local.

    reference : XML de référence des ratios, mémorisé pour signaler les modèles déjà utilisés.
    """
    auteur = _auteur(auteur)
    source = Path(chemin_base).read_bytes()
    if reference:
        resultat = {**resultat, 'reference': {'nom': Path(reference).name, 'sha256': empreinte_fichier(reference)}}
    lignes = [(a['fob'], a['poids']) for a in resultat['resume']['articles']]
    if len(lignes) != len(resultat['colis']):
        raise ValueError('Nombre de colis et articles incohérent.')
    xml = _snapshot(source, resultat, lignes)
    empreinte = _empreinte(source, lignes, resultat['colis'], resultat.get('plaque'))
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
    {_derniere(COMPARAISON)} compare_detail
    FROM modeles m ORDER BY m.id DESC'''


def _plaque_affichee(saisie, resultat):
    return saisie or resultat.get('info', {}).get('camion') or ''


def lister(statut=None, base=None, supprimes=False):
    """supprimes : False masque les modèles retirés, True ne montre qu'eux."""
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
        d['plaque'] = _plaque_affichee(d.pop('plaque_saisie'), d['resultat'])
        d['chemin_xml'] = _chemin_export(d.pop('export_detail'))
        d['dernier_ecart'] = _dernier_ecart(d.pop('compare_detail'))
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


def bons_modeles(signature, base=None):
    """Répartitions des modèles cochés, non supprimés, dont les articles sont ceux de cette signature."""
    sortie = []
    for m in lister(base=base):
        if not m['bon'] or _signature_modele(m['id'], base) != signature:
            continue
        r = m['resultat']
        sortie.append({'id': m['id'], 'poids': [a['poids'] for a in r['resume']['articles']],
                       'fob': list(r['fob']), 'colis': list(r['colis'])})
    return sortie


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
    """Plaque saisie sur un modèle validé ; tracée dans l'historique, le snapshot reste intact."""
    auteur = _auteur(auteur)
    plaque = _plaque(plaque)
    with _connexion(base) as conn:
        statut = _statut_courant(conn, identifiant)
        if statut is None:
            raise ValueError('Modèle introuvable.')
        if statut != 'valide':
            raise ValueError('La plaque se saisit sur un modèle Validé localement.')
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
        return json.loads(detail_)['chemin'] if detail_ else ''
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
    sha = _sha(contenu)
    trace = json.dumps({'chemin': str(destination), 'sha256': sha}, sort_keys=True)
    try:
        with _connexion(base) as conn:
            evenement = _evenement(conn, identifiant, auteur, EXPORT, detail=trace)
            conn.execute('INSERT INTO exports_xml(evenement_id,sha256,contenu) VALUES(?,?,?)',
                         (evenement, sha, contenu))
    except Exception as exc:
        raise ErreurSuiviExport(f'Le XML a été enregistré dans {destination}, mais son suivi a échoué : {exc}') from exc
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
        octets = Path(infos['fichier']).read_bytes()
    except OSError:
        return estime_seul(f'Estimé seul : le XML comparé {nom} est introuvable (déplacé ou supprimé).')
    if _sha(octets) != infos['sha256']:
        return estime_seul(f'Estimé seul : le XML comparé {nom} a été modifié depuis la comparaison.')
    return comparaison_prediction.detail_taxes(genere, extraire(octets)), \
        f'Estimé ({origine}) face au dernier XML comparé : {nom}.'


# =============================================================================
# Données pour l'analyse des anomalies
# =============================================================================
def _articles_identifies(d):
    """Articles du modèle avec leur groupe (devise, code, désignation), comme dans les références."""
    donnees = extraire(bytes(d['base_xml']))
    devise = donnees['document']['devise'] or 'NON RENSEIGNEE'
    sources = [a for a in donnees['articles'] if a['fob'] is not None and Decimal(a['fob']) != 0]
    r = d['resultat']
    return [{'position': s['position'], 'code': s['code'] or '', 'designation': s['designation'] or '',
             'groupe': (devise, s['code'] or '', s['designation_normalisee'] or ''),
             'poids': float(a['poids']), 'fob': float(a['fob']), 'colis': float(c)}
            for s, a, c in zip(sources, r['resume']['articles'], r['colis'])]


def _ecart_derniere_comparaison_pct(d):
    derniere = next(iter(comparaisons(d)), None)
    if derniere and derniere['ecart_total'] is not None and derniere['total_estime']:
        return float(derniere['ecart_total'] / abs(derniere['total_estime']) * 100)
    return None


def donnees_analyse(base=None):
    """Modèles non supprimés au format d'anomalies.analyser (articles identifiés comme dans les références)."""
    sortie = []
    for m in lister(base=base):
        d = detail(m['id'], base=base)
        try:
            articles = _articles_identifies(d)
        except ValueError:
            continue
        motif = next((e['detail'] for e in reversed(d['evenements']) if e['statut'] == 'rejete'), '')
        sortie.append({'id': d['id'], 'statut': d['statut'], 'motif': motif, 'articles': articles,
                       'ecart_comparaison_pct': _ecart_derniere_comparaison_pct(d)})
    return sortie
