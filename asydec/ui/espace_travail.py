"""Choix du dossier de travail (premier lancement, Paramètres) et rangement des fichiers existants."""
from collections import Counter
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from asydec.systeme import espace_travail
from asydec.ui import theme

APERCU = """1 - IMPORTATEURS/<IMPORTATEUR>/
    1 - BASES SYDONIA          XML de base reçus
    2 - DECLARATIONS GENEREES  sorties du générateur
    3 - XML VALIDES            modèles validés téléchargés
    4 - DECLARATIONS REELLES   déclarations SYDONIA comparées
    5 - PDF        6 - FACTURES
2 - RAPPORTS/AAAA-MM/          exports Excel
3 - A TRIER/                   fichiers anciens non reconnus
4 - SAUVEGARDES/"""


def ouvrir_dans_finder(chemin):
    if sys.platform == 'darwin':
        subprocess.run(['open', str(chemin)], check=False)


class FenetreEspaceTravail(tk.Toplevel):
    """Demande le dossier de travail ; Documents/AsyDec est proposé par défaut."""

    def __init__(self, parent, premier_lancement=False):
        super().__init__(parent)
        self.choisi = None
        self.title('Dossier de travail AsyDec')
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        cadre = ttk.Frame(self, padding=20)
        cadre.pack(fill='both', expand=True)
        theme.entete_page(cadre, 'Où AsyDec doit-il ranger vos fichiers ?',
            ('Bienvenue. ' if premier_lancement else '') +
            'Toutes les déclarations, XML validés, PDF, factures et rapports produits par AsyDec seront rangés '
            'dans ce dossier, par importateur et par type. Les données internes du logiciel restent dans OUTILS.')
        texte = tk.Text(cadre, height=9, width=70, font=('Menlo', 11), relief='flat', bg=theme.FOND_LATERAL,
                        padx=10, pady=8)
        texte.insert('1.0', APERCU)
        texte.configure(state='disabled')
        texte.pack(fill='x', pady=(0, 12))
        ligne = ttk.Frame(cadre)
        ligne.pack(fill='x')
        self.var_dossier = tk.StringVar(value=str(espace_travail.racine() or espace_travail.DEFAUT))
        ttk.Entry(ligne, textvariable=self.var_dossier, width=60).pack(side='left', fill='x', expand=True)
        theme.bouton(ligne, 'Choisir…', self.parcourir).pack(side='left', padx=(8, 0))
        self.message = theme.Message(cadre)
        self.message.pack(fill='x', pady=8)
        boutons = ttk.Frame(cadre)
        boutons.pack(fill='x')
        theme.bouton(boutons, 'Utiliser ce dossier', self.valider, principal=True).pack(side='right')
        theme.bouton(boutons, 'Plus tard' if premier_lancement else 'Annuler', self.destroy).pack(side='right', padx=8)
        if premier_lancement:
            ttk.Label(boutons, text='« Plus tard » : la question sera reposée au prochain lancement.',
                      style='Doux.TLabel').pack(side='left')
        self.grab_set()

    def parcourir(self):
        dossier = filedialog.askdirectory(parent=self, title='Dossier de travail AsyDec', mustexist=False,
                                          initialdir=str(espace_travail.DEFAUT.parent))
        if dossier:
            self.var_dossier.set(dossier)

    def valider(self):
        try:
            self.choisi = espace_travail.definir(self.var_dossier.get().strip())
        except (OSError, ValueError) as exc:
            self.message.afficher('erreur', 'Dossier inutilisable', [str(exc)])
            return
        self.destroy()


