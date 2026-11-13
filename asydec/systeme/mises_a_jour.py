"""Versions GitHub pour macOS et Windows : téléchargement vérifié et installation.

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
_jeton_session = None


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
             'User-Agent':'AsyDec'}
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
    """Trousseau sur Mac, mémoire de session sur Windows ; aucun secret dans les préférences."""
    if sys.platform != 'darwin':
        return _jeton_session
    r=subprocess.run(['/usr/bin/security','find-generic-password','-s','AsyDec GitHub','-a',DEPOT,'-w'],capture_output=True,text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def retenir_token(token):
    """Sur Windows le jeton reste en mémoire pour la session, jamais en clair sur disque."""
    global _jeton_session
    if sys.platform != 'darwin':
        _jeton_session = token
        return 'Jeton conservé pour cette session uniquement.'
    r = subprocess.run(['/usr/bin/security', 'add-generic-password', '-U', '-s', 'AsyDec GitHub',
                        '-a', DEPOT, '-w', token], capture_output=True)
    if r.returncode:
        raise ValueError('Le Trousseau a refusé l’enregistrement du jeton.')
    return 'Jeton enregistré dans le Trousseau.'


# Noms lisibles des versions Mac. M1, M2, M3, M4… partagent le même programme arm64.
TYPES_MAC = {
    'arm64': dict(libelle='Mac Apple Silicon (puces M1, M2, M3, M4…)', fichier='AsyDec-Mac-Apple-Silicon-M1-M2-M3-M4'),
    'x86_64': dict(libelle='Mac Intel', fichier='AsyDec-Mac-Intel'),
}


def type_mac(arch=None):
    arch = arch or architecture()
    return TYPES_MAC.get(arch, dict(libelle=f'Mac {arch}', fichier=f'AsyDec-Mac-{arch}'))['libelle']


def architecture():
    """Cible Windows x64 ou architecture Mac native (même sous Rosetta)."""
    arch=platform.machine()
    if sys.platform == 'win32':
        return 'x64' if arch.lower() in ('amd64', 'x86_64', 'x64', 'arm64', 'aarch64') else arch.lower()
    if arch=='x86_64':
        r=subprocess.run(['/usr/sbin/sysctl','-n','sysctl.proc_translated'],capture_output=True,text=True)
        if r.returncode==0 and r.stdout.strip()=='1':
            return 'arm64'
    return arch


def verifier(token=None):
    windows = sys.platform == 'win32'
    arch = architecture()
    nom = f'AsyDec-windows-{arch}' if windows else f'AsyDec-macos-{arch}'
    nom_binaire = f'AsyDec-Setup-windows-{arch}.exe' if windows else nom + '.zip'
    try:
        if windows:
            # Les publications Windows portent --latest=false : /latest renvoie le Mac.
            release = None
            for page in range(1, 11):
                with _ouvrir(API+f'/releases?per_page=100&page={page}', token) as r:
                    versions = json.loads(r.read(10_000_000))
                for candidate in versions:
                    noms = {a['name'] for a in candidate.get('assets', [])}
                    if not candidate.get('draft') and not candidate.get('prerelease') and {nom+'.json', nom_binaire} <= noms:
                        release = candidate
                        break
                if release is not None or len(versions) < 100:
                    break
            if release is None:
                raise ValueError('Aucune version Windows publiée accessible pour cet ordinateur. '
                                 'Si le dépôt est privé, renseignez un jeton GitHub en lecture seule.')
        else:
            with _ouvrir(API+'/releases/latest',token) as r:
                release=json.loads(r.read(2_000_000))
    except HTTPError as exc:
        if exc.code==404:
            raise ValueError('Aucune version publiée accessible. Si le dépôt est privé, configurez un jeton GitHub en lecture seule.') from exc
        if exc.code == 401:
            raise ValueError('Jeton GitHub invalide ou expiré. Renseignez un jeton en lecture seule ayant accès au dépôt AsyDec.') from exc
        if exc.code == 403:
            raise ValueError('GitHub a refusé la recherche : vérifiez les droits du jeton ou réessayez plus tard si la limite de requêtes est atteinte.') from exc
        raise
    assets={a['name']:a for a in release.get('assets',[])}
    if nom+'.json' not in assets or nom_binaire not in assets:
        raise ValueError('Cette version ne propose pas encore de fichier pour cet ordinateur.')
    meta_asset=assets[nom+'.json']
    with _ouvrir(meta_asset['url'],token,True) as r:
        meta=json.loads(r.read(100_000))
    arch_meta = str(meta.get('architecture', '')).lower()
    arch_valide = arch_meta in ('amd64', 'x86_64', 'x64') if windows else arch_meta == arch
    if not arch_valide or not re.fullmatch(r'[0-9a-f]{64}',meta.get('sha256','')):
        raise ValueError('Métadonnées de mise à jour invalides.')
    if not re.fullmatch(r'[0-9a-f]{40}',meta.get('revision','')) or not isinstance(meta.get('build'),int):
        raise ValueError('Identité de construction invalide.')
    locale=courante()
    disponible=meta['revision']!=locale.get('revision') and meta['build']>locale.get('build',0)
    return dict(meta, disponible=disponible, asset=assets[nom_binaire])


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
    if sys.platform == 'win32':
        return preparer_windows(meta, token)
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
    if sys.platform == 'win32':
        cible = application_windows()
        nouvelle = Path(nouvelle)
        if nouvelle.name != 'AsyDec-Setup-windows-x64.exe' or not nouvelle.is_file():
            raise ValueError('Installateur Windows non reconnu.')
        subprocess.Popen([str(nouvelle), '/NORESTART', '/DIR=' + str(cible.parent)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    app=application_courante()
    subprocess.Popen([sys.executable,'--installer',str(nouvelle),str(app),str(os.getpid())],
                     start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


def application_windows():
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False) or Path(sys.executable).name.lower() != 'asydec.exe':
        raise ValueError('L’installation est disponible dans l’application Windows installée.')
    return Path(sys.executable).resolve()


def preparer_windows(meta, token=None):
    application_windows()
    dossier = Path(tempfile.mkdtemp(prefix='AsyDec-maj-'))
    try:
        setup = dossier / 'AsyDec-Setup-windows-x64.exe'
        h = hashlib.sha256()
        taille = 0
        with _ouvrir(meta['asset']['url'], token, True) as entree, setup.open('wb') as sortie:
            while bloc := entree.read(1024 * 1024):
                taille += len(bloc)
                if taille > 1_000_000_000:
                    raise ValueError('Téléchargement trop volumineux.')
                h.update(bloc)
                sortie.write(bloc)
        if h.hexdigest() != meta['sha256']:
            raise ValueError('Empreinte du téléchargement incorrecte ; installation annulée.')
        with setup.open('rb') as f:
            if f.read(2) != b'MZ':
                raise ValueError('Le téléchargement n’est pas un installateur Windows.')
        return setup
    except Exception:
        shutil.rmtree(dossier, ignore_errors=True)
        raise


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
