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
    plaque = resultat.get('plaque')
    if plaque:
        moteur.ecrire_plaque(arbre.getroot(), plaque)
    for cle in ('poids', 'fob', 'cif', 'taxes_totales'):
        if Decimal(str(resume[cle])) != Decimal(str(resultat['resume'][cle])):
            raise ValueError("L'aperçu ne correspond plus à sa base. Vérifiez-le à nouveau avant de le conserver.")
    xml = ET.tostring(arbre.getroot(), encoding='utf-8', xml_declaration=True)
    normaliser = lambda v: str(Decimal(str(v)).normalize())
    contenu = {'base': hashlib.sha256(source).hexdigest(),
               'lignes': [[normaliser(f), normaliser(p), normaliser(c)]
                          for (f,p),c in zip(lignes,resultat['colis'])]}
    if plaque:  # absente sinon : les empreintes des modèles existants restent identiques
        contenu['plaque'] = moteur.normaliser_plaque(plaque)
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


def lister(statut=None, base=None, supprimes=False):
    """supprimes : False masque les modèles retirés, True ne montre qu'eux."""
    if statut is not None and statut not in STATUTS:
        raise ValueError('Statut local inconnu.')
    with _connexion(base) as conn:
        lignes = conn.execute('''SELECT m.id,m.cree_utc,m.auteur,m.importateur,m.nom,m.resultat_json,
            (SELECT e.statut FROM evenements e WHERE e.modele_id=m.id AND e.statut IS NOT NULL ORDER BY e.id DESC LIMIT 1) statut,
            EXISTS(SELECT 1 FROM evenements e WHERE e.modele_id=m.id AND e.action='export') exporte,
            (SELECT e.date_utc FROM evenements e WHERE e.modele_id=m.id ORDER BY e.id DESC LIMIT 1) modifie_utc,
            (SELECT e.detail FROM evenements e WHERE e.modele_id=m.id AND e.action='plaque' ORDER BY e.id DESC LIMIT 1) plaque_saisie,
            (SELECT COUNT(*) FROM evenements e WHERE e.modele_id=m.id AND e.action='comparaison') comparaisons,
            COALESCE((SELECT e.action='bon_modele' FROM evenements e WHERE e.modele_id=m.id
                      AND e.action IN ('bon_modele','retrait_bon_modele') ORDER BY e.id DESC LIMIT 1),0) bon,
            (SELECT e.detail FROM evenements e WHERE e.modele_id=m.id AND e.action='export' ORDER BY e.id DESC LIMIT 1) export_detail,
            COALESCE((SELECT e.action='suppression' FROM evenements e WHERE e.modele_id=m.id
                      AND e.action IN ('suppression','restauration') ORDER BY e.id DESC LIMIT 1),0) supprime,
            (SELECT e.date_utc FROM evenements e WHERE e.modele_id=m.id AND e.action='comparaison' ORDER BY e.id DESC LIMIT 1) compare_utc,
            (SELECT e.detail FROM evenements e WHERE e.modele_id=m.id AND e.action='comparaison' ORDER BY e.id DESC LIMIT 1) compare_detail
            FROM modeles m ORDER BY m.id DESC''').fetchall()
    sortie = []
    for ligne in lignes:
        d = dict(ligne)
        if (statut is None or d['statut'] == statut) and bool(d['supprime']) == supprimes:
            d['resultat'] = json.loads(d.pop('resultat_json'))
            d['plaque'] = d.pop('plaque_saisie') or d['resultat'].get('info', {}).get('camion') or ''
            d['chemin_xml'] = _chemin_export(d.pop('export_detail'))
            d['dernier_ecart'] = _dernier_ecart(d.pop('compare_detail'))
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
        sortie['supprime'] = _supprime(sortie['evenements'])
        sortie['bon'] = _bon(sortie['evenements'])
        saisie = next((e['detail'] for e in reversed(sortie['evenements']) if e['action'] == 'plaque'), None)
        sortie['plaque'] = saisie or sortie['resultat'].get('info', {}).get('camion') or ''
        return sortie


