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
    sys.path.insert(0, str(RACINE))
    from asydec.systeme.mises_a_jour import TYPES_MAC
    if arch not in TYPES_MAC:
        raise SystemExit(f'Architecture non prise en charge : {arch}')
    # Un Python Intel lancé sous Rosetta sur une puce M produirait une version Intel étiquetée par erreur.
    rosetta = subprocess.run(['/usr/sbin/sysctl','-n','sysctl.proc_translated'],capture_output=True,text=True)
    if rosetta.stdout.strip() == '1' and os.environ.get('ASYDEC_ACCEPTER_ROSETTA') != '1':
        raise SystemExit('Python tourne sous Rosetta : la version produite serait Intel. Utilisez un Python arm64 '
                         '(ou ASYDEC_ACCEPTER_ROSETTA=1 pour construire volontairement la version Intel).')
    if build == 0 and subprocess.check_output(['git','status','--porcelain'],cwd=RACINE,text=True).strip():
        revision = 'local-' + revision[:12]
    meta = {'revision':revision,'build':build,'version':f'1.0.{build}','architecture':arch,
            'type_mac':TYPES_MAC[arch]['libelle']}
    (RACINE/'asydec/construction.json').write_text(json.dumps(meta))
    commande=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--onedir',
        '--name','AsyDec','--osx-bundle-identifier','com.asydec.desktop','--paths',str(RACINE),
        '--collect-all','sv_ttk','--add-data',f'{RACINE}/asydec/construction.json:asydec',
        *(['--add-data', str(RACINE/'ressources/cvi/CVI-modele.docx')+':ressources/cvi']
          if (RACINE/'ressources/cvi/CVI-modele.docx').is_file() else []),
        *(['--add-data', str(RACINE/'ressources/declaration/Declaration-modele.docx')+':ressources/declaration']
          if (RACINE/'ressources/declaration/Declaration-modele.docx').is_file() else []),
        '--add-data', str(RACINE/'ressources/factures')+':ressources/factures',
        '--collect-all','rapidocr_onnxruntime','--collect-all','onnxruntime',
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
    info.update(CFBundleShortVersionString=meta['version'],CFBundleVersion=meta['version'],
                # Sans cette phrase, macOS refuse sans rien demander le pilotage de Word (PDF des factures).
                NSAppleEventsUsageDescription='AsyDec utilise Microsoft Word pour créer le PDF de vos factures '
                                              'et documents, avec la même mise en page que le Word.')
    with plist.open('wb') as f:
        plistlib.dump(info,f)
    subprocess.run(['/usr/bin/codesign','--force','--deep','--sign',os.environ.get('ASYDEC_CODESIGN_IDENTITY','-'),str(app)],check=True)
    # Le programme principal doit contenir exactement l'architecture annoncée.
    binaire = app/'Contents/MacOS/AsyDec'
    contenues = subprocess.check_output(['/usr/bin/lipo','-archs',str(binaire)],text=True).split()
    if arch not in contenues:
        raise SystemExit(f'Le programme construit contient {contenues}, pas {arch}.')
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
    # Copie au nom explicite pour les utilisateurs ; le nom technique reste celui des mises à jour automatiques.
    shutil.copyfile(dmg, RACINE/f"dist/{TYPES_MAC[arch]['fichier']}.dmg")
    archive=RACINE/f'dist/AsyDec-macos-{arch}.zip'
    subprocess.run(['/usr/bin/ditto','-c','-k','--sequesterRsrc','--keepParent',str(app),str(archive)],check=True)
    with archive.open('rb') as f:
        meta.update(nom=archive.name,sha256=hashlib.file_digest(f,'sha256').hexdigest())
    (RACINE/f'dist/AsyDec-macos-{arch}.json').write_text(json.dumps(meta,indent=2))
    print(app)

if __name__=='__main__':
    main()
