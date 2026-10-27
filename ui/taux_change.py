"""Confirmation du taux réellement lu dans chaque XML, sans réglage fiscal implicite."""
from decimal import Decimal
from pathlib import Path
from tkinter import messagebox
from import_references import extraire


def confirmer(app, chemins, parent=None):
    if app.session_verrouillee:
        return False
    deja = getattr(app, '_taux_change_confirmes', set())
    nouveaux = {}
    for chemin in chemins:
        document = extraire(Path(chemin).read_bytes())
        devise = document['document']['devise']
        brut = document['valorisation']['taux_change']
        taux = Decimal(brut) if brut is not None else None
        if not devise or taux is None or not taux.is_finite() or taux <= 0:
            raise ValueError(f'{Path(chemin).name} : devise et taux de change fini strictement positif requis.')
        cle = (str(Path(chemin).resolve()), devise, str(taux.normalize()))
        if cle not in deja:
            nouveaux[cle] = f'{Path(chemin).name} : 1 {devise} = {taux} CDF'
    if not nouveaux:
        return True
    taux_distincts = sorted({f'1 {cle[1]} = {format(Decimal(cle[2]), 'f')} CDF' for cle in nouveaux})
    texte = ('Les prédictions utilisent les taux inscrits dans leurs XML de base, sans taux global configuré.\n\n'
             + '\n'.join(taux_distincts) + '\n\n'
             + '\n'.join(list(nouveaux.values())[:8])
             + (f'\n… {len(nouveaux)-8} autre(s) XML.' if len(nouveaux)>8 else '')
             + '\n\nLes taxes globales sont reprises du XML de base. Confirmer ces taux pour les calculs ?')
    if not messagebox.askyesno('Confirmer les taux de change utilisés', texte, parent=parent or app):
        return False
    app._taux_change_confirmes = deja | set(nouveaux)
    return True
