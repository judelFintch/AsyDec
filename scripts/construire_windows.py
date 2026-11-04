"""Construit l’application autonome puis son setup Inno Setup sous Windows."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

RACINE = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != 'win32':
        raise SystemExit('La construction Windows doit être effectuée sur Windows.')
    revision = os.environ.get('GITHUB_SHA') or subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=RACINE, text=True).strip()
    build = int(os.environ.get('GITHUB_RUN_NUMBER', '0'))
    meta = {'revision': revision, 'build': build, 'version': f'1.0.{build}',
            'architecture': platform.machine()}
    (RACINE/'asydec/construction.json').write_text(json.dumps(meta), encoding='utf-8')
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed',
        '--onedir', '--name', 'AsyDec', '--paths', str(RACINE), '--collect-all', 'sv_ttk',
        '--add-data', f'{RACINE}/asydec/construction.json;asydec',
        '--distpath', str(RACINE/'dist'), '--workpath', str(RACINE/'build'),
        '--specpath', str(RACINE/'packaging'), str(RACINE/'packaging/lancer.py')
    ], cwd=RACINE, check=True)
    compilateur = (shutil.which('ISCC') or
                   str(Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)'))/
                       'Inno Setup 6/ISCC.exe'))
    subprocess.run([compilateur, f'/DAppVersion={meta["version"]}',
                    str(RACINE/'packaging/windows.iss')], cwd=RACINE, check=True)
    setup = RACINE/'dist/AsyDec-Setup-windows-x64.exe'
    with setup.open('rb') as f:
        meta.update(nom=setup.name, sha256=hashlib.file_digest(f, 'sha256').hexdigest())
    (RACINE/'dist/AsyDec-windows-x64.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    print(setup)


if __name__ == '__main__':
    main()
