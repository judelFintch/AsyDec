"""Choix d'une licence dans un fichier Excel (liste des DEC de la banque)."""
import tkinter as tk
from tkinter import ttk

from asydec.declarations import import_excel_licence as excel
from asydec.formats import nombre
from asydec.ui import theme


class ChoixLicenceExcel(tk.Toplevel):
    """Liste les licences du fichier ; resultat = liste des lignes choisies, ou None si annulé."""

    AUCUN_IMPORTATEUR = 'Client du fichier Excel (nom seulement)'
    AUCUN_FOURNISSEUR = 'Aucun : à compléter'

    def __init__(self, parent, licences, deja_ouvertes=(), nom_fichier='', importateurs=(), fournisseurs=()):
        super().__init__(parent)
        self.title('Choisir la licence à ouvrir')
        self.geometry('1060x720')
        self.minsize(820, 420)
        self.transient(parent.winfo_toplevel())
        self.resultat = None
        # Coordonnées choisies (dict) ou None : reprises d'une licence déjà ouverte.
        self.importateur = self.fournisseur = None
        self.sources = {'importateur': list(importateurs), 'fournisseur': list(fournisseurs)}
        self.deja = {str(n).strip().upper() for n in deja_ouvertes}
        # Les plus récentes en premier : ce sont généralement celles à ouvrir.
        self.licences = sorted(licences, key=lambda l: _cle_date(l['date_validation']), reverse=True)
        cadre = ttk.Frame(self, padding=20)
        cadre.pack(fill='both', expand=True)
        bas = ttk.Frame(cadre)
        bas.pack(side='bottom', fill='x', pady=(12, 0))
        theme.bouton(bas, 'Annuler', self.destroy).pack(side='left')
        self.bouton = theme.bouton(bas, 'Ouvrir cette licence →', self.choisir, principal=True, state='disabled')
        self.bouton.pack(side='right')
        theme.bouton(bas, 'Tout désélectionner', self.tout_deselectionner).pack(side='right', padx=(0, 10))
        theme.bouton(bas, 'Tout sélectionner', self.tout_selectionner).pack(side='right', padx=(0, 10))
        theme.entete_page(cadre, 'Importer depuis Excel', nom_fichier)
        ttk.Label(cadre, text=f'{len(licences)} licence(s) trouvée(s). Choisissez celle à ouvrir : numéro, DEC, montant, '
                  'date de validation et client seront repris ; importateur et fournisseur peuvent venir d’une licence existante. '
                  'Sélection multiple : Cmd/Ctrl ou Maj + clic, ou « Tout sélectionner ».',
                  style='SousTitre.TLabel', wraplength=980).pack(anchor='w', pady=(0, 10))
        reprise = ttk.Frame(cadre, padding=12, relief='solid', borderwidth=1)
        reprise.pack(fill='x', pady=(0, 10))
        reprise.columnconfigure(1, weight=1)
        ttk.Label(reprise, text='Reprendre les informations d’une licence existante', style='Section.TLabel').grid(
            row=0, column=0, columnspan=2, sticky='w', pady=(0, 6))
        self.choix_sources, self.apercus = {}, {}
        for i, (cle, titre, aucun) in enumerate((('importateur', 'Importateur / client', self.AUCUN_IMPORTATEUR),
                                                 ('fournisseur', 'Fournisseur', self.AUCUN_FOURNISSEUR)), 1):
            ttk.Label(reprise, text=titre).grid(row=i * 2 - 1, column=0, sticky='w', padx=(0, 12), pady=(4, 0))
            variable = tk.StringVar(value=aucun)
            liste = ttk.Combobox(reprise, textvariable=variable, state='readonly',
                                 values=[aucun] + [s['libelle'] for s in self.sources[cle]])
            liste.grid(row=i * 2 - 1, column=1, sticky='ew', pady=(4, 0))
            liste.bind('<<ComboboxSelected>>', lambda _, c=cle: self.source_modifiee(c))
            self.choix_sources[cle] = variable
            self.apercus[cle] = tk.StringVar()
            ttk.Label(reprise, textvariable=self.apercus[cle], style='Doux.TLabel', wraplength=820).grid(
                row=i * 2, column=1, sticky='w')
        if not any(self.sources.values()):
            ttk.Label(reprise, text='Aucune licence ouverte pour l’instant : rien à reprendre.', style='Doux.TLabel').grid(
                row=5, column=0, columnspan=2, sticky='w', pady=(6, 0))
        filtre = ttk.Frame(cadre)
        filtre.pack(fill='x', pady=(0, 8))
        ttk.Label(filtre, text='Rechercher').pack(side='left', padx=(0, 8))
        self.recherche = tk.StringVar()
        ttk.Entry(filtre, textvariable=self.recherche, width=30).pack(side='left')
        self.masquer = tk.BooleanVar(value=False)
        ttk.Checkbutton(filtre, text='Masquer les licences expirées ou déjà ouvertes', variable=self.masquer,
                        command=self.afficher).pack(side='left', padx=(18, 0))
        self.recherche.trace_add('write', self.afficher)
        zone, self.table = theme.tableau(cadre, [
            ('numero', 'Déclaration', 250, 'w'), ('client', 'Désignation client', 230, 'w'),
            ('montant', 'Montant licence', 130, 'e'), ('devise', 'Devise', 60, 'center'),
            ('validation', 'Date de validation', 120, 'center'), ('extreme', 'Extrême validité', 120, 'center'),
            ('etat', 'État', 110, 'center')], hauteur=14)
        zone.pack(fill='both', expand=True)
        self.table.configure(selectmode='extended')
        self.table.bind('<<TreeviewSelect>>', lambda _: self.selection_modifiee())
        self.table.bind('<Double-1>', lambda _: self.choisir())
        self.afficher()
        self.grab_set()

    def etat(self, ligne):
        if ligne['numero_validation'].upper() in self.deja:
            return 'Déjà ouverte'
        if excel.expiree(ligne):
            return 'Expirée'
        return 'Disponible'

    def afficher(self, *_):
        self.table.delete(*self.table.get_children())
        terme = self.recherche.get().strip().casefold()
        for i, ligne in enumerate(self.licences):
            etat = self.etat(ligne)
            if self.masquer.get() and etat != 'Disponible':
                continue
            texte = ' '.join(str(ligne.get(c, '')) for c in ('numero_validation', 'soussigne', 'montant_fob', 'date_validation'))
            if terme and terme not in texte.casefold():
                continue
            try:
                montant = nombre(float(ligne['montant_fob']), 2)
            except ValueError:
                montant = ligne['montant_fob']
            self.table.insert('', 'end', iid=str(i), values=(
                ligne['numero_validation'], ligne['soussigne'], montant, ligne['devise'],
                ligne['date_validation'], ligne['date_extreme'], etat))
        self.selection_modifiee()

    def source_modifiee(self, cle):
        libelle = self.choix_sources[cle].get()
        source = next((s for s in self.sources[cle] if s['libelle'] == libelle), None)
        coordonnees = source['coordonnees'] if source else None
        setattr(self, cle, coordonnees)
        if coordonnees:
            details = [coordonnees.get(c, '') for c in ('adresse', 'telephone', 'email', 'identifiants')]
            self.apercus[cle].set(' · '.join(' '.join(str(d).split()) for d in details if d))
        else:
            self.apercus[cle].set('')

    def selection_modifiee(self):
        n = len(self.table.selection())
        self.bouton.configure(state='normal' if n else 'disabled',
                              text='Ouvrir cette licence →' if n <= 1 else f'Ouvrir les {n} licences →')

    def tout_selectionner(self):
        self.table.selection_set(self.table.get_children())

    def tout_deselectionner(self):
        self.table.selection_remove(self.table.selection())

    def choisir(self):
        selection = self.table.selection()
        if not selection:
            return
        self.resultat = [self.licences[int(i)] for i in sorted(selection, key=int)]
        self.destroy()


def _cle_date(texte):
    parties = str(texte).split('/')
    return tuple(reversed(parties)) if len(parties) == 3 else ('',)
