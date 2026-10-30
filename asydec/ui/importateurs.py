"""Sélecteur de l'importateur de la déclaration, partagé par l'étape Dossier et les Répartitions."""
from tkinter import ttk

IMPORTATEUR_XML = "Celui du XML du dossier"


def importateur_choisi(app):
    """Importateur sélectionné, ou None pour garder celui du XML (y compris sur une application de test)."""
    lire = getattr(app, "importateur_choisi", None)
    return lire() if callable(lire) else None


def selecteur(parent, app):
    ttk.Label(parent, text="Importateur de la déclaration", style="Doux.TLabel").pack(side="left")
    choix = ttk.Combobox(parent, textvariable=app.var_importateur, state="readonly", width=46)
    choix.pack(side="left", padx=10)
    choix.bind("<<ComboboxSelected>>", lambda _e: app.changer_importateur())
    return choix
