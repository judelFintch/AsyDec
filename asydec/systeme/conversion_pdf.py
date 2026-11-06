"""Conversion d'un document Word (.docx) en PDF identique, par Microsoft Word lui-même.

Seul Word reproduit fidèlement nos modèles (zones de texte, images, tampons, polices). Sans Word,
la conversion est refusée avec un message clair : le .docx reste la référence.

- macOS : Word est « bac à sable » et ne lit librement que son propre dossier. Le .docx y est copié,
  converti par AppleScript, puis le PDF est rapporté à côté du .docx. La première fois, macOS demande
  d'autoriser AsyDec à contrôler Microsoft Word.
- Windows : Word est piloté par COM depuis PowerShell.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import uuid

DELAI = 180  # secondes : Word peut mettre du temps à démarrer
WORD_MAC = Path('/Applications/Microsoft Word.app')
DOSSIER_WORD_MAC = Path.home() / 'Library' / 'Containers' / 'com.microsoft.Word' / 'Data' / 'Documents' / 'AsyDec-conversion'

SCRIPT_MAC = '''on run argv
	set entree to item 1 of argv
	set sortie to item 2 of argv
	tell application "Microsoft Word"
		set avant to count of documents
		open (POSIX file entree)
		set n to 0
		repeat until (count of documents) > avant or n > 120
			delay 0.5
			set n to n + 1
		end repeat
		if (count of documents) = avant then error "Word n'a pas ouvert le document."
		set doc to document 1
		save as doc file name sortie file format format PDF
		close doc saving no
	end tell
	return "ok"
end run
'''

SCRIPT_WINDOWS = r'''
param([string]$entree, [string]$sortie)
$ErrorActionPreference = 'Stop'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
  $doc = $word.Documents.Open($entree, $false, $true)
  $doc.SaveAs([ref]$sortie, [ref]17)
  $doc.Close(0)
} finally { $word.Quit() }
'''


class ConversionImpossible(ValueError):
    """Le PDF n'a pas pu être créé ; le .docx, lui, est intact."""


def disponible():
    """True si Microsoft Word est présent pour convertir."""
    if sys.platform == 'darwin':
        return WORD_MAC.is_dir()
    if sys.platform == 'win32':
        return shutil.which('powershell') is not None
    return False


def docx_vers_pdf(docx, pdf=None):
    """Crée le PDF du .docx (même dossier et même nom par défaut) ; renvoie son chemin.
    ConversionImpossible si Word est absent, refuse l'autorisation ou échoue."""
    docx = Path(docx)
    pdf = Path(pdf) if pdf else docx.with_suffix('.pdf')
    if not docx.is_file():
        raise ConversionImpossible(f'Document Word introuvable : {docx}')
    if not disponible():
        raise ConversionImpossible('Microsoft Word n’est pas installé sur ce poste : PDF non créé (le Word est enregistré).')
    if sys.platform == 'darwin':
        _mac(docx, pdf)
    else:
        _windows(docx, pdf)
    if not pdf.is_file() or pdf.stat().st_size == 0:
        raise ConversionImpossible('Word n’a pas produit le PDF.')
    return pdf


def _mac(docx, pdf):
    DOSSIER_WORD_MAC.mkdir(parents=True, exist_ok=True)
    nom = uuid.uuid4().hex
    entree, sortie = DOSSIER_WORD_MAC / f'{nom}.docx', DOSSIER_WORD_MAC / f'{nom}.pdf'
    shutil.copy2(docx, entree)
    try:
        resultat = subprocess.run(['osascript', '-', str(entree), str(sortie)], input=SCRIPT_MAC, text=True,
                                  capture_output=True, timeout=DELAI)
        if resultat.returncode != 0 or not sortie.is_file():
            message = (resultat.stderr or resultat.stdout).strip()
            if '-1743' in message or 'autoris' in message.lower() or 'not authorized' in message.lower():
                raise ConversionImpossible(
                    'macOS n’autorise pas AsyDec à piloter Microsoft Word. Autorisez-le dans Réglages Système › '
                    'Confidentialité et sécurité › Automatisation, puis recommencez.')
            raise ConversionImpossible(f'Word n’a pas pu créer le PDF : {message or "erreur inconnue"}')
        pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(sortie), str(pdf))
    except subprocess.TimeoutExpired:
        raise ConversionImpossible('Word ne répond pas : PDF non créé.') from None
    finally:
        for f in (entree, sortie):
            try:
                f.unlink()
            except OSError:
                pass


def _windows(docx, pdf):
    with tempfile.TemporaryDirectory() as dossier:
        script = Path(dossier) / 'convertir.ps1'
        script.write_text(SCRIPT_WINDOWS, encoding='utf-8')
        try:
            resultat = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
                                       str(docx.resolve()), str(pdf.resolve())], capture_output=True, text=True,
                                      timeout=DELAI, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired:
            raise ConversionImpossible('Word ne répond pas : PDF non créé.') from None
        if resultat.returncode != 0:
            raise ConversionImpossible('Word n’a pas pu créer le PDF : ' + (resultat.stderr or resultat.stdout).strip()[:300])
