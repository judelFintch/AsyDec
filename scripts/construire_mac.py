"""Construit une .app autonome, sans données personnelles. À exécuter sous macOS."""
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys

RACINE = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != 'darwin':
        raise SystemExit('La construction Mac doit être effectuée sur macOS.')
    revision = os.environ.get('GITHUB_SHA') or subprocess.check_output(['git','rev-parse','HEAD'],cwd=RACINE,text=True).strip()
    build = int(os.environ.get('GITHUB_RUN_NUMBER','0'))
    arch = platform.machine()
    if build == 0 and subprocess.check_output(['git','status','--porcelain'],cwd=RACINE,text=True).strip():
        revision = 'local-' + revision[:12]
    meta = {'revision':revision,'build':build,'version':f'1.0.{build}','architecture':arch}
    (RACINE/'asydec/construction.json').write_text(json.dumps(meta))
    commande=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--onedir',
        '--name','AsyDec','--osx-bundle-identifier','com.asydec.desktop','--paths',str(RACINE),
        '--collect-all','sv_ttk','--add-data',f'{RACINE}/asydec/construction.json:asydec',
        '--distpath',str(RACINE/'dist'),'--workpath',str(RACINE/'build'),
        '--specpath',str(RACINE/'packaging'),str(RACINE/'packaging/lancer.py')]
    if os.environ.get('ASYDEC_CODESIGN_IDENTITY'):
        commande[3:3]=['--codesign-identity',os.environ['ASYDEC_CODESIGN_IDENTITY']]
    env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(RACINE/'build/pyinstaller-cache'))
    subprocess.run(commande,cwd=RACINE,check=True,env=env)
    app=RACINE/'dist/AsyDec.app'
    plist=app/'Contents/Info.plist'
    with plist.open('rb') as f:
        info=plistlib.load(f)
    info.update(CFBundleShortVersionString=meta['version'],CFBundleVersion=meta['version'])
    with plist.open('wb') as f:
        plistlib.dump(info,f)
    subprocess.run(['/usr/bin/codesign','--force','--deep','--sign',os.environ.get('ASYDEC_CODESIGN_IDENTITY','-'),str(app)],check=True)
    # Image d’installation : glisser AsyDec vers Applications.
    contenu = RACINE/'build/dmg'
    if contenu.exists():
        shutil.rmtree(contenu)
    contenu.mkdir(parents=True)
    subprocess.run(['/usr/bin/ditto', str(app), str(contenu/'AsyDec.app')], check=True)
    (contenu/'Applications').symlink_to('/Applications')
    dmg = RACINE/f'dist/AsyDec-macos-{arch}.dmg'
    subprocess.run(['/usr/bin/hdiutil', 'create', '-ov', '-volname', 'AsyDec',
                    '-srcfolder', str(contenu), '-format', 'UDZO', str(dmg)], check=True)
    archive=RACINE/f'dist/AsyDec-macos-{arch}.zip'
    subprocess.run(['/usr/bin/ditto','-c','-k','--sequesterRsrc','--keepParent',str(app),str(archive)],check=True)
    with archive.open('rb') as f:
        meta.update(nom=archive.name,sha256=hashlib.file_digest(f,'sha256').hexdigest())
    (RACINE/f'dist/AsyDec-macos-{arch}.json').write_text(json.dumps(meta,indent=2))
    print(app)

if __name__=='__main__':
    main()
