"""Paramètres et reset : ne modifie pas le module de références."""
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from asydec.systeme import gestion_locale as local
from asydec.ui import theme

LIBELLES = {'dossier': 'Dossier', 'repartitions': 'Répartitions', 'ratios': 'Récupération des ratios',
            'etude': 'Étude des XML', 'historique': 'Historique', 'parametres': 'Paramètres'}


class PageParametres(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.derniere_sauvegarde = None
        theme.entete_page(self, 'Paramètres', 'Personnalisez votre outil, gérez votre compte et remettez les données de travail à zéro.')
        onglets = ttk.Notebook(self)
        onglets.pack(fill='both', expand=True)
        general = ttk.Frame(onglets, padding=18)
        compte = ttk.Frame(onglets, padding=18)
        reset = ttk.Frame(onglets, padding=18)
        for page, titre in ((general, 'Application'), (compte, 'Compte'), (reset, 'Remise à zéro')):
            onglets.add(page, text=titre)
        self.organisation = tk.StringVar()
        self.dossier = tk.StringVar()
        self.recents = tk.BooleanVar()
        self.page = tk.StringVar()
        self.delai = tk.StringVar()
        for titre, variable in (('Nom de votre organisation', self.organisation), ('Dossier XML proposé à l’ouverture', self.dossier)):
            ttk.Label(general, text=titre, style='Section.TLabel').pack(anchor='w', pady=(12, 4))
            ttk.Entry(general, textvariable=variable, width=75).pack(anchor='w', fill='x')
        theme.bouton(general, 'Choisir le dossier…', self.choisir_dossier).pack(anchor='w', pady=5)
        ttk.Checkbutton(general, text='Mémoriser les fichiers récents', variable=self.recents).pack(anchor='w', pady=10)
        ttk.Label(general, text='Page ouverte au démarrage').pack(anchor='w')
        ttk.Combobox(general, textvariable=self.page, values=list(LIBELLES.values()), state='readonly', width=35).pack(anchor='w', pady=4)
        ttk.Label(general, text='Verrouillage après inactivité (minutes ; 0 = désactivé)').pack(anchor='w', pady=(12, 3))
        ttk.Spinbox(general, from_=0, to=240, textvariable=self.delai, width=8).pack(anchor='w')
        barre = ttk.Frame(general)
        barre.pack(fill='x', pady=20)
        theme.bouton(barre, 'Enregistrer les paramètres', self.enregistrer, principal=True).pack(side='left')
        theme.bouton(barre, 'Valeurs par défaut', self.defauts).pack(side='left', padx=8)
        self.message = theme.Message(general)
        self.message.pack(fill='x')

        ttk.Label(compte, text='Administrateur : ' + app.utilisateur, style='Section.TLabel').pack(anchor='w')
        ttk.Label(compte, text='Changer le mot de passe', style='Section.TLabel').pack(anchor='w', pady=(20, 6))
        self.ancien, self.nouveau, self.confirmer = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for titre, variable in (('Mot de passe actuel', self.ancien), (f'Nouveau mot de passe — {local.MIN_MOT_DE_PASSE} caractères minimum', self.nouveau), ('Confirmer le nouveau mot de passe', self.confirmer)):
            ttk.Label(compte, text=titre).pack(anchor='w', pady=(10, 3))
            ttk.Entry(compte, textvariable=variable, show='•', width=45).pack(anchor='w')
        theme.bouton(compte, 'Changer le mot de passe', self.changer_mdp, principal=True).pack(anchor='w', pady=15)
        theme.bouton(compte, 'Verrouiller la session', app.verrouiller).pack(anchor='w', pady=5)
        theme.bouton(compte, 'Se déconnecter', app.deconnecter).pack(anchor='w', pady=5)

        ttk.Label(reset, text='Recommencer avec des données de travail vides', style='Section.TLabel').pack(anchor='w')
        ttk.Label(reset, text='Les modèles de contrôle, études, références, historiques internes, registre et fichier de saisie seront retirés de l’espace de travail. Les paramètres seront remis par défaut.', wraplength=760, justify='left').pack(anchor='w', pady=10)
        ttk.Label(reset, text='Conservés : XML originaux externes, déclarations déjà exportées, exports Excel, compte administrateur et code du projet. Les données retirées sont archivées avant le redémarrage.', wraplength=760, justify='left').pack(anchor='w', pady=8)
        self.apercu = tk.StringVar()
        ttk.Label(reset, textvariable=self.apercu, wraplength=760, style='Doux.TLabel').pack(anchor='w', pady=8)
        self.sessions_fermees = tk.BooleanVar(value=False)
        ttk.Checkbutton(reset, text='J’ai fermé les autres fenêtres et arrêté les imports en cours.', variable=self.sessions_fermees).pack(anchor='w', pady=8)
        self.mdp_reset, self.phrase = tk.StringVar(), tk.StringVar()
        ttk.Label(reset, text='Mot de passe administrateur').pack(anchor='w')
        ttk.Entry(reset, textvariable=self.mdp_reset, show='•', width=40).pack(anchor='w', pady=4)
        ttk.Label(reset, text='Saisissez REINITIALISER pour confirmer').pack(anchor='w', pady=(8, 0))
        ttk.Entry(reset, textvariable=self.phrase, width=40).pack(anchor='w', pady=4)
        theme.bouton(reset, 'Réinitialiser les données de travail…', self.reinitialiser).pack(anchor='w', pady=15)
        self.charger_champs(app.reglages)

    def charger_champs(self, reglages):
        self.organisation.set(reglages['organisation'])
        self.dossier.set(reglages['dossier_xml'])
        self.recents.set(reglages['memoriser_recents'])
        self.page.set(LIBELLES[reglages['page_demarrage']])
        self.delai.set(str(reglages['verrouillage_minutes']))

    def afficher(self):
        try:
            elements = local.apercu_reset()
            self.apercu.set('Données actuellement présentes : ' + (', '.join(elements) or 'aucune donnée à retirer'))
        except ValueError as exc:
            self.apercu.set(str(exc))

    def choisir_dossier(self):
        dossier = filedialog.askdirectory(parent=self, title='Dossier XML proposé à l’ouverture')
        if dossier:
            self.dossier.set(dossier)

    def enregistrer(self):
        try:
            reglages = local.enregistrer_reglages({
                'organisation': self.organisation.get().strip(), 'dossier_xml': self.dossier.get(),
                'memoriser_recents': self.recents.get(), 'page_demarrage': next(k for k,v in LIBELLES.items() if v == self.page.get()),
                'verrouillage_minutes': int(self.delai.get()),
            })
            self.app.appliquer_reglages(reglages)
            self.message.afficher('ok', 'Paramètres enregistrés')
        except (ValueError, OSError, StopIteration) as exc:
            messagebox.showerror('Paramètres', str(exc), parent=self)

    def defauts(self):
        self.charger_champs(local.DEFAUTS)
        self.message.afficher('alerte', 'Valeurs par défaut affichées', ['Cliquez sur Enregistrer pour les appliquer. Aucune donnée de travail n’a été effacée.'])

    def changer_mdp(self):
        try:
            if self.nouveau.get() != self.confirmer.get():
                raise ValueError('Les nouveaux mots de passe ne correspondent pas.')
            local.changer_mot_de_passe(self.ancien.get(), self.nouveau.get())
            messagebox.showinfo('Compte', 'Le mot de passe a été modifié.', parent=self)
        except (ValueError, OSError) as exc:
            messagebox.showerror('Compte', str(exc), parent=self)
        finally:
            for variable in (self.ancien, self.nouveau, self.confirmer):
                variable.set('')

    def reinitialiser(self):
        if not self.sessions_fermees.get():
            messagebox.showerror('Remise à zéro', 'Fermez les autres fenêtres et les imports, puis cochez la confirmation.', parent=self)
            return
        if self.phrase.get() != local.PHRASE_RESET:
            messagebox.showerror('Remise à zéro', 'Saisissez exactement REINITIALISER.', parent=self)
            return
        if not messagebox.askyesno('Confirmer la remise à zéro',
            'Retirer les données de travail et redémarrer ?\n\nUne archive de récupération sera conservée dans SAUVEGARDES. Les saisies non enregistrées seront perdues. Les originaux externes, exports et compte seront conservés.', parent=self):
            return
        try:
            sauvegarde = local.reinitialiser(self.mdp_reset.get(), self.phrase.get(), avant_reset=self.app.preparer_reset)
        except (ValueError, OSError) as exc:
            messagebox.showerror('Remise à zéro non effectuée', str(exc), parent=self)
            return
        finally:
            self.mdp_reset.set('')
            self.phrase.set('')
        self.app.prefs = {}
        self.app.reconnexion = True
        messagebox.showinfo('Données réinitialisées', 'L’application va redémarrer avec des données vides.\n\nArchive de récupération :\n' + str(sauvegarde), parent=self)
        self.app.fermer_sans_preferences()
