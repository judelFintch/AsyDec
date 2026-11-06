"""Étape 7 : un XML par part au montant différent (parts identiques générées une fois),
avec un modèle de structure choisi automatiquement."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog
import xml.etree.ElementTree as ET

from asydec.declarations import xml_licence
from asydec.ui import theme, synthese_licence


class FenetreGenerationXML(tk.Toplevel):
    def __init__(self, parent, licence, modele, generer):
        super().__init__(parent)
        self.licence, self.modele, self.generer = licence, modele, generer
        self.vues = xml_licence.vues_a_generer(licence)
        self.title('Génération XML')
        self.geometry('980x800')
        self.minsize(760, 560)
        self.transient(parent.winfo_toplevel())
        cadre = ttk.Frame(self, padding=20)
        cadre.pack(fill='both', expand=True)

        bas = ttk.Frame(cadre)
        bas.pack(side='bottom', fill='x')
        self.erreur = tk.StringVar()
        ttk.Label(bas, textvariable=self.erreur, style='Erreur.TLabel', wraplength=900).pack(anchor='w', pady=(6, 0))
        actions = ttk.Frame(bas)
        actions.pack(fill='x', pady=(10, 0))
        theme.bouton(actions, 'Annuler', self.destroy).pack(side='left')
        n = len(self.vues)
        self.bouton_generer = theme.bouton(actions, f'Générer {n} XML' if n > 1 else 'Générer le XML', self.valider, principal=True)
        self.bouton_generer.pack(side='right')

        theme.entete_page(cadre, '7 · Génération XML', licence['numero_validation'])
        bloc = ttk.Frame(cadre, padding=12, relief='solid', borderwidth=1)
        bloc.pack(fill='x', pady=(0, 12))
        bloc.columnconfigure(0, weight=1)
        ttk.Label(bloc, text='Modèle de structure proposé', style='Doux.TLabel').grid(row=0, column=0, sticky='w')
        self.nom_modele = tk.StringVar()
        ttk.Label(bloc, textvariable=self.nom_modele, style='Section.TLabel', wraplength=700).grid(row=1, column=0, sticky='w', pady=(2, 0))
        self.explication = tk.StringVar()
        ttk.Label(bloc, textvariable=self.explication, style='Doux.TLabel', wraplength=700).grid(row=2, column=0, sticky='w', pady=(4, 0))
        theme.bouton(bloc, 'Changer de modèle…', self.changer).grid(row=0, column=1, rowspan=3, sticky='e', padx=(12, 0))
        theme.bouton(bloc, 'Ajouter une déclaration réelle…', self.ajouter_base).grid(
            row=3, column=1, sticky='e', padx=(12, 0), pady=(6, 0))
        self._afficher_modele()

        ttk.Label(cadre, text=f'XML à générer : un par montant de part différent ({len(self.vues)})',
                  style='Section.TLabel').pack(anchor='w', pady=(0, 6))
        zone, fichiers = theme.tableau(cadre, [('parts', 'Parts couvertes', 260, 'w'), ('fob', 'FOB de la part (USD)', 160, 'e'),
                                               ('e', 'Numéro E', 140, 'w'), ('plaque', 'Plaques', 220, 'w')],
                                       hauteur=min(len(self.vues), 6))
        zone.pack(fill='x', pady=(0, 12))
        for vue in self.vues:
            part, infos = vue['part_generee'], vue.get('informations_declaration') or {}
            fichiers.insert('', 'end', values=(xml_licence.libelle_parts(part['identiques']).capitalize(),
                                               synthese_licence.nombre(synthese_licence.decimal(part['fob']), 2),
                                               infos.get('numero_e', ''), infos.get('plaque', '')))
        ttk.Label(cadre, text='Informations reprises de la première déclaration (part 1)', style='Section.TLabel').pack(anchor='w', pady=(0, 6))
        lignes, produits = xml_licence.apercu(licence)
        zone, table = theme.tableau(cadre, [('champ', 'Champ', 260, 'w'), ('valeur', 'Valeur', 560, 'w')], hauteur=min(len(lignes), 9))
        zone.pack(fill='x', pady=(0, 12))
        for titre, valeur in lignes:
            table.insert('', 'end', values=(titre, valeur))

        ttk.Label(cadre, text='Articles de la part 1', style='Section.TLabel').pack(anchor='w', pady=(0, 6))
        zone, articles = theme.tableau(cadre, [('numero', 'N°', 40, 'center'), ('designation', 'Désignation', 420, 'w'),
                                               ('quantite', 'Quantité', 110, 'e'), ('prix', 'Prix unitaire', 110, 'e'),
                                               ('valeur', 'Valeur', 120, 'e')], hauteur=6)
        zone.pack(fill='both', expand=True)
        for i, produit in enumerate(produits, 1):
            q, pu = synthese_licence.decimal(produit.get('quantite')), synthese_licence.decimal(produit.get('prix_unitaire'))
            articles.insert('', 'end', values=(i, ' '.join(str(produit.get('designation', '')).split()),
                                               synthese_licence.quantite(q), synthese_licence.nombre(pu, 2),
                                               synthese_licence.nombre(synthese_licence.decimal(produit['valeur']), 2)
                                               if produit.get('valeur') else
                                               synthese_licence.nombre(q * pu, 2) if q is not None and pu is not None else '—'))

    def _afficher_modele(self):
        if self.modele is None:
            self.nom_modele.set('Aucun modèle compatible trouvé : choisissez un XML ASYCUDA.')
            self.bouton_generer.configure(state='disabled')
        else:
            self.nom_modele.set(Path(self.modele).name)
            self.bouton_generer.configure(state='normal')
        complet = self.modele is not None and xml_licence.est_base_licence(self.modele)
        self.explication.set(
            'Déclaration réelle de licence : XML complet (bureau, déclarant, banque, transport, documents, poids, colis, '
            'valeur, fret, assurance et taxes recalculés). Les données de l’ancien dossier sont remplacées.'
            if complet else
            '⚠ Aucune déclaration réelle de licence sur ce poste : XML de PRÉPARATION seulement (structure du modèle, '
            'sans bureau, banque, taux, fret, assurance ni taxes). Cliquez sur « Ajouter une déclaration réelle… » '
            'pour obtenir un XML complet.')

    def changer(self):
        chemin = filedialog.askopenfilename(parent=self, title='Choisir la structure XML ASYCUDA',
                                            filetypes=[('XML ASYCUDA', '*.xml')])
        if not chemin:
            return
        try:
            for vue in self.vues:
                xml_licence.preparer(vue, chemin)
        except (ValueError, OSError, ET.ParseError) as exc:
            self.erreur.set(f'Modèle refusé : {exc}')
            return
        self.erreur.set('')
        self.modele = chemin
        self._afficher_modele()

    def ajouter_base(self):
        """Dépose une vraie déclaration SYDONIA de licence dans XML_LICENCES et la prend comme base."""
        chemin = filedialog.askopenfilename(parent=self, title='Vraie déclaration SYDONIA de licence (XML)',
                                            filetypes=[('XML SYDONIA', '*.xml')])
        if not chemin:
            return
        try:
            base = xml_licence.ajouter_base_licence(chemin)
            for vue in self.vues:
                xml_licence.preparer(vue, base)
        except (ValueError, OSError, ET.ParseError) as exc:
            self.erreur.set(f'Déclaration refusée : {exc}')
            return
        self.erreur.set('')
        self.modele = base
        self._afficher_modele()

    def valider(self):
        if self.modele is None:
            return
        erreur = self.generer(self.modele)
        if erreur:
            self.erreur.set(erreur)
        elif self.winfo_exists():
            self.destroy()
