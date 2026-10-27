"""Catalogue commun : réutilise les archives SQLite et expose les modèles existants."""
import hashlib
from pathlib import Path
import import_references
import service_references


def partager(conn, chemins):
    """Un même contenu conserve son document et son statut, quelle que soit la page."""
    identifiants, erreurs = [], []
    for chemin in chemins:
        try:
            _, identifiant = import_references.importer_fichier(conn, chemin)
            identifiants.append(identifiant)
        except Exception as exc:  # un fichier refusé ne bloque pas le partage des autres
            erreurs.append(f'{Path(chemin).name} : {exc}')
    return identifiants, erreurs


def lister(conn, supplementaires=(), generation=False):
    resultat, vus = [], set()
    for d in service_references.lister_documents(conn):
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
            if empreinte in vus:
                continue
            vus.add(empreinte)
            resultat.append({'id':None,'empreinte':empreinte,'chemin':str(p),'nom':p.name,
                             'importateur':'','statut':'non_verifie','source':'Modèle existant','articles':None})
        except OSError:
            continue
    return resultat
