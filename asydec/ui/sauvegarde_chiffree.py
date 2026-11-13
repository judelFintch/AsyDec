"""Sauvegardes locales et GitHub, chiffrées avant toute publication."""
from datetime import date
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from asydec.systeme import sauvegarde_chiffree as coffre, sauvegarde_github as distant
from asydec.systeme import gestion_locale as local
from asydec.ui import theme


class PageSauvegardeChiffree(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=18)
        self.app, self.occupe, self.sauvegardes = app, False, []
        self.resultats = queue.Queue()
        ttk.Label(self, text='Sauvegarde complète protégée par mot de passe', style='Section.TLabel').pack(anchor='w')
        ttk.Label(self, text='Compte, dossiers, factures, modèles CVI/BL et DEC et réglages sont chiffrés avant publication. '
                  'Le mot de passe de sauvegarde est distinct du compte AsyDec ; il n’est jamais enregistré ni envoyé à GitHub.',
                  wraplength=820).pack(anchor='w', pady=(6, 12))
        self.mdp, self.confirmation, self.jeton = tk.StringVar(), tk.StringVar(), tk.StringVar()
        ligne = ttk.Frame(self)
        ligne.pack(anchor='w')
        ttk.Label(ligne, text='Mot de passe de sauvegarde (12 caractères minimum)').grid(row=0, column=0, sticky='w')
        ttk.Entry(ligne, textvariable=self.mdp, show='•', width=38).grid(row=0, column=1, padx=10, pady=4)
        ttk.Label(ligne, text='Confirmer pour créer un export').grid(row=1, column=0, sticky='w')
        ttk.Entry(ligne, textvariable=self.confirmation, show='•', width=38).grid(row=1, column=1, padx=10, pady=4)
        theme.bouton(self, 'Créer un export complet chiffré…', self.exporter, principal=True).pack(anchor='w', pady=8)
        ttk.Label(self, text='Gardez ce mot de passe : sans lui, la sauvegarde ne peut pas être récupérée.',
                  wraplength=820, style='Doux.TLabel').pack(anchor='w')
        ttk.Separator(self).pack(fill='x', pady=12)
        ttk.Label(self, text='GitHub Releases', style='Section.TLabel').pack(anchor='w')
        ttk.Label(self, text=f'Dépôt : {distant.github.DEPOT}. Sur une release publique, seul le fichier chiffré est visible ; '
                  'son contenu exige le mot de passe. Une mise à jour du logiciel ne charge jamais vos données automatiquement.',
                  wraplength=820).pack(anchor='w', pady=6)
        ligne = ttk.Frame(self)
        ligne.pack(anchor='w')
        ttk.Label(ligne, text='Jeton GitHub (Contents en écriture pour publier)').pack(side='left')
        ttk.Entry(ligne, textvariable=self.jeton, show='•', width=40).pack(side='left', padx=10)
        ttk.Label(self, text='Jeton utilisé pour cette opération seulement. Pour récupérer depuis un dépôt public, laissez-le vide.',
                  wraplength=820, style='Doux.TLabel').pack(anchor='w', pady=4)
        ligne = ttk.Frame(self)
        ligne.pack(anchor='w', pady=8)
        theme.bouton(ligne, 'Publier un fichier chiffré…', self.publier).pack(side='left')
        theme.bouton(ligne, 'Rechercher les sauvegardes sur GitHub', self.rechercher).pack(side='left', padx=10)
        self.choix = ttk.Combobox(self, state='readonly', width=95)
        self.choix.pack(anchor='w', pady=4)
        ligne = ttk.Frame(self)
        ligne.pack(anchor='w', pady=8)
        theme.bouton(ligne, 'Télécharger et charger avec mon mot de passe…', self.recuperer, principal=True).pack(side='left')
        theme.bouton(ligne, 'Charger un fichier chiffré local…', self.importer_local).pack(side='left', padx=10)
        self.etat = tk.StringVar()
        ttk.Label(self, textvariable=self.etat, wraplength=820).pack(anchor='w', pady=10)

    def _disponible(self):
        return not self.occupe and not self.app.session_verrouillee

    def _secret(self, creation=False):
        mdp = self.mdp.get()
        coffre.verifier_mot_de_passe(mdp)
        if creation and mdp != self.confirmation.get():
            raise ValueError('Les deux mots de passe de sauvegarde ne correspondent pas.')
        return mdp

    def travailler(self, texte, action, fin):
        if not self._disponible():
            return
        self.occupe = True
        self.etat.set(texte)
        self.mdp.set('')
        self.confirmation.set('')
        self.jeton.set('')

        def worker():
            try:
                self.resultats.put((True, action()))
            except Exception as exc:
                self.resultats.put((False, str(exc)))

        def suivre():
            try:
                ok, resultat = self.resultats.get_nowait()
            except queue.Empty:
                self.after(150, suivre)
                return
            self.occupe = False
            if not ok:
                self.etat.set(resultat)
                messagebox.showerror('Sauvegarde non effectuée', resultat, parent=self)
                return
            try:
                fin(resultat)
            except Exception as exc:
                self.etat.set(str(exc))
                messagebox.showerror('Sauvegarde', str(exc), parent=self)

        threading.Thread(target=worker, daemon=True).start()
        self.after(150, suivre)

    def exporter(self):
        if not self._disponible():
            return
        try:
            mdp = self._secret(creation=True)
        except ValueError as exc:
            messagebox.showerror('Mot de passe', str(exc), parent=self)
            return
        fichier = filedialog.asksaveasfilename(parent=self, title='Export complet chiffré',
            initialfile=f'AsyDec-sauvegarde-{date.today():%Y-%m-%d}{coffre.EXTENSION}',
            defaultextension=coffre.EXTENSION, filetypes=[('Sauvegarde chiffrée', '*' + coffre.EXTENSION)])
        if fichier:
            self.travailler('Création et chiffrement de l’export complet…', lambda: coffre.exporter(fichier, mdp),
                lambda resultat: self.etat.set(f'Export chiffré prêt : {resultat[0]}. Vous pouvez le publier sur GitHub.'))

    def publier(self):
        if not self._disponible():
            return
        try:
            mdp = self._secret()
            token = self.jeton.get().strip()
            if not token:
                raise ValueError('Renseignez le jeton GitHub avec Contents en écriture pour publier.')
        except ValueError as exc:
            messagebox.showerror('Publication', str(exc), parent=self)
            return
        fichier = filedialog.askopenfilename(parent=self, title='Sauvegarde complète déjà chiffrée',
                                             filetypes=[('Sauvegarde chiffrée', '*' + coffre.EXTENSION)])
        if not fichier or not messagebox.askyesno('Publier la sauvegarde chiffrée',
            f'Publier ce fichier chiffré dans une release du dépôt {distant.github.DEPOT} ?\n\n'
            'Seul le fichier chiffré est envoyé. Le mot de passe reste sur cet ordinateur.', parent=self):
            return
        self.travailler('Vérification du mot de passe et publication du fichier chiffré…',
            lambda: distant.publier(fichier, mdp, token),
            lambda url: self.etat.set('Sauvegarde chiffrée publiée : ' + url))

    def rechercher(self):
        if not self._disponible():
            return
        token = self.jeton.get().strip() or None

        def fin(sauvegardes):
            self.sauvegardes = sauvegardes
            self.choix.configure(values=[f"{s['date']} · {s['release']} · {s['taille']/1e6:.1f} Mo" for s in sauvegardes])
            if sauvegardes:
                self.choix.current(0)
            else:
                self.choix.set('')
            self.etat.set(f'{len(sauvegardes)} sauvegarde(s) chiffrée(s) disponible(s). '
                          'Saisissez le mot de passe avant de télécharger et charger.')

        self.travailler('Recherche des sauvegardes chiffrées sur GitHub…', lambda: distant.lister(token), fin)

    def _confirmer_import(self):
        mdp = simpledialog.askstring('Remplacer les données locales',
            'Mot de passe du compte AsyDec de cet ordinateur (distinct du mot de passe de sauvegarde) :', show='•', parent=self)
        if mdp is None:
            return False
        if not local.authentifier(local.identifiant_compte(), mdp):
            raise ValueError('Mot de passe du compte local incorrect.')
        return messagebox.askyesno('Charger la sauvegarde complète',
            'Après vérification du mot de passe de sauvegarde, les données actuelles seront mises de côté, '
            'puis remplacées au redémarrage.\n\nLe compte et le mot de passe de connexion deviennent ceux de la sauvegarde. Continuer ?',
            icon='warning', parent=self)

    def _pret(self, resultat):
        self.etat.set('Sauvegarde déchiffrée, vérifiée et prête à être chargée au redémarrage.')
        if self.app.session_verrouillee:
            return
        messagebox.showinfo('Sauvegarde prête', 'AsyDec va se fermer puis charger les données vérifiées. '
                            'Connectez-vous ensuite avec le compte de la sauvegarde.', parent=self)
        self.app.reconnexion = True
        self.app.fermer_sans_preferences()

    def recuperer(self):
        if not self._disponible() or not 0 <= self.choix.current() < len(self.sauvegardes):
            return
        try:
            mdp = self._secret()
            if not self._confirmer_import():
                return
        except (ValueError, OSError) as exc:
            messagebox.showerror('Chargement', str(exc), parent=self)
            return
        asset = dict(self.sauvegardes[self.choix.current()])
        token = self.jeton.get().strip() or None
        self.travailler('Téléchargement, déchiffrement et vérification de la sauvegarde…',
                        lambda: distant.recuperer(asset, mdp, token), self._pret)

    def importer_local(self):
        if not self._disponible():
            return
        try:
            mdp = self._secret()
            fichier = filedialog.askopenfilename(parent=self, title='Sauvegarde chiffrée',
                filetypes=[('Sauvegarde chiffrée', '*' + coffre.EXTENSION)])
            if not fichier or not self._confirmer_import():
                return
        except (ValueError, OSError) as exc:
            messagebox.showerror('Chargement', str(exc), parent=self)
            return
        self.travailler('Déchiffrement et vérification de la sauvegarde locale…',
                        lambda: coffre.preparer_import(fichier, mdp), self._pret)
