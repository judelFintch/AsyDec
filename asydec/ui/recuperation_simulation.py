"""Fenêtre de l'étape 8 : écarts entre les XML générés et les XML récupérés de SYDONIA."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from asydec.declarations import recuperation_simulation as regles
from asydec.formats import date_locale
from asydec.ui import theme


class FenetreComparaison(tk.Toplevel):
    FILTRES = {'Tous les écarts': None, 'Modifiés': 'modifie', 'Complétés par SYDONIA': 'complete',
               'Retirés par SYDONIA': 'retire'}

    def __init__(self, parent, licence, comparaisons):
        """comparaisons : [dict(titre, genere, sydonia, importe_le, comparaison)] ;
        une comparaison seule (ancien format) est aussi acceptée."""
        super().__init__(parent)
        if isinstance(comparaisons, dict):
            reference = licence.get('xml_genere', {})
            recuperation = licence.get('recuperation_simulation', {})
            comparaisons = [dict(titre='XML SYDONIA', genere=reference.get('fichier', '—'),
                                 sydonia=recuperation.get('fichier', '—'), importe_le=recuperation.get('importe_le'),
                                 comparaison=comparaisons)]
        self.comparaisons = comparaisons
        self.title('Récupération simulation')
        self.geometry('1100x800')
        self.minsize(820, 600)
        self.transient(parent.winfo_toplevel())
        cadre = ttk.Frame(self, padding=20)
        cadre.pack(fill='both', expand=True)
        theme.entete_page(cadre, '8 · Récupération simulation', licence['numero_validation'])
        theme.bouton(cadre, 'Fermer', self.destroy).pack(side='bottom', anchor='e', pady=(12, 0))
        if len(comparaisons) > 1:
            barre = ttk.Frame(cadre)
            barre.pack(fill='x', pady=(0, 10))
            ttk.Label(barre, text=f'XML SYDONIA importés ({len(comparaisons)})', style='Section.TLabel').pack(side='left')
            self.choix = tk.StringVar()
            libelles = [self._libelle(i, c) for i, c in enumerate(comparaisons)]
            liste = ttk.Combobox(barre, textvariable=self.choix, values=libelles, state='readonly', width=80)
            liste.pack(side='left', padx=10)
            liste.bind('<<ComboboxSelected>>', lambda _: self.afficher(libelles.index(self.choix.get())))
            self.choix.set(libelles[0])
        self.corps = ttk.Frame(cadre)
        self.corps.pack(fill='both', expand=True)
        self.afficher(0)

    @staticmethod
    def _libelle(i, c):
        r = c['comparaison']['resume']
        etat = '✗' if r['controles_differents'] else ('⚠' if r['modifie'] or r['retire'] else '✓')
        return f"{etat} {i + 1}. {Path(str(c['sydonia'])).name} → {c['titre']}"

    def afficher(self, index):
        for widget in self.corps.winfo_children():
            widget.destroy()
        cadre = self.corps
        choisie = self.comparaisons[index]
        comparaison = self.comparaison = choisie['comparaison']
        ttk.Label(cadre, text=f"Comparé au XML attendu de : {choisie['titre']}\n"
                              f"XML généré : {choisie['genere']}\n"
                              f"XML SYDONIA : {choisie['sydonia']} · {self._date(choisie.get('importe_le'))}",
                  style='Doux.TLabel', wraplength=1000, justify='left').pack(anchor='w', pady=(0, 10))

        resume = comparaison['resume']
        message = theme.Message(cadre)
        message.pack(fill='x', pady=(0, 12))
        genre = 'erreur' if resume['controles_differents'] else ('alerte' if resume['modifie'] or resume['retire'] else 'ok')
        message.afficher(genre, regles.conclusion(resume))

        grille = ttk.Frame(cadre)
        grille.pack(fill='x', pady=(0, 12))
        for i, (titre, valeur) in enumerate((('Contrôles clés différents', resume['controles_differents']),
                                             ('Champs modifiés', resume['modifie']),
                                             ('Complétés par SYDONIA', resume['complete']),
                                             ('Retirés par SYDONIA', resume['retire']))):
            grille.columnconfigure(i, weight=1, uniform='resume')
            carte = theme.Carte(grille, titre)
            carte.grid(row=0, column=i, sticky='nsew', padx=(0 if i == 0 else 6, 0))
            carte.definir(str(valeur))

        carnet = ttk.Notebook(cadre)
        carnet.pack(fill='both', expand=True)
        page_controles = ttk.Frame(carnet, padding=10)
        page_ecarts = ttk.Frame(carnet, padding=10)
        carnet.add(page_controles, text='Contrôles clés')
        carnet.add(page_ecarts, text=f"Tous les écarts ({len(comparaison['differences'])})")

        colonnes = [('etat', 'État', 90, 'center'), ('libelle', 'Champ', 260, 'w'),
                    ('genere', 'XML généré', 300, 'w'), ('sydonia', 'XML SYDONIA', 300, 'w')]
        zone, table = theme.tableau(page_controles, colonnes, hauteur=14)
        zone.pack(fill='both', expand=True)
        table.tag_configure('different', foreground=theme.ERREUR)
        for controle in sorted(comparaison['controles'], key=lambda c: c['identique']):
            table.insert('', 'end', values=('✓ Identique' if controle['identique'] else '✗ Différent', controle['libelle'],
                                            controle['genere'] or '—', controle['sydonia'] or '—'),
                         tags=() if controle['identique'] else ('different',))

        barre = ttk.Frame(page_ecarts)
        barre.pack(fill='x', pady=(0, 8))
        ttk.Label(barre, text='Afficher').pack(side='left')
        self.filtre = tk.StringVar(value='Tous les écarts')
        ttk.Combobox(barre, textvariable=self.filtre, values=list(self.FILTRES), state='readonly', width=24).pack(side='left', padx=8)
        ttk.Label(barre, text='Rechercher').pack(side='left', padx=(16, 0))
        self.recherche = tk.StringVar()
        ttk.Entry(barre, textvariable=self.recherche, width=28).pack(side='left', padx=8)
        colonnes = [('genre', 'Type', 170, 'w'), ('libelle', 'Champ', 280, 'w'),
                    ('genere', 'XML généré', 260, 'w'), ('sydonia', 'XML SYDONIA', 260, 'w')]
        zone, self.ecarts = theme.tableau(page_ecarts, colonnes, hauteur=14)
        zone.pack(fill='both', expand=True)
        self.ecarts.tag_configure('modifie', foreground=theme.ERREUR)
        self.ecarts.tag_configure('retire', foreground=theme.ALERTE)
        self.filtre.trace_add('write', self.filtrer)
        self.recherche.trace_add('write', self.filtrer)
        self.filtrer()

    @staticmethod
    def _date(valeur):
        try:
            return date_locale(valeur)
        except (TypeError, ValueError):
            return '—'

    def filtrer(self, *_):
        self.ecarts.delete(*self.ecarts.get_children())
        genre = self.FILTRES.get(self.filtre.get())
        terme = self.recherche.get().strip().casefold()
        for ecart in self.comparaison['differences']:
            if genre and ecart['genre'] != genre:
                continue
            if terme and terme not in ' '.join((ecart['libelle'], ecart['chemin'], ecart['genere'], ecart['sydonia'])).casefold():
                continue
            self.ecarts.insert('', 'end', values=(regles.GENRES[ecart['genre']], ecart['libelle'],
                                                  ecart['genere'] or '—', ecart['sydonia'] or '—'), tags=(ecart['genre'],))