def noter_comparaison(identifiant, chemin_fourni, rapport, auteur, base=None):
    """Trace qu'un modèle exporté a été comparé ; le fichier fourni n'est ni copié ni modifié."""
    auteur = _auteur(auteur)
    contenu = Path(chemin_fourni).read_bytes()
    total = next((l for l in rapport['lignes'] if l['position'] == 'Total global' and l['metrique'] == 'taxes'), {})
    texte = lambda v: None if v is None else str(v)
    detail = json.dumps({'fichier': str(Path(chemin_fourni).resolve()), 'sha256': hashlib.sha256(contenu).hexdigest(),
                         'plaque_fournie': rapport.get('plaque_fournie') or '',
                         'total_estime': texte(total.get('prevu')), 'total_compare': texte(total.get('fourni')),
                         'ecart_total': texte(total.get('ecart')),
                         # Rapport complet conservé : la comparaison reste consultable sans le fichier.
                         'rapport': rapport},
                        ensure_ascii=False, sort_keys=True, default=_texte_decimal)
    with _connexion(base) as conn:
        if not conn.execute('SELECT 1 FROM modeles WHERE id=?', (identifiant,)).fetchone():
            raise ValueError('Modèle introuvable.')
        return _evenement(conn, identifiant, auteur, 'comparaison', detail=detail)


def _texte_decimal(valeur):
    if isinstance(valeur, Decimal):
        return {'__decimal__': str(valeur)}
    raise TypeError(f'Valeur non enregistrable : {type(valeur).__name__}')


def _lire_decimal(objet):
    return Decimal(objet['__decimal__']) if set(objet) == {'__decimal__'} else objet


def comparaisons(d):
    """Comparaisons enregistrées d'un modèle (detail()), de la plus récente à la plus ancienne."""
    sortie = []
    for e in reversed(d['evenements']):
        if e['action'] != 'comparaison':
            continue
        infos = json.loads(e['detail'], object_hook=_lire_decimal)
        rapport = infos.get('rapport')
        decimal = lambda v: Decimal(v) if v is not None else None
        sortie.append({'evenement': e['id'], 'date_utc': e['date_utc'], 'auteur': e['auteur'],
                       'fichier': infos['fichier'], 'total_estime': decimal(infos.get('total_estime')),
                       'total_compare': decimal(infos.get('total_compare')),
                       'ecart_total': decimal(infos.get('ecart_total')), 'rapport': rapport})
    return sortie


def modele_par_export(contenu, base=None):
    """Modèle dont un export archivé a exactement ces octets, sinon None."""
    sha = hashlib.sha256(contenu).hexdigest()
    with _connexion(base) as conn:
        ligne = conn.execute('SELECT e.modele_id FROM exports_xml x JOIN evenements e ON e.id=x.evenement_id '
                             'WHERE x.sha256=? ORDER BY e.id DESC LIMIT 1', (sha,)).fetchone()
    return ligne['modele_id'] if ligne else None


def detail_taxes_modele(d, base=None):
    """Détail des taxes d'un modèle (resultat de detail()) : estimé seul, ou face au dernier XML comparé.

    Le XML comparé est relu sur le disque et son empreinte vérifiée ; il n'est jamais copié.
    Renvoie (lignes, explication).
    """
    import comparaison_prediction
    from import_references import extraire
    try:
        genere_octets = lire_export(d['id'], base=base)
        origine = 'XML exporté archivé'
    except ValueError:
        genere_octets = d['modele_xml']
        origine = 'proposition non exportée'
    genere = extraire(bytes(genere_octets))
    trace = next((json.loads(e['detail'], object_hook=_lire_decimal) for e in reversed(d['evenements'])
                  if e['action'] == 'comparaison'), None)
    vide = {'articles': [], 'taxes_globales': []}
    enregistre = (trace or {}).get('rapport') or {}
    if enregistre.get('taxes_detail'):
        # Détail enregistré au moment de la comparaison : indépendant du fichier comparé.
        return enregistre['taxes_detail'], \
            f"Estimé face au XML comparé {Path(trace['fichier']).name} (détail enregistré lors de la comparaison)."
    if trace is None:
        return comparaison_prediction.detail_taxes(genere, vide), \
            f'Estimé seul ({origine}) : ce dossier n’a jamais été comparé avec un XML.'
    chemin = Path(trace['fichier'])
    try:
        octets = chemin.read_bytes()
    except OSError:
        return comparaison_prediction.detail_taxes(genere, vide), \
            f'Estimé seul : le XML comparé {chemin.name} est introuvable (déplacé ou supprimé).'
    if hashlib.sha256(octets).hexdigest() != trace['sha256']:
        return comparaison_prediction.detail_taxes(genere, vide), \
            f'Estimé seul : le XML comparé {chemin.name} a été modifié depuis la comparaison.'
    return comparaison_prediction.detail_taxes(genere, extraire(octets)), \
        f'Estimé ({origine}) face au dernier XML comparé : {chemin.name}.'


