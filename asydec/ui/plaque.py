"""Plaque à inscrire dans le XML : un seul champ, modifiable depuis chaque page de génération."""
import tkinter as tk
from tkinter import ttk

from asydec.calcul import moteur

AIDE = "Vide = plaque du XML. Ex. : T546ECQ/T618ECT"


def variable(app):
    """Plaque saisie, commune à toutes les pages ; vide = plaque du XML de base."""
    if getattr(app, "var_plaque", None) is None:
        app.var_plaque = tk.StringVar()
        bandeau = getattr(app, "afficher_bandeau", None)
        if callable(bandeau):
            app.var_plaque.trace_add("write", lambda *_: bandeau() if getattr(app, "info", None) else None)
    return app.var_plaque


def lire(app):
    """Plaque saisie, ou chaîne vide (aussi sur une application sans champ plaque)."""
    var = getattr(app, "var_plaque", None)
    return var.get().strip() if var is not None else ""


def remettre(app, valeur):
    """Rétablit une saisie, sans créer le champ s'il n'existe pas."""
    var = getattr(app, "var_plaque", None)
    if var is not None:
        var.set(valeur)


def texte_plaque(app):
    """Plaque qui sera inscrite : la saisie normalisée, sinon celle du XML (« — » si aucune)."""
    saisie = lire(app)
    if saisie:
        try:
            return f"{moteur.normaliser_plaque(saisie)} (saisie)"
        except ValueError:
            return f"{saisie} (invalide)"
    info = getattr(app, "info", None) or {}
    return info.get("camion") or "—"


def selecteur(parent, app, apres=None, aide=True):
    """Champ plaque ; apres() est appelé quand la saisie est validée (Entrée ou sortie du champ)."""
    ttk.Label(parent, text="Plaque", style="Doux.TLabel").pack(side="left", padx=(0, 4))
    champ = ttk.Entry(parent, textvariable=variable(app), width=22)
    champ.pack(side="left")
    if aide:
        ttk.Label(parent, text=AIDE, style="Doux.TLabel").pack(side="left", padx=(6, 0))
    if apres is not None:
        champ.bind("<Return>", lambda _e: apres())
        champ.bind("<FocusOut>", lambda _e: apres())
    return champ
