"""Taux de change : confirmation du taux lu dans chaque XML, ou taux saisi qui le remplace."""
from decimal import Decimal
import math
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from asydec.references.import_references import extraire


def variable(app):
    """Taux saisi, commun aux pages et mémorisé dans les préférences ; vide = taux de chaque XML."""
    if getattr(app, "var_taux", None) is None:
        prefs = getattr(app, "prefs", None)
        app.var_taux = tk.StringVar(value=(prefs or {}).get("taux_change", ""))
        if prefs is not None:
            app.var_taux.trace_add("write", lambda *_: prefs.__setitem__("taux_change", app.var_taux.get().strip()))
    return app.var_taux


def taux_choisi(app):
    """Taux saisi (CDF pour 1 USD), ou None pour garder celui du XML. Lève ValueError s'il est illisible."""
    var = getattr(app, "var_taux", None)
    texte = var.get().strip() if var is not None else ""
    if not texte:
        return None
    from asydec.declarations.taux_declaration import lire
    try:
        taux = float(lire(texte))
    except ValueError:
        raise ValueError(f"Taux de change « {texte} » invalide : saisissez un nombre positif (CDF pour 1 USD) "
                         "ou videz le champ pour garder le taux du XML.") from None
    return taux


def selecteur(parent, app):
    ttk.Label(parent, text="Taux CDF/USD", style="Doux.TLabel").pack(side="left", padx=(12, 4))
    champ = ttk.Entry(parent, textvariable=variable(app), width=12, justify="right")
    champ.pack(side="left")
    lu = tk.StringVar()

    def relire(*_):
        texte = variable(app).get().strip()
        if not texte:
            lu.set("(vide = taux du XML)")
            return
        try:
            lu.set(f"= {taux_choisi(app):,.4f} CDF pour 1 USD".replace(",", " "))
        except ValueError:
            lu.set("taux illisible")

    variable(app).trace_add("write", relire)
    relire()
    ttk.Label(parent, textvariable=lu, style="Doux.TLabel").pack(side="left", padx=(4, 0))
    ecrire = getattr(app, "_ecrire_prefs", None)
    if callable(ecrire):
        champ.bind("<FocusOut>", lambda _e: ecrire())
    return champ


def confirmer(app, chemins, parent=None):
    if app.session_verrouillee:
        return False
    # Un taux saisi remplace celui de chaque XML : il est explicite, rien à confirmer.
    saisi = taux_choisi(app) is not None
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
    if not nouveaux or saisi:
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