def choisir(app, premier_lancement=False):
    """Fenêtre de choix, puis proposition de ranger les fichiers existants. Renvoie le dossier ou None."""
    fenetre = FenetreEspaceTravail(app, premier_lancement)
    app.wait_window(fenetre)
    if fenetre.choisi is None:
        return None
    try:
        plan = [p for p in planifier(app) if not p['deja']]
    except Exception as exc:  # noqa: BLE001 - le dossier est choisi ; le rangement reste possible plus tard
        messagebox.showwarning('Fichiers existants', f'Analyse impossible pour le moment : {exc}', parent=app)
        return fenetre.choisi
    if plan and messagebox.askyesno('Fichiers existants',
            f'{len(plan)} fichier(s) existant(s) peuvent être copiés et rangés dans ce dossier '
            '(les originaux restent en place).\n\nVoir l’aperçu maintenant ?', parent=app):
        app.wait_window(FenetreRangement(app, plan))
    return fenetre.choisi


def planifier(app):
    from asydec.declarations import rangement_existants
    return rangement_existants.planifier(table_imp=getattr(app, 'table_imp', None))


class FenetreRangement(tk.Toplevel):
    """Aperçu des copies prévues, puis copie sur confirmation."""

    def __init__(self, parent, plan):
        from asydec.declarations import rangement_existants
        super().__init__(parent)
        self.plan = plan
        self.title('Ranger mes fichiers existants')
        self.geometry('1240x640')
        self.transient(parent.winfo_toplevel())
        cadre = ttk.Frame(self, padding=16)
        cadre.pack(fill='both', expand=True)
        racine = espace_travail.racine()
        theme.entete_page(cadre, 'Ranger mes fichiers existants',
            f'Copie dans {racine}. Les originaux restent à leur place ; rien n’est écrasé. '
            'Le type est déduit du contenu du XML (déclaration réelle, importateur), puis du dossier d’origine.')
        comptes = Counter(rangement_existants.LIBELLES[p['categorie']] for p in plan)
        ttk.Label(cadre, text=f'{len(plan)} fichier(s) : ' + ', '.join(f'{n} {t.lower()}' for t, n in comptes.most_common()),
                  style='Section.TLabel', wraplength=1180).pack(anchor='w', pady=(0, 6))
        zone, table = theme.tableau(cadre, [
            ('type', 'Type', 140, 'w'), ('importateur', 'Importateur', 170, 'w'), ('fichier', 'Fichier', 300, 'w'),
            ('destination', 'Rangé dans', 330, 'w'), ('raison', 'Pourquoi', 280, 'w')], 16)
        zone.pack(fill='both', expand=True)
        table.tag_configure('a_trier', foreground=theme.ALERTE)
        for k, p in enumerate(plan):
            table.insert('', 'end', iid=str(k), tags=(p['categorie'],), values=(
                rangement_existants.LIBELLES[p['categorie']], p['importateur'] or '—', p['source'].name,
                str(p['destination'].parent.relative_to(racine)), p['raison']))
        self.message = theme.Message(cadre)
        self.message.pack(fill='x', pady=8)
        boutons = ttk.Frame(cadre)
        boutons.pack(fill='x')
        theme.bouton(boutons, 'Fermer', self.destroy).pack(side='right')
        self.copier_bouton = theme.bouton(boutons, 'Copier et ranger', self.copier, principal=True,
                                          state='normal' if plan else 'disabled')
        self.copier_bouton.pack(side='right', padx=8)
        theme.bouton(boutons, 'Ouvrir le dossier de travail', lambda: ouvrir_dans_finder(racine)).pack(side='left')

    def copier(self):
        from asydec.declarations import rangement_existants
        try:
            copies, compte_rendu = rangement_existants.executer(self.plan)
        except OSError as exc:
            self.message.afficher('erreur', 'Rangement interrompu', [str(exc), 'Relancez : les fichiers déjà copiés ne le seront pas deux fois.'])
            return
        self.copier_bouton.configure(state='disabled')
        lignes = ['Les originaux sont restés en place.']
        if compte_rendu is not None:
            lignes.append(f'Compte rendu : {espace_travail.relatif(compte_rendu)}')
        self.message.afficher('ok', f'{copies} fichier(s) copié(s) et rangé(s)', lignes)
