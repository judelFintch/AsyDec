"""Aperçu de correction d'un modèle archivé, sans remplacer le dossier actif."""
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from asydec.declarations import correction_modele as service
from asydec.formats import nombre
from asydec.ui import theme


class FenetreCorrection(tk.Toplevel):
    def __init__(self, page, identifiant, parent=None):
        super().__init__(parent or page)
        self.page, self.identifiant = page, identifiant
        self.apercu = None
        self.donneur = None
        self.title(f'Corriger le dossier · modèle n° {identifiant}')
        self.geometry('1020x690')
        cadre = ttk.Frame(self, padding=20)
        cadre.pack(fill='both', expand=True)
        theme.entete_page(cadre, f'Corriger le dossier du modèle n° {identifiant}',
            'La répartition et ses ratios sont conservés. La correction crée une nouvelle version à valider ; '
            'le modèle initial et sa validation restent dans l’historique.')
        self.mode = tk.StringVar(value='importateur')
        for valeur, texte in service.MODES.items():
            ttk.Radiobutton(cadre, text=texte, variable=self.mode, value=valeur,
                            command=self.actualiser).pack(anchor='w', pady=3)
        choix = ttk.Frame(cadre)
        choix.pack(fill='x', pady=10)
        theme.bouton(choix, 'Choisir le bon XML…', self.choisir_fichier).pack(side='left')
        theme.bouton(choix, 'Médiathèque XML…', self.choisir_archive).pack(side='left', padx=8)
        self.var_source = tk.StringVar(value='Choisissez le XML contenant les bonnes informations du dossier.')
        ttk.Label(cadre, textvariable=self.var_source, style='Doux.TLabel', wraplength=950).pack(anchor='w')
        pied = ttk.Frame(cadre)
        pied.pack(side='bottom', fill='x')
        zone, self.table = theme.tableau(cadre, [('champ','Information',220,'w'),
            ('avant','Modèle initial',330,'w'), ('apres','Version corrigée',330,'w')], 12)
        zone.pack(fill='both', expand=True, pady=10)
        self.var_total = tk.StringVar(value='Total taxes : —')
        ttk.Label(pied, textvariable=self.var_total, style='Section.TLabel').pack(anchor='w', pady=6)
        ttk.Label(pied, text='Motif de la correction (obligatoire)').pack(anchor='w')
        self.motif = tk.StringVar()
        ttk.Entry(pied, textvariable=self.motif).pack(fill='x', pady=5)
        self.message = theme.Message(pied)
        self.message.pack(fill='x', pady=6)
        boutons = ttk.Frame(pied)
        boutons.pack(fill='x')
        self.enregistrer_bouton = theme.bouton(boutons, 'Créer la version à valider', self.enregistrer, principal=True, state='disabled')
        self.enregistrer_bouton.pack(side='right')
        theme.bouton(boutons, 'Annuler', self.destroy).pack(side='right', padx=8)

    def choisir_fichier(self):
        if self.page.app.session_verrouillee:
            return
        chemin = filedialog.askopenfilename(parent=self, title='XML avec les bonnes informations du dossier',
                                            filetypes=[('XML', '*.xml')])
        if chemin:
            self.charger(chemin)

    def choisir_archive(self):
        if self.page.app.session_verrouillee:
            return
        from asydec.ui.selection_xml import choisir
        try:
            documents = self.page.app.xml_disponibles(generation=self.mode.get() == 'base', tous_modules=True)
            chemins = choisir(self, documents, titre='Choisir le bon dossier XML')
            if chemins:
                self.charger(chemins[0])
        except Exception as exc:
            self.message.afficher('erreur', 'Médiathèque indisponible', [str(exc)])

    def charger(self, chemin):
        self.donneur = None
        try:
            self.donneur = Path(chemin).read_bytes()
            self.var_source.set(str(chemin))
        except Exception as exc:
            self.message.afficher('erreur', 'XML illisible', [str(exc)])
        self.actualiser()

    def actualiser(self):
        self.apercu = None
        self.enregistrer_bouton.configure(state='disabled')
        self.table.delete(*self.table.get_children())
        self.var_total.set('Total taxes : —')
        if self.donneur is None or self.page.app.session_verrouillee:
            return
        try:
            self.apercu = service.preparer(self.identifiant, self.donneur, self.mode.get())
            for champ, avant, apres in self.apercu.changements:
                self.table.insert('', 'end', tags=('alerte',) if avant != apres else (),
                                  values=(champ, avant if avant != '' else '—', apres if apres != '' else '—'))
            total = next((a, b) for cle, a, b in self.apercu.changements if cle == 'Total taxes CDF')
            self.var_total.set(f'Total taxes : {nombre(total[0])} → {nombre(total[1])} CDF · écart {nombre(total[1]-total[0])} CDF')
            self.message.afficher('ok', 'Aperçu prêt', ['Vérifiez les informations avant de créer la nouvelle version.'])
            self.enregistrer_bouton.configure(state='normal')
        except Exception as exc:
            self.message.afficher('erreur', 'Correction impossible', [str(exc)])

    def enregistrer(self):
        if self.page.app.session_verrouillee or self.apercu is None:
            return
        self.enregistrer_bouton.configure(state='disabled')
        try:
            identifiant = service.enregistrer(self.apercu, self.page.app.utilisateur, self.motif.get())
        except Exception as exc:
            self.message.afficher('erreur', 'Correction non enregistrée', [str(exc)])
            self.enregistrer_bouton.configure(state='normal')
            return
        self.page.filtre.set('Tous')
        self.page.afficher()
        if self.page.table.exists(str(identifiant)):
            self.page.table.selection_set(str(identifiant))
            self.page.table.see(str(identifiant))
        messagebox.showinfo('Nouvelle version créée', f'Modèle n° {identifiant} créé à partir du modèle n° {self.identifiant}. '
                           'Il est en attente de validation.', parent=self)
        self.destroy()
