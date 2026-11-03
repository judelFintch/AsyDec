"""Premier démarrage de l’application Mac : récupération facultative de OUTILS."""
from tkinter import Tk, messagebox, filedialog
from asydec import chemins
from asydec.systeme.donnees_installation import importer


def proposer():
    if not chemins.COMPILE or (chemins.CONFIG_LOCAL/'compte.json').exists():
        return
    racine=Tk()
    racine.withdraw()
    try:
        if not messagebox.askyesno('Bienvenue dans AsyDec pour Mac',
            'Voulez-vous récupérer vos données de l’ancienne version ?\n\n'
            'Fermez l’ancienne application puis sélectionnez son dossier OUTILS. '
            'Vos modèles, factures, compte et numéros déjà attribués seront copiés.',parent=racine):
            return
        dossier=filedialog.askdirectory(parent=racine,title='Sélectionnez l’ancien dossier OUTILS')
        if dossier:
            try:
                importer(dossier,chemins.RACINE)
            except Exception as exc:
                messagebox.showerror('Import non effectué',str(exc),parent=racine)
    finally:
        racine.destroy()
