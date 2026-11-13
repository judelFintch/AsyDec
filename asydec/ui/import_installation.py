"""Premier démarrage et import en attente : reprise des données d'une autre machine."""
from tkinter import Tk, messagebox, filedialog, simpledialog
from asydec import chemins
from asydec.systeme import transfert


def proposer():
    """Installation sans compte : propose de reprendre un export .asydec ou un ancien dossier OUTILS."""
    if not chemins.COMPILE or (chemins.CONFIG_LOCAL/'compte.json').exists():
        return
    racine=Tk()
    racine.withdraw()
    try:
        choix=messagebox.askyesnocancel('Bienvenue dans AsyDec',
            'Voulez-vous reprendre les données d’une autre machine ?\n\n'
            'Oui : un export .asydec ou une sauvegarde chiffrée .asydec.enc.\n'
            'Non : un ancien dossier OUTILS copié depuis l’autre machine.\n'
            'Annuler : commencer avec une installation vide.',parent=racine)
        if choix is None:
            return
        if choix:
            source=filedialog.askopenfilename(parent=racine,title='Export AsyDec',
                                              filetypes=[('Export AsyDec','*.asydec *.asydec.enc')])
        else:
            source=filedialog.askdirectory(parent=racine,title='Sélectionnez l’ancien dossier OUTILS')
        if not source:
            return
        try:
            if choix and source.endswith('.asydec.enc'):
                from asydec.systeme import sauvegarde_chiffree
                mot_de_passe = simpledialog.askstring('Sauvegarde chiffrée',
                    'Mot de passe de la sauvegarde (pas le mot de passe du compte AsyDec) :', show='•', parent=racine)
                if mot_de_passe is None:
                    return
                sauvegarde_chiffree.preparer_import(source, mot_de_passe)
                transfert.appliquer_en_attente()
                messagebox.showinfo('Données reprises', 'La sauvegarde a été déchiffrée et chargée. '
                    'Connectez-vous avec le compte de l’ancienne machine.', parent=racine)
                return
            if choix and transfert.lire(source)['type']=='kit':
                # Kit d'un collègue : modèles seulement ; le compte sera créé ensuite.
                bilan=transfert.importer_modeles(source)
                bilan.pop('deja_presents',None)
                messagebox.showinfo('Modèles importés','Ajoutés :\n'+transfert.decrire(bilan)
                                    +'\n\nCréez maintenant votre compte AsyDec.',parent=racine)
                return
            transfert.preparer_import_complet(source)
            transfert.appliquer_en_attente()
            messagebox.showinfo('Données reprises','Les données ont été importées. '
                                'Connectez-vous avec le compte de l’ancienne machine.',parent=racine)
        except Exception as exc:
            transfert.annuler_en_attente()
            messagebox.showerror('Import non effectué',str(exc),parent=racine)
    finally:
        racine.destroy()


def appliquer_en_attente():
    """Installe un import complet préparé depuis Paramètres, avant toute connexion (aucune base ouverte)."""
    if transfert.en_attente() is None:
        return
    racine=Tk()
    racine.withdraw()
    try:
        try:
            mise_de_cote=transfert.appliquer_en_attente()
        except Exception as exc:
            if messagebox.askyesno('Import non installé',
                                   f'Les données importées n’ont pas pu être installées : {exc}\n\n'
                                   'Vos données actuelles sont inchangées.\n\n'
                                   'Abandonner cet import ? (Non : réessayer au prochain démarrage, après avoir '
                                   'fermé les autres fenêtres AsyDec.)',icon='warning',parent=racine):
                transfert.annuler_en_attente()
            return
        messagebox.showinfo('Données importées','Les données importées sont installées.\n\n'
                            f'Anciennes données mises de côté :\n{mise_de_cote}',parent=racine)
    finally:
        racine.destroy()
