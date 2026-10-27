"""Catalogue commun : réutilise les archives SQLite et expose les modèles existants."""
import hashlib
from pathlib import Path
import import_references
import service_references
import etude_xml


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


def lister(conn, supplementaires=(), generation=False):
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
        try:
            etude = etude_xml.analyser(document['chemin'])
        except (OSError, ValueError, SyntaxError):
            continue
        positions = [a['article'] for a in etude['articles']]
        complet = positions == list(range(1, 9)) and all(
            a['poids'] is not None and a['poids'] > 0 and
            a['fob'] is not None and a['fob'] > 0 for a in etude['articles'])
        document.update(articles=len(positions), positions=positions,
                        usage='Génération et étude' if complet else 'Étude uniquement')
        if not generation or complet:
            disponibles.append(document)
    return disponibles


def _fichier_retraits(configuration=None):
    import gestion_locale
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
    import gestion_locale
    valeurs=retraits(configuration)
    for d in documents:
        valeurs[d['empreinte']]={'nom':d['nom'],'auteur':auteur,
            'retire_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    gestion_locale._ecrire_json(_fichier_retraits(configuration),valeurs)


def restaurer(empreintes,configuration=None):
    import gestion_locale
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