def resume_evenement(e):
    """Libellé lisible d'un événement d'historique."""
    if e['action'] in ('bon_modele', 'retrait_bon_modele'):
        return 'Coché bon modèle ★' if e['action'] == 'bon_modele' else 'Coche bon modèle retirée'
    if e['action'] in ('suppression', 'restauration'):
        libelle = 'Supprimé de la liste' if e['action'] == 'suppression' else 'Restauré dans la liste'
        return f"{libelle} · {e['detail']}" if e['detail'] else libelle
    if e['action'] == 'plaque':
        return f"Plaque : {e['detail']}"
    if e['action'] == 'comparaison':
        d = json.loads(e['detail'])
        ecart = d.get('ecart_total')
        return (f"Comparé avec {Path(d['fichier']).name}"
                + (f" · écart total déclaration {ecart} CDF" if ecart is not None else ''))
    if e['action'] == 'export':
        try:
            return f"XML exporté : {Path(json.loads(e['detail'])['chemin']).name}"
        except (ValueError, KeyError):
            pass
    libelle = STATUTS.get(e['statut'], e['action'])
    return f"{libelle} · {e['detail']}" if e['detail'] else libelle


def _dernier_ecart(detail):
    try:
        ecart = json.loads(detail).get('ecart_total') if detail else None
        return Decimal(ecart) if ecart is not None else None
    except (ValueError, TypeError, ArithmeticError):
        return None


def _chemin_export(detail):
    try:
        return json.loads(detail)['chemin'] if detail else ''
    except (ValueError, KeyError, TypeError):
        return ''


def fichier_xml_genere(d):
    """Dernier XML généré pour ce modèle : (chemin, état) ; état relu sur le disque, empreinte comprise."""
    trace = next((e['detail'] for e in reversed(d['evenements']) if e['action'] == 'export'), None)
    if trace is None:
        return '', 'Aucun XML généré pour ce modèle'
    try:
        infos = json.loads(trace)
        chemin = Path(infos['chemin'])
    except (ValueError, KeyError, TypeError):
        return '', 'Trace d’export illisible'
    try:
        octets = chemin.read_bytes()
    except OSError:
        return str(chemin), 'introuvable (déplacé ou supprimé)'
    if hashlib.sha256(octets).hexdigest() != infos.get('sha256'):
        return str(chemin), 'MODIFIÉ depuis la génération : ce n’est plus le fichier généré'
    return str(chemin), 'présent et identique au XML généré'


def _bon(evenements):
    dernier = next((e['action'] for e in reversed(evenements) if e['action'] in ('bon_modele', 'retrait_bon_modele')), None)
    return dernier == 'bon_modele'


def marquer_bon(identifiant, auteur, bon=True, base=None):
    """Coche « bon modèle » : sert seulement à orienter les prochaines répartitions, sans valeur de validation."""
    auteur = _auteur(auteur)
    with _connexion(base) as conn:
        if not conn.execute('SELECT 1 FROM modeles WHERE id=?', (identifiant,)).fetchone():
            raise ValueError('Modèle introuvable.')
        evenements = [dict(e) for e in conn.execute('SELECT action FROM evenements WHERE modele_id=? ORDER BY id', (identifiant,))]
        if _bon(evenements) != bon:
            _evenement(conn, identifiant, auteur, 'bon_modele' if bon else 'retrait_bon_modele')


def bons_modeles(signature, base=None):
    """Répartitions des modèles cochés, non supprimés, dont les articles sont ceux de cette signature."""
    import variantes
    sortie = []
    for m in lister(base=base):
        if not m['bon']:
            continue
        with _connexion(base) as conn:
            source = conn.execute('SELECT base_xml FROM modeles WHERE id=?', (m['id'],)).fetchone()['base_xml']
        try:
            if variantes.signature_racine(ET.fromstring(bytes(source))) != signature:
                continue
        except ET.ParseError:
            continue
        r = m['resultat']
        sortie.append({'id': m['id'], 'poids': [a['poids'] for a in r['resume']['articles']],
                       'fob': list(r['fob']), 'colis': list(r['colis'])})
    return sortie


