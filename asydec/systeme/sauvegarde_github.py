"""Publication explicite et récupération des seuls exports chiffrés via GitHub Releases."""
from datetime import datetime, timezone
import hashlib
import http.client
import json
from pathlib import Path
import secrets
import shutil
import tempfile
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPSHandler

from asydec.systeme import mises_a_jour as github, sauvegarde_chiffree as chiffrement


def _api(chemin, token=None, methode='GET', donnees=None):
    if not chemin.startswith('/releases') or '..' in chemin:
        raise ValueError('Adresse GitHub non autorisée.')
    url = github.API + chemin
    try:
        if methode == 'GET':
            with github._ouvrir(url, token) as r:
                return json.loads(r.read(10_000_000))
        if not token:
            raise ValueError('Un jeton GitHub avec accès Contents en écriture est requis pour publier.')
        contenu = json.dumps(donnees).encode() if donnees is not None else None
        requete = Request(url, data=contenu, method=methode, headers={
            'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
            'Content-Type': 'application/json', 'User-Agent': 'AsyDec'})
        with build_opener(github.Redirection(), HTTPSHandler(context=github.contexte_ssl())).open(requete, timeout=60) as r:
            resultat = r.read(2_000_000)
            return json.loads(resultat) if resultat else None
    except HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise ValueError('Accès GitHub refusé. Vérifiez le jeton et son accès au dépôt AsyDec '
                             '(Contents en écriture pour publier, en lecture pour un dépôt privé).') from exc
        raise ValueError(f'GitHub a refusé l’opération (HTTP {exc.code}).') from exc


def lister(token=None):
    resultat = []
    for page in range(1, 11):
        releases = _api(f'/releases?per_page=100&page={page}', token)
        for release in releases:
            if release.get('draft') or release.get('prerelease'):
                continue
            for asset in release.get('assets', []):
                if (asset.get('name', '').endswith(chiffrement.EXTENSION)
                        and asset.get('state') == 'uploaded' and isinstance(asset.get('id'), int)):
                    resultat.append(dict(id=asset['id'], nom=asset['name'], taille=asset.get('size', 0),
                        date=release.get('published_at') or '', release=release.get('tag_name', ''),
                        digest=asset.get('digest') or ''))
        if len(releases) < 100:
            break
    return sorted(resultat, key=lambda a: (a['date'], a['id']), reverse=True)


def _envoyer(fichier, release_id, nom, token):
    """Envoi en flux uniquement au point d'accès fixe GitHub, sans redirection du jeton."""
    connexion = http.client.HTTPSConnection('uploads.github.com', context=github.contexte_ssl(), timeout=120)
    try:
        chemin = f'/repos/{github.DEPOT}/releases/{int(release_id)}/assets?name={quote(nom)}'
        connexion.putrequest('POST', chemin)
        for cle, valeur in {'Authorization': 'Bearer ' + token, 'User-Agent': 'AsyDec',
                            'Content-Type': 'application/octet-stream',
                            'Content-Length': str(fichier.stat().st_size)}.items():
            connexion.putheader(cle, valeur)
        connexion.endheaders()
        with fichier.open('rb') as entree:
            for bloc in iter(lambda: entree.read(chiffrement.BLOC), b''):
                connexion.send(bloc)
        reponse = connexion.getresponse()
        contenu = reponse.read(2_000_000)
        if reponse.status != 201:
            raise ValueError(f'Envoi GitHub refusé (HTTP {reponse.status}). Vérifiez les droits Contents du jeton.')
        asset = json.loads(contenu)
        if asset.get('state') != 'uploaded':
            raise ValueError('GitHub n’a pas confirmé l’envoi du fichier chiffré.')
        return asset
    finally:
        connexion.close()


def publier(source, mot_de_passe, token):
    """Le mot de passe est utilisé localement ; seul le fichier authentifié chiffré est envoyé."""
    if not token or not token.strip():
        raise ValueError('Renseignez un jeton GitHub avec Contents en écriture pour publier.')
    chiffrement.verifier_fichier(source)
    with tempfile.TemporaryDirectory(prefix='asydec-publication-') as d:
        copie = Path(d) / ('sauvegarde' + chiffrement.EXTENSION)
        shutil.copyfile(source, copie)
        # Refuse même un fichier au bon en-tête si son chiffrement n'est pas valide.
        with chiffrement.ouvrir(copie, mot_de_passe):
            pass
        tag = 'sauvegarde-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3)
        nom = 'AsyDec-' + tag + chiffrement.EXTENSION
        release = _api('/releases', token, 'POST', dict(tag_name=tag, target_commitish='main',
            name='Sauvegarde AsyDec chiffrée', draft=True, make_latest='false',
            body='Export complet chiffré. Dans AsyDec : Paramètres › Sauvegarde chiffrée › Rechercher sur GitHub. '
                 'Le mot de passe de sauvegarde est nécessaire pour charger les données. '
                 'Il n’est enregistré ni dans le code ni sur GitHub.'))
        try:
            _envoyer(copie, release['id'], nom, token)
            publiee = _api(f"/releases/{release['id']}", token, 'PATCH', dict(draft=False, make_latest='false'))
        except Exception:
            try:
                _api(f"/releases/{release['id']}", token, 'DELETE')
            except Exception:
                pass  # l'erreur initiale reste visible ; un brouillon éventuel ne devient pas public
            raise
    return publiee['html_url']


def recuperer(asset, mot_de_passe, token=None, racine=None):
    """Demande un mot de passe avant téléchargement, puis prépare l'import après vérification GCM."""
    chiffrement.verifier_mot_de_passe(mot_de_passe)
    identifiant = asset.get('id')
    if type(identifiant) is not int or identifiant <= 0 or not str(asset.get('nom', '')).endswith(chiffrement.EXTENSION):
        raise ValueError('Sauvegarde GitHub non reconnue.')
    if not 0 < asset.get('taille', 0) <= chiffrement.LIMITE:
        raise ValueError('Sauvegarde GitHub trop volumineuse ou vide.')
    with tempfile.TemporaryDirectory(prefix='asydec-reception-') as d:
        cible = Path(d) / ('sauvegarde' + chiffrement.EXTENSION)
        empreinte, taille = hashlib.sha256(), 0
        with github._ouvrir(github.API + f'/releases/assets/{identifiant}', token, True) as entree, cible.open('wb') as sortie:
            for bloc in iter(lambda: entree.read(chiffrement.BLOC), b''):
                taille += len(bloc)
                if taille > chiffrement.LIMITE or taille > asset['taille']:
                    raise ValueError('La taille du téléchargement dépasse celle de la sauvegarde annoncée.')
                empreinte.update(bloc)
                sortie.write(bloc)
        if taille != asset['taille']:
            raise ValueError('Téléchargement incomplet. Aucune donnée chargée.')
        digest = asset.get('digest', '')
        if digest.startswith('sha256:') and digest[7:] != empreinte.hexdigest():
            raise ValueError('Empreinte du téléchargement incorrecte. Aucune donnée chargée.')
        return chiffrement.preparer_import(cible, mot_de_passe, racine=racine)
