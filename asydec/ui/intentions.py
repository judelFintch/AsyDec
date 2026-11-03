"""Sélecteur de l'intention de génération, partagé par l'étape Articles et les Répartitions."""
import tkinter as tk
from tkinter import ttk

from asydec.calcul.variantes import INTENTIONS

PAR_LIBELLE = {libelle: cle for cle, libelle in INTENTIONS.items()}


def variable(app):
    """Variable commune aux pages (libellé affiché), créée au premier besoin."""
    if getattr(app, "var_intention", None) is None:
        app.var_intention = tk.StringVar(value=INTENTIONS["proche"])
    return app.var_intention


def intention_choisie(app):
    """Clé de l'intention choisie ; « proche » sur une application sans sélecteur (tests)."""
    var = getattr(app, "var_intention", None)
    return PAR_LIBELLE.get(var.get(), "proche") if var is not None else "proche"


def selecteur(parent, app):
    ttk.Label(parent, text="Intention", style="Doux.TLabel").pack(side="left", padx=(12, 4))
    choix = ttk.Combobox(parent, textvariable=variable(app), state="readonly", width=26,
                         values=list(INTENTIONS.values()))
    choix.pack(side="left")
    return choix
