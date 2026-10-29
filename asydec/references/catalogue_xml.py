"""Catalogue commun : réutilise les archives SQLite et expose les modèles existants."""
import hashlib
from pathlib import Path

from asydec.declarations import etude_xml
from asydec.references import import_references
from asydec.references import service_references


def partager(conn, chemins):
    """Un même contenu conserve son document et son statut, quelle que soit la page."""
    identifiants, erreurs = [], []
    for chemin in chemins:
        try:
            _, identifiant = import_references.importer_fichier(conn, chemin)
            identifiants.append(identifiant)
            empreinte=conn.execute('SELECT sha256 FROM documents WHERE id=?',(identifiant,)).fetchone()[0]
            restaurer([empreinte])
        except Exception as exc:  # un fichier refusé ne bloque pas le partage des autres
            erreurs.append(f'{Path(chemin).name} : {exc}')
    return identifiants, erreurs


def lister(conn, supplementaires=(), generation=False, module=None):
    if module is not None and module not in MODULES:
        raise ValueError('Type de dossier inconnu.')
    classement = dict(conn.execute('SELECT sha256, module FROM xml_modules'))
    resultat, vus = [], set()
    retires=retraits()
    for d in service_references.lister_documents(conn):
        if d['sha256'] in retires:
            vus.add(d['sha256'])
            continue
        if generation and d['statut'] in ('rejete', 'exclu'):
            # Ne pas réintroduire ce même contenu par une ancienne copie sur disque.
            vus.add(d['sha256'])
            continue
        if not Path(d['archive']).is_file():
            continue
        vus.add(d['sha256'])
        resultat.append({'id':d['id'], 'empreinte':d['sha256'], 'chemin':d['archive'],
                         'nom':d['nom_initial'], 'importateur':d['importateur'] or '',
                         'statut':d['statut'], 'source':'Bibliothèque', 'articles':d['nb_articles']})
    for p in supplementaires:
        try:
            p=Path(p)
            empreinte=hashlib.sha256(p.read_bytes()).hexdigest()
            if empreinte in vus or empreinte in retires:
                continue
            vus.add(empreinte)
            resultat.append({'id':None,'empreinte':empreinte,'chemin':str(p),'nom':p.name,
                             'importateur':'','statut':'non_verifie','source':'Modèle existant','articles':None})
        except OSError:
            continue
    disponibles = []
    for document in resultat:
        document['module'] = classement.get(document['empreinte'], 'friperie')
        if module is not None and document['module'] != module:
            continue
        try:
            etude = etude_xml.analyser(document['chemin'])
        except (OSError, ValueError, SyntaxError):
            continue
        positions = [a['article'] for a in etude['articles']]
        complet = bool(positions) and positions == list(range(1, len(positions)+1)) and all(
            a['poids'] is not None and a['poids'] > 0 and
            a['fob'] is not None and a['fob'] > 0 for a in etude['articles'])
        document.update(articles=len(positions), positions=positions,
                        usage='Génération et étude' if complet else 'Étude uniquement')
        if not generation or complet:
            disponibles.append(document)
    return disponibles


def _fichier_retraits(configuration=None):
    from asydec.systeme import gestion_locale
    return (Path(configuration) if configuration is not None else gestion_locale.CONFIGURATION) / 'xml_retires.json'


def retraits(configuration=None):
    import json
    chemin=_fichier_retraits(configuration)
    if not chemin.exists():
        return {}
    valeurs=json.loads(chemin.read_text(encoding='utf-8'))
    if not isinstance(valeurs,dict):
        raise ValueError('La liste des XML retirés est illisible.')
    return valeurs


def retirer(documents,auteur='',configuration=None):
    """Retrait logique et traçable ; aucun fichier ni événement historique n'est effacé."""
    import datetime
    from asydec.systeme import gestion_locale
    valeurs=retraits(configuration)
    for d in documents:
        valeurs[d['empreinte']]={'nom':d['nom'],'auteur':auteur,
            'retire_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    gestion_locale._ecrire_json(_fichier_retraits(configuration),valeurs)


def restaurer(empreintes,configuration=None):
    from asydec.systeme import gestion_locale
    valeurs=retraits(configuration)
    for empreinte in empreintes:
        valeurs.pop(empreinte,None)
    if _fichier_retraits(configuration).exists():
        gestion_locale._ecrire_json(_fichier_retraits(configuration),valeurs)


def est_retire(chemin,configuration=None):
    try:
        return hashlib.sha256(Path(chemin).read_bytes()).hexdigest() in retraits(configuration)
    except OSError:
        return False


MODULES = {'friperie': 'Friperie', 'divers': 'Divers'}


def classer(conn, empreintes, module, remplacer=True):
    """Le classement suit le contenu du XML, même renommé ou importé à nouveau."""
    if module not in MODULES:
        raise ValueError('Type de dossier inconnu.')
    with conn:
        for empreinte in empreintes:
            if len(empreinte) != 64 or any(c not in '0123456789abcdef' for c in empreinte):
                raise ValueError('Empreinte XML invalide.')
            conn.execute('INSERT INTO xml_modules(sha256, module) VALUES (?, ?) ' +
                         ('ON CONFLICT(sha256) DO UPDATE SET module=excluded.module' if remplacer else
                          'ON CONFLICT(sha256) DO NOTHING'), (empreinte, module))


def module_document(conn, empreinte):
    ligne = conn.execute('SELECT module FROM xml_modules WHERE sha256=?', (empreinte,)).fetchone()
    if ligne:
        return ligne[0]
    return 'friperie' if conn.execute('SELECT 1 FROM documents WHERE sha256=?', (empreinte,)).fetchone() else None
