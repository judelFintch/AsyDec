"""Envoi d'un PDF à une imprimante du poste, sans boîte de dialogue.

- macOS / Linux : CUPS (`lpstat` pour la liste, `lp` pour l'impression).
- Windows : PowerShell (Get-Printer) et l'application PDF par défaut (verbe « PrintTo »).
"""
from pathlib import Path
import subprocess
import sys

DELAI = 60


class ImpressionImpossible(ValueError):
    """L'impression n'a pas pu être lancée ; le PDF, lui, est enregistré."""


def _executer(commande):
    return subprocess.run(commande, capture_output=True, text=True, timeout=DELAI,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def imprimantes():
    """(noms des imprimantes, imprimante par défaut ou None). Liste vide si aucune n'est installée."""
    try:
        if sys.platform == 'win32':
            r = _executer(['powershell', '-NoProfile', '-Command',
                           'Get-Printer | Select-Object -ExpandProperty Name'])
            noms = [l.strip() for l in r.stdout.splitlines() if l.strip()]
            d = _executer(['powershell', '-NoProfile', '-Command',
                           '(Get-CimInstance Win32_Printer -Filter "Default=true").Name'])
            defaut = d.stdout.strip() or None
            return noms, defaut if defaut in noms else (noms[0] if noms else None)
        r = _executer(['lpstat', '-a'])
        noms = [l.split()[0] for l in r.stdout.splitlines() if l.strip()]
        d = _executer(['lpstat', '-d'])
        defaut = d.stdout.strip().rsplit(':', 1)[-1].strip() if ':' in d.stdout else None
        return noms, defaut if defaut in noms else (noms[0] if noms else None)
    except (OSError, subprocess.TimeoutExpired):
        return [], None


def imprimer(pdf, imprimante=None, copies=1, recto_verso=False, titre=None):
    """Envoie le PDF à l'imprimante ; renvoie un court message de confirmation."""
    pdf = Path(pdf)
    if not pdf.is_file():
        raise ImpressionImpossible(f'PDF introuvable : {pdf}')
    copies = max(1, int(copies))
    try:
        if sys.platform == 'win32':
            cible = f'"{imprimante}"' if imprimante else ''
            verbe = 'PrintTo' if imprimante else 'Print'
            script = (f"$f = '{str(pdf).replace(chr(39), chr(39) * 2)}'; "
                      f"for ($i = 0; $i -lt {copies}; $i++) {{ Start-Process -FilePath $f -Verb {verbe} "
                      + (f"-ArgumentList '{cible}' " if cible else '') + '-WindowStyle Hidden }')
            r = _executer(['powershell', '-NoProfile', '-Command', script])
            if r.returncode != 0:
                raise ImpressionImpossible('Windows n’a pas pu lancer l’impression : '
                                           + (r.stderr or r.stdout).strip()[:300]
                                           + '\nOuvrez le PDF et imprimez-le depuis votre lecteur PDF.')
            return f"Envoyé à {imprimante or 'l’imprimante par défaut'} ({copies} exemplaire(s))."
        commande = ['lp', '-n', str(copies), '-o', 'sides=two-sided-long-edge' if recto_verso else 'sides=one-sided',
                    '-o', 'fit-to-page']
        if imprimante:
            commande += ['-d', imprimante]
        if titre:
            commande += ['-t', titre]
        r = _executer(commande + [str(pdf)])
        if r.returncode != 0:
            raise ImpressionImpossible('L’imprimante a refusé le document : ' + (r.stderr or r.stdout).strip()[:300])
        return f"Envoyé à {imprimante or 'l’imprimante par défaut'} ({copies} exemplaire(s)) · {r.stdout.strip()}"
    except FileNotFoundError:
        raise ImpressionImpossible('Aucun service d’impression trouvé sur ce poste : ouvrez le PDF pour l’imprimer.') from None
    except subprocess.TimeoutExpired:
        raise ImpressionImpossible('Le service d’impression ne répond pas.') from None
