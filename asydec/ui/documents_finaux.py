"""Parcours de préparation des documents finaux."""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from asydec.declarations.documents_finaux import preparer_licence
from asydec.ui import theme
from asydec.declarations.import_licence import lire_licence


class PageDocumentsFinaux(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.licence = None
        self.import_en_cours = False
        self.a_verifier = False
        theme.entete_page(self, 'Documents finaux', 'Étape 1 · Licence d’importation')
        self.bouton_import = theme.bouton(self, 'Importer une licence PDF ou photo', self.importer)
        self.bouton_import.pack(anchor='w', pady=6)
        self.source = tk.StringVar(value='Saisie manuelle : remplissez les champs ci-dessous.')
        ttk.Label(self, textvariable=self.source, wraplength=760).pack(anchor='w')
        cadre = ttk.Frame(self, padding=20, relief='solid', borderwidth=1)
        cadre.pack(fill='x', pady=8)
        cadre.columnconfigure(1, weight=1)
        self.champs = {}
        for ligne, (cle, libelle) in enumerate((
                ('numero_dec', 'Numéro DEC'), ('montant_fob', 'Montant FOB'),
                ('numero_validation', 'Numéro de validation de la licence'),
                ('date_validation', 'Date de validation (JJ/MM/AAAA)'))):
            ttk.Label(cadre, text=libelle).grid(row=ligne, column=0, sticky='w', padx=(0, 16), pady=8)
            variable = tk.StringVar()
            self.champs[cle] = variable
            ttk.Entry(cadre, textvariable=variable).grid(row=ligne, column=1, sticky='ew', pady=8)
            variable.trace_add('write', self._modifier)
        ttk.Label(self, text='Date du BL : premier jour du lundi au vendredi entre J+3 et J+5 calendaires.\n'
                  'Les jours fériés ne sont pas pris en compte.',
                  style='SousTitre.TLabel', wraplength=760).pack(anchor='w', pady=8)
        self.resultat = tk.StringVar(value='Renseignez la licence pour calculer la date du BL.')
        ttk.Label(self, textvariable=self.resultat, style='Section.TLabel',
                  wraplength=760).pack(anchor='w', pady=12)
        self.bouton_valider = theme.bouton(self, 'Valider l’étape 1', self.valider, principal=True)
        self.bouton_valider.pack(anchor='w')
        self.confirme = tk.BooleanVar(value=False)
        self.verification = ttk.Checkbutton(self, text='J’ai vérifié les informations importées avec la licence.',
                                            variable=self.confirme, command=self._modifier)
        self.message = theme.Message(self)
        self._modifier()

    def _modifier(self, *_):
        self.licence = None
        self.message.pack_forget()
        try:
            licence = preparer_licence(**{cle: var.get() for cle, var in self.champs.items()})
        except ValueError as exc:
            self.resultat.set(str(exc))
            self.bouton_valider.configure(state='disabled')
            return
        self.resultat.set(f"Date du BL : {licence['date_bl']:%d/%m/%Y} · J+{licence['delai']}")
        self.bouton_valider.configure(state='disabled' if self.import_en_cours or
                                      (self.a_verifier and not self.confirme.get()) else 'normal')

    def importer(self):
        if self.app.session_verrouillee or self.import_en_cours:
            return
        chemin = filedialog.askopenfilename(parent=self, title='Importer la licence d’importation',
                    filetypes=[('Licence PDF ou photo', '*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp')])
        if not chemin:
            return
        if any(v.get().strip() for v in self.champs.values()) and not messagebox.askyesno(
                'Nouvelle licence', 'Remplacer les informations du formulaire par celles de cette licence ?', parent=self):
            return
        self.import_en_cours = True
        self.bouton_import.configure(state='disabled')
        self.bouton_valider.configure(state='disabled')
        self.source.set('Lecture de la licence en cours…')
        executant = ThreadPoolExecutor(max_workers=1)
        future = executant.submit(lire_licence, chemin)
        executant.shutdown(wait=False)

        def terminer():
            if not future.done() or self.app.session_verrouillee:
                self.after(150, terminer)
                return
            self.import_en_cours = False
            self.bouton_import.configure(state='normal')
            try:
                valeurs, texte = future.result()
            except Exception as exc:
                self.source.set('Import impossible. Vous pouvez continuer en saisie manuelle.')
                self._modifier()
                self.message.pack(fill='x', pady=12)
                self.message.afficher('erreur', 'Lecture impossible', [str(exc)])
                return
            self.a_verifier = True
            self.confirme.set(False)
            for cle, variable in self.champs.items():
                variable.set(valeurs.get(cle, ''))
            self.source.set(f'{Path(chemin).name} · {len(valeurs)}/4 champs détectés. Complétez et vérifiez le formulaire.')
            self.verification.pack(anchor='w', before=self.bouton_valider, pady=8)
            self._modifier()
            fenetre = tk.Toplevel(self)
            fenetre.title('Texte extrait de la licence — à vérifier')
            fenetre.geometry('750x500')
            zone = tk.Text(fenetre, wrap='word')
            zone.pack(fill='both', expand=True)
            zone.insert('1.0', texte)
            zone.configure(state='disabled')
            theme.bouton(fenetre, 'Revenir au formulaire', fenetre.destroy).pack(pady=8)

        self.after(150, terminer)

    def valider(self):
        if self.app.session_verrouillee or self.import_en_cours or (self.a_verifier and not self.confirme.get()):
            return
        try:
            self.licence = preparer_licence(**{cle: var.get() for cle, var in self.champs.items()})
        except ValueError as exc:
            self.message.pack(fill='x', pady=12)
            self.message.afficher('erreur', str(exc))
            return
        self.message.pack(fill='x', pady=12)
        self.message.afficher('ok', 'Étape 1 validée', [
            f"DEC : {self.licence['numero_dec']} · FOB : {self.licence['montant_fob']:,.2f}",
            f"Validation licence : {self.licence['numero_validation']}",
            f"Date du BL : {self.licence['date_bl']:%d/%m/%Y}"])
