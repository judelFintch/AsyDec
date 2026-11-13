"""Paramètres et reset : ne modifie pas le module de références."""
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from asydec.systeme import espace_travail, transfert
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
        transfert_page = ttk.Frame(onglets, padding=18)
        for page, titre in ((general, 'Application'), (compte, 'Compte'), (transfert_page, 'Transfert vers une autre machine'),
                            (reset, 'Remise à zéro')):
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
        ttk.Label(general, text='Dossier de travail (fichiers produits par AsyDec)', style='Section.TLabel').pack(anchor='w', pady=(16, 4))
        self.var_espace = tk.StringVar()
        ttk.Label(general, textvariable=self.var_espace, wraplength=760).pack(anchor='w')
        ligne = ttk.Frame(general)
        ligne.pack(anchor='w', pady=5)
        theme.bouton(ligne, 'Changer…', app.choisir_espace_travail).pack(side='left')
        theme.bouton(ligne, 'Ouvrir', self.ouvrir_espace_travail).pack(side='left', padx=6)
        theme.bouton(ligne, 'Ranger mes fichiers existants…', self.ranger_existants).pack(side='left')
        self.afficher_espace_travail()
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
        self.construire_transfert(transfert_page)
        self.charger_champs(app.reglages)

    # ----- Transfert vers une autre machine -----
    def construire_transfert(self, cadre):
        ttk.Label(cadre, text='Exporter', style='Section.TLabel').pack(anchor='w')
        ttk.Label(cadre, text='Un seul fichier .asydec à copier sur la nouvelle machine (clé USB, e-mail, cloud).',
                  wraplength=760).pack(anchor='w', pady=(4, 8))
        self.avec_sauvegardes = tk.BooleanVar(value=False)
        ligne = ttk.Frame(cadre)
        ligne.pack(anchor='w')
        theme.bouton(ligne, 'Exporter toutes mes données…', lambda: self.exporter(False), principal=True).pack(side='left')
        ttk.Checkbutton(ligne, text='inclure les sauvegardes (fichier plus lourd)', variable=self.avec_sauvegardes).pack(side='left', padx=10)
        ttk.Label(cadre, text='Compte, numéros de facture réservés, modèles, dossiers, licences, références et réglages. '
                  'Pour remplacer votre ordinateur. Contient vos données : gardez ce fichier en lieu sûr.',
                  wraplength=760, style='Doux.TLabel').pack(anchor='w', pady=(2, 10))
        theme.bouton(cadre, 'Exporter un kit de démarrage (modèles seulement)…', lambda: self.exporter(True)).pack(anchor='w')
        ttk.Label(cadre, text='Modèles de facture Word, XML de référence et médiathèque XML, sans compte, historique ni '
                  'numéros. Pour équiper le poste d’un collègue.', wraplength=760, style='Doux.TLabel').pack(anchor='w', pady=(2, 16))
        ttk.Separator(cadre).pack(fill='x', pady=6)
        ttk.Label(cadre, text='Importer', style='Section.TLabel').pack(anchor='w', pady=(8, 4))
        theme.bouton(cadre, 'Importer des modèles (kit ou export complet)…', self.importer_modeles, principal=True).pack(anchor='w')
        ttk.Label(cadre, text='Ajoute les modèles absents de cette machine ; rien n’est remplacé ni supprimé.',
                  wraplength=760, style='Doux.TLabel').pack(anchor='w', pady=(2, 10))
        ligne = ttk.Frame(cadre)
        ligne.pack(anchor='w')
        theme.bouton(ligne, 'Remplacer mes données par un export complet…', lambda: self.importer_complet(False)).pack(side='left')
        theme.bouton(ligne, 'Depuis un ancien dossier OUTILS…', lambda: self.importer_complet(True)).pack(side='left', padx=8)
        ttk.Label(cadre, text='Les données actuelles sont mises de côté dans SAUVEGARDES, puis AsyDec redémarre avec '
                  'les données importées (le compte et le mot de passe deviennent ceux de l’export).',
                  wraplength=760, style='Doux.TLabel').pack(anchor='w', pady=(2, 8))
        self.mdp_transfert = tk.StringVar()
        ligne = ttk.Frame(cadre)
        ligne.pack(anchor='w', pady=4)
        ttk.Label(ligne, text='Mot de passe administrateur (pour remplacer les données)').pack(side='left')
        ttk.Entry(ligne, textvariable=self.mdp_transfert, show='•', width=28).pack(side='left', padx=8)
        self.etat_transfert = tk.StringVar()
        ttk.Label(cadre, textvariable=self.etat_transfert, wraplength=760).pack(anchor='w', pady=10)

    def _occupe(self, texte):
        self.etat_transfert.set(texte)
        self.configure(cursor='watch')
        self.update_idletasks()

    def exporter(self, kit):
        from datetime import date
        nom = f"AsyDec-{'kit-modeles' if kit else 'donnees'}-{date.today():%Y-%m-%d}{transfert.EXTENSION}"
        chemin = filedialog.asksaveasfilename(parent=self, title='Enregistrer l’export AsyDec', initialfile=nom,
                                              defaultextension=transfert.EXTENSION,
                                              filetypes=[('Export AsyDec', '*' + transfert.EXTENSION)])
        if not chemin:
            return
        try:
            self._occupe('Export en cours…')
            fichier, resume = transfert.exporter(chemin, kit=kit, avec_sauvegardes=self.avec_sauvegardes.get())
        except (ValueError, OSError) as exc:
            self.etat_transfert.set('')
            messagebox.showerror('Export non effectué', str(exc), parent=self)
            return
        finally:
            self.configure(cursor='')
        taille = fichier.stat().st_size / 1e6
        self.etat_transfert.set(f'Export enregistré : {fichier} ({taille:.1f} Mo).')
        messagebox.showinfo('Export terminé', f'{fichier.name} ({taille:.1f} Mo)\n\n{transfert.decrire(resume)}\n\n'
                            'Sur l’autre machine : Paramètres › Transfert › '
                            + ('« Importer des modèles ».' if kit else '« Remplacer mes données par un export complet ».'),
                            parent=self)

    def importer_modeles(self):
        chemin = filedialog.askopenfilename(parent=self, title='Export AsyDec contenant les modèles',
                                            filetypes=[('Export AsyDec', '*' + transfert.EXTENSION)])
        if not chemin:
            return
        try:
            manifeste = transfert.lire(chemin)
            if not messagebox.askyesno('Importer des modèles',
                                       f"Export du {manifeste.get('cree_le', '')[:10]} ({manifeste['type']}).\n\n"
                                       f"{transfert.decrire({k: v for k, v in manifeste.get('resume', {}).items() if k in ('modeles_word', 'xml_reference', 'xml_licences', 'xml_mediatheque')})}"
                                       '\n\nAjouter les modèles absents de cette machine ?', parent=self):
                return
            self._occupe('Import des modèles en cours…')
            bilan = transfert.importer_modeles(chemin, conn_references=self.app.base_refs())
        except (ValueError, OSError) as exc:
            self.etat_transfert.set('')
            messagebox.showerror('Import non effectué', str(exc), parent=self)
            return
        finally:
            self.configure(cursor='')
        deja = bilan.pop('deja_presents')
        texte = transfert.decrire(bilan) + f'\n• {deja} éléments déjà présents (ignorés)'
        self.etat_transfert.set('Modèles importés.')
        messagebox.showinfo('Modèles importés', 'Ajoutés :\n' + texte, parent=self)

    def importer_complet(self, dossier):
        if dossier:
            source = filedialog.askdirectory(parent=self, title='Ancien dossier OUTILS ou « Application Support/AsyDec »')
        else:
            source = filedialog.askopenfilename(parent=self, title='Export complet AsyDec',
                                                filetypes=[('Export AsyDec', '*' + transfert.EXTENSION)])
        if not source:
            return
        try:
            if not local.authentifier(local.identifiant_compte(), self.mdp_transfert.get()):
                raise ValueError('Mot de passe administrateur incorrect.')
            if not dossier:
                manifeste = transfert.lire(source)
                if manifeste['type'] != 'complet':
                    raise ValueError('Ce fichier est un kit de modèles : utilisez « Importer des modèles ».')
                if not messagebox.askyesno('Remplacer les données de cette machine',
                                           f"Export du {manifeste.get('cree_le', '')[:10]} :\n{transfert.decrire(manifeste.get('resume', {}))}"
                                           '\n\nLes données actuelles seront mises de côté dans SAUVEGARDES, puis remplacées. '
                                           'Continuer ?', icon='warning', parent=self):
                    return
            elif not messagebox.askyesno('Remplacer les données de cette machine',
                                         f'Données de : {source}\n\nLes données actuelles seront mises de côté dans '
                                         'SAUVEGARDES, puis remplacées. Continuer ?', icon='warning', parent=self):
                return
            self._occupe('Vérification et préparation de l’import…')
            transfert.preparer_import_complet(source)
        except (ValueError, OSError, local.ErreurCompte) as exc:
            self.etat_transfert.set('')
            messagebox.showerror('Import non effectué', str(exc), parent=self)
            return
        finally:
            self.mdp_transfert.set('')
            self.configure(cursor='')
        messagebox.showinfo('Import prêt', 'Données vérifiées. AsyDec va se fermer, installer les données importées, '
                            'puis demander de vous reconnecter avec le compte de l’export.', parent=self)
        self.app.reconnexion = True
        self.app.fermer_sans_preferences()

    def afficher_espace_travail(self):
        racine = espace_travail.racine()
        self.var_espace.set(str(racine) if racine else
                            'Aucun : les fichiers vont encore dans l’ancienne organisation (DEC FRIPERIE). Cliquez sur « Changer… ».')

    def ouvrir_espace_travail(self):
        from asydec.ui.espace_travail import ouvrir_dans_finder
        racine = espace_travail.racine()
        if racine is None:
            messagebox.showinfo('Dossier de travail', 'Choisissez d’abord le dossier de travail.', parent=self)
            return
        ouvrir_dans_finder(espace_travail.preparer(racine))

    def ranger_existants(self):
        from asydec.ui import espace_travail as fenetres
        if espace_travail.racine() is None:
            messagebox.showinfo('Dossier de travail', 'Choisissez d’abord le dossier de travail.', parent=self)
            return
        try:
            plan = [p for p in fenetres.planifier(self.app) if not p['deja']]
        except Exception as exc:  # noqa: BLE001 - message montré à l'utilisateur
            messagebox.showerror('Analyse impossible', str(exc), parent=self)
            return
        if not plan:
            messagebox.showinfo('Rien à ranger', 'Tous vos fichiers existants sont déjà rangés.', parent=self)
            return
        self.wait_window(fenetres.FenetreRangement(self, plan))

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