def _supprime(evenements):
    dernier = next((e['action'] for e in reversed(evenements) if e['action'] in ('suppression', 'restauration')), None)
    return dernier == 'suppression'


def supprimer(identifiant, auteur, motif='', base=None):
    """Retire le modèle de la liste. Rien n'est effacé : snapshot, exports et historique restent (restauration possible)."""
    _changer_suppression(identifiant, auteur, 'suppression', motif, base)


def restaurer(identifiant, auteur, base=None):
    _changer_suppression(identifiant, auteur, 'restauration', '', base)


def _changer_suppression(identifiant, auteur, action, motif, base):
    auteur = _auteur(auteur)
    with _connexion(base) as conn:
        if not conn.execute('SELECT 1 FROM modeles WHERE id=?', (identifiant,)).fetchone():
            raise ValueError('Modèle introuvable.')
        evenements = [dict(e) for e in conn.execute('SELECT action FROM evenements WHERE modele_id=? ORDER BY id', (identifiant,))]
        if _supprime(evenements) != (action == 'suppression'):
            _evenement(conn, identifiant, auteur, action, detail=(motif or '').strip())


def appliquer_plaque(contenu, plaque):
    """Inscrit la plaque dans Transport/Means_of_transport (arrivée et frontière), sans réécrire le reste du XML."""
    import re
    plaque = _plaque(plaque).encode('ascii')
    remplacees = []
    def identite(bloc):
        # Seule la valeur d'Identity change ; les autres octets du fichier restent identiques.
        motif = rb'(<%s>(?:(?!</%s>).)*?)<Identity(?:\s*/>|>.*?</Identity>)'
        for nom in (b'Departure_arrival_information', b'Border_information'):
            bloc, n = re.subn(motif % (nom, nom), lambda m: m.group(1) + b'<Identity>' + plaque + b'</Identity>',
                              bloc, count=1, flags=re.S)
            remplacees.append(n)
        return bloc
    nouveau = re.sub(rb'<Means_of_transport>.*?</Means_of_transport>', lambda m: identite(m.group(0)),
                     bytes(contenu), count=1, flags=re.S)
    if not any(remplacees):
        raise ValueError('Le XML ne contient pas de champ Identity dans Transport/Means_of_transport : plaque non inscrite.')
    racine = ET.fromstring(nouveau)
    valeurs = [e.text for e in racine.findall('Transport/Means_of_transport/*/Identity')]
    if not valeurs or any(v != plaque.decode() for v in valeurs):
        raise ValueError('La plaque n’a pas pu être inscrite correctement dans le XML.')
    return nouveau


def _plaque(valeur):
    return moteur.normaliser_plaque(valeur)


def definir_plaque(identifiant, plaque, auteur, base=None):
    """Plaque saisie sur un modèle validé ; tracée dans l'historique, le snapshot reste intact."""
    auteur = _auteur(auteur)
    plaque = _plaque(plaque)
    with _connexion(base) as conn:
        courant = conn.execute('SELECT statut FROM evenements WHERE modele_id=? AND statut IS NOT NULL ORDER BY id DESC LIMIT 1',(identifiant,)).fetchone()
        if courant is None:
            raise ValueError('Modèle introuvable.')
        if courant['statut'] != 'valide':
            raise ValueError('La plaque se saisit sur un modèle Validé localement.')
        precedente = conn.execute("SELECT detail FROM evenements WHERE modele_id=? AND action='plaque' ORDER BY id DESC LIMIT 1",(identifiant,)).fetchone()
        if precedente is None or precedente['detail'] != plaque:
            _evenement(conn, identifiant, auteur, 'plaque', detail=plaque)
    return plaque


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
    plaque = nettoyer(modele.get('plaque') or modele['resultat'].get('info', {}).get('camion'), 'SANS-PLAQUE')[:80]
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
    # Plaque saisie dans Modèles générés : elle remplace celle du XML de base.
    saisie = next((e['detail'] for e in reversed(modele['evenements']) if e['action'] == 'plaque'), None)
    if saisie:
        contenu = appliquer_plaque(contenu, saisie)
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
