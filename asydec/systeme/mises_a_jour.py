"""Versions GitHub pour macOS : téléchargement vérifié et remplacement du .app.

Les données utilisateur sont ailleurs. Aucune mise à jour n'est obligatoire.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler
from zipfile import ZipFile

from asydec.systeme.version import courante

DEPOT = 'judelFintch/AsyDec'
API = f'https://api.github.com/repos/{DEPOT}'


class Redirection(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlparse(newurl).scheme != 'https':
            raise ValueError('Redirection non sécurisée refusée.')
        nouvelle = super().redirect_request(req,fp,code,msg,headers,newurl)
        if nouvelle is not None and urlparse(newurl).hostname != 'api.github.com':
            nouvelle.remove_header('Authorization')
        return nouvelle


def _ouvrir(url, token=None, binaire=False):
    if urlparse(url).scheme != 'https' or urlparse(url).hostname != 'api.github.com':
        raise ValueError('Adresse de mise à jour non autorisée.')
    headers={'Accept':'application/octet-stream' if binaire else 'application/vnd.github+json',
             'User-Agent':'AsyDec-macOS'}
    if token:
        headers['Authorization']='Bearer '+token
    contexte = ssl.create_default_context()
    try:
        import certifi
        contexte.load_verify_locations(certifi.where())
    except ImportError:
        pass
    return build_opener(Redirection(),HTTPSHandler(context=contexte)).open(Request(url,headers=headers),timeout=25)


def token_github():
    """Compte utilisateur du Trousseau ; aucun secret dans le code ni les préférences."""
    r=subprocess.run(['/usr/bin/security','find-generic-password','-s','AsyDec GitHub','-a',DEPOT,'-w'],capture_output=True,text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def verifier(token=None):
    try:
        with _ouvrir(API+'/releases/latest',token) as r:
            release=json.loads(r.read(2_000_000))
    except HTTPError as exc:
        if exc.code==404:
            raise ValueError('Aucune version publiée accessible. Si le dépôt est privé, configurez un jeton GitHub en lecture seule.') from exc
        raise
    arch=platform.machine()
    nom=f'AsyDec-macos-{arch}'
    assets={a['name']:a for a in release.get('assets',[])}
    if nom+'.json' not in assets or nom+'.zip' not in assets:
        raise ValueError('Cette version ne propose pas encore de fichier pour ce type de Mac.')
    meta_asset=assets[nom+'.json']
    with _ouvrir(meta_asset['url'],token,True) as r:
        meta=json.loads(r.read(100_000))
    if meta.get('architecture')!=arch or not re.fullmatch(r'[0-9a-f]{64}',meta.get('sha256','')):
        raise ValueError('Métadonnées de mise à jour invalides.')
    if not re.fullmatch(r'[0-9a-f]{40}',meta.get('revision','')) or not isinstance(meta.get('build'),int):
        raise ValueError('Identité de construction invalide.')
    locale=courante()
    disponible=meta['revision']!=locale.get('revision') and meta['build']>locale.get('build',0)
    return dict(meta, disponible=disponible, asset=assets[nom+'.zip'])


def verifier_zip(chemin):
    """Accepte les liens internes de frameworks, jamais une écriture hors du .app."""
    with ZipFile(chemin) as z:
        if sum(i.file_size for i in z.infolist())>2_000_000_000:
            raise ValueError('Archive trop volumineuse.')
        for i in z.infolist():
            p=PurePosixPath(i.filename)
            if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0] not in ('AsyDec.app','__MACOSX'):
                raise ValueError('Chemin inattendu dans la mise à jour.')
            if (i.external_attr >> 16) & 0o170000 == 0o120000:
                cible=z.read(i).decode('utf-8')
                chemin_relatif=os.path.normpath(str(p.parent / cible))
                if PurePosixPath(cible).is_absolute() or not chemin_relatif.startswith('AsyDec.app/'):
                    raise ValueError('Lien sortant du .app refusé.')


def application_courante():
    if not getattr(sys,'frozen',False) or sys.platform!='darwin':
        raise ValueError('L’installation est disponible dans l’application Mac compilée.')
    app=Path(sys.executable).resolve().parents[2]
    if app.name!='AsyDec.app':
        raise ValueError('Emplacement de l’application non reconnu.')
    return app


def preparer(meta, token=None):
    app=application_courante()
    if not os.access(app.parent,os.W_OK):
        raise ValueError('Déplacez AsyDec dans votre dossier Applications utilisateur pour autoriser sa mise à jour.')
    dossier=Path(tempfile.mkdtemp(prefix='.AsyDec-maj-',dir=app.parent))
    try:
        archive=dossier/'application.zip'
        h=hashlib.sha256()
        taille=0
        with _ouvrir(meta['asset']['url'],token,True) as r, archive.open('wb') as f:
            while bloc:=r.read(1024*1024):
                taille+=len(bloc)
                if taille>1_000_000_000:
                    raise ValueError('Téléchargement trop volumineux.')
                h.update(bloc)
                f.write(bloc)
        if h.hexdigest()!=meta['sha256']:
            raise ValueError('Empreinte du téléchargement incorrecte ; installation annulée.')
        verifier_zip(archive)
        extraction=dossier/'extraction'
        subprocess.run(['/usr/bin/ditto','-x','-k',str(archive),str(extraction)],check=True,capture_output=True)
        nouvelle=extraction/'AsyDec.app'
        executable=nouvelle/'Contents/MacOS/AsyDec'
        if not executable.is_file():
            raise ValueError('L’archive ne contient pas une application AsyDec.')
        subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(nouvelle)],check=True,capture_output=True)
        # Ne lance pas de code avant la demande explicite d’installation.
        archive.unlink()
        return nouvelle
    except Exception:
        shutil.rmtree(dossier,ignore_errors=True)
        raise


def lancer_installation(nouvelle):
    app=application_courante()
    subprocess.Popen([sys.executable,'--installer',str(nouvelle),str(app),str(os.getpid())],
                     start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


def installer(nouvelle, cible, pid):
    """Processus auxiliaire : attend la fermeture, conserve un retour arrière."""
    nouvelle,cible=Path(nouvelle).resolve(),Path(cible).resolve()
    if cible.name!='AsyDec.app' or nouvelle.name!='AsyDec.app' or nouvelle.parent.parent.parent!=cible.parent or not nouvelle.parent.parent.name.startswith('.AsyDec-maj-'):
        raise ValueError('Emplacements d’installation invalides.')
    limite=time.monotonic()+60
    while time.monotonic()<limite:
        try:
            os.kill(pid,0)
        except ProcessLookupError:
            break
        time.sleep(.3)
    else:
        return
    sauvegarde=cible.parent/'AsyDec-version-precedente.app'
    if sauvegarde.exists():
        shutil.rmtree(sauvegarde)
    os.replace(cible,sauvegarde)
    try:
        os.replace(nouvelle,cible)
        subprocess.run(['/usr/bin/open',str(cible)],check=True)
    except Exception:
        if cible.exists():
            shutil.rmtree(cible)
        os.replace(sauvegarde,cible)
        subprocess.run(['/usr/bin/open',str(cible)],check=False)
        raise
    finally:
        shutil.rmtree(nouvelle.parent.parent,ignore_errors=True)
