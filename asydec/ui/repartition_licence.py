"""Répartition du FOB puis confirmation du poids par part."""
import sqlite3
from decimal import Decimal
import tkinter as tk
from tkinter import ttk

from asydec.declarations import conteneurs, licences_ouvertes, repartition_licence as calcul
from asydec.formats import nombre
from asydec.ui import theme, synthese_licence


class FenetreRepartition(tk.Toplevel):
    def __init__(self, parent, app, licence, apres_validation):
        super().__init__(parent)
        self.app, self.licence = app, licence
        self.apres_validation = apres_validation
        self.parts = None
        self.plaques = [p.get('plaque') for p in licence.get('repartition', {}).get('parts', [])]
        self.conteneurs = [dict(conteneur=p.get('conteneur'), scelle=p.get('scelle'))
                           for p in licence.get('repartition', {}).get('parts', [])]
        self.title('Répartition de la licence')
        self.geometry('1080x780')
        self.minsize(700, 600)
        self.transient(parent.winfo_toplevel())
        cadre = ttk.Frame(self, padding=20)
        cadre.pack(fill='both', expand=True)
        # Barre du bas placée en premier : toujours visible, ce sont les tableaux qui rétrécissent.
        bas = ttk.Frame(cadre)
        bas.pack(side='bottom', fill='x')
        self.resume = tk.StringVar(value='Calculez d’abord la répartition pour proposer les poids.')
        ttk.Label(bas, textvariable=self.resume, style='SousTitre.TLabel', wraplength=900).pack(anchor='w', pady=(8, 4))
        self.erreur = tk.StringVar()
        ttk.Label(bas, textvariable=self.erreur, style='Erreur.TLabel', wraplength=900).pack(anchor='w')
        actions = ttk.Frame(bas)
        actions.pack(fill='x', pady=(10, 0))
        theme.entete_page(cadre, 'Répartition de la licence', licence['numero_validation'])
        self.fob = licence['montant_fob']
        ttk.Label(cadre, text=f'FOB initial : {nombre(calcul.montant(self.fob), 2)} USD', style='Section.TLabel').pack(anchor='w')
        ttk.Label(cadre, text='1 · Répartir en parts égales de 120 000 USD maximum. Le total est conservé au centime.',
                  style='SousTitre.TLabel', wraplength=730).pack(anchor='w', pady=8)
        # Options facultatives : sans rien changer, le calcul automatique actuel s'applique.
        enregistree = licence.get('repartition') or {}
        options = ttk.Frame(cadre)
        options.pack(anchor='w', fill='x', pady=(0, 8))
        ttk.Label(options, text='Nombre de parts').pack(side='left', padx=(0, 8))
        choisi = enregistree.get('nombre_parts_choisi')
        self.nombre_parts = tk.StringVar(value='' if choisi is None else str(choisi))
        ttk.Entry(options, textvariable=self.nombre_parts, width=6).pack(side='left')
        ttk.Label(options, text='vide = automatique', style='Doux.TLabel').pack(side='left', padx=(6, 24))
        self.sans_plafond = tk.BooleanVar(value=not enregistree.get('plafond_actif', True))
        ttk.Checkbutton(options, text='Retirer le plafond de 120 000 USD', variable=self.sans_plafond,
                        command=self.options_modifiees).pack(side='left')
        self.nombre_parts.trace_add('write', self.options_modifiees)
        self.texte_options = tk.StringVar()
        ttk.Label(cadre, textvariable=self.texte_options, style='Doux.TLabel', wraplength=900).pack(anchor='w', pady=(0, 6))
        self.decrire_options()
        theme.bouton(cadre, 'Calculer la répartition', self.repartir, principal=True).pack(anchor='w', pady=(0, 12))
        self.etape_poids = ttk.Frame(cadre, padding=14, relief='solid', borderwidth=1)
        ttk.Label(self.etape_poids, text='2 · Confirmer le poids de chaque part', style='Section.TLabel').pack(anchor='w')
        ttk.Label(self.etape_poids, text='Même poids pour toutes les parts, entre 22 000 et 24 000 kg. Proposition : 23 000 kg.',
                  style='Doux.TLabel', wraplength=700).pack(anchor='w', pady=6)
        ligne = ttk.Frame(self.etape_poids)
        ligne.pack(fill='x')
        ttk.Label(ligne, text='Poids par part (kg)').pack(side='left', padx=(0, 12))
        self.poids = tk.StringVar(value=str(licence.get('repartition', {}).get('poids_par_part_kg', calcul.POIDS_PROPOSE)))
        ttk.Entry(ligne, textvariable=self.poids, width=12).pack(side='left')
        self.poids.trace_add('write', self.actualiser)
        self.zone_table = ttk.Frame(cadre)
        self.zone_table.pack(fill='both', expand=True, pady=12)
        self.table = ttk.Treeview(self.zone_table, columns=('part', 'fob', 'poids', 'plaque', 'conteneur', 'scelle'), show='headings', height=4)
        for cle, titre in [('part', 'Part'), ('fob', 'FOB (USD)'), ('poids', 'Poids proposé (kg)'), ('plaque', 'Plaques proposées'),
                           ('conteneur', 'Conteneur'), ('scelle', 'Scellé')]:
            self.table.heading(cle, text=titre)
            self.table.column(cle, width={'part': 50, 'plaque': 190, 'conteneur': 130, 'scelle': 100}.get(cle, 120),
                              anchor='e' if cle in ('fob','poids') else 'center')
        defilement = ttk.Scrollbar(self.zone_table, orient='vertical', command=self.table.yview)
        defilement.pack(side='right', fill='y')
        self.table.configure(yscrollcommand=defilement.set)
        self.table.pack(fill='both', expand=True)
        ttk.Label(cadre, text='Articles par part · quantités divisées à l’identique', style='Section.TLabel').pack(anchor='w', pady=(4, 6))
        zone_articles, self.articles = theme.tableau(cadre, [
            ('numero', 'N°', 40, 'center'), ('designation', 'Désignation', 300, 'w'), ('unite', 'Unité', 70, 'w'),
            ('total', 'Qté totale', 110, 'e'), ('part', 'Qté par part', 120, 'e'), ('valeur', 'Valeur par part (USD)', 150, 'e')], hauteur=5)
        zone_articles.pack(fill='both', expand=True)
        theme.bouton(actions, 'Annuler', self.destroy).pack(side='left')
        self.valider_bouton = theme.bouton(actions, 'Valider la répartition et les poids', self.valider, principal=True, state='disabled')
        self.valider_bouton.pack(side='right')
        if licence.get('repartition'):
            self.repartir()

    def options(self):
        return dict(nombre=self.nombre_parts.get().strip() or None, plafond=not self.sans_plafond.get())

    def decrire_options(self):
        nombre = self.nombre_parts.get().strip()
        plafond = not self.sans_plafond.get()
        if not nombre and plafond:
            texte = 'Par défaut : nombre de parts calculé automatiquement, 120 000 USD maximum par part.'
        else:
            texte = ((f'{nombre} part(s) demandée(s)' if nombre else 'Nombre de parts automatique')
                     + (' · plafond de 120 000 USD conservé.' if plafond else ' · plafond de 120 000 USD retiré.')
                     + ' Les parts restent égales et le total conservé au centime.')
        self.texte_options.set(texte)

    def options_modifiees(self, *_):
        self.decrire_options()
        if self.parts is not None:
            self.repartir()

    def repartir(self):
        if self.app.session_verrouillee:
            return
        try:
            proposition = calcul.preparer(self.fob, calcul.POIDS_PROPOSE, self.licence.get('produits'), **self.options())
            self.parts = [Decimal(p['fob']) for p in proposition['parts']]
        except ValueError as exc:
            # Choix impossible (ex. trop peu de parts avec le plafond) : rien n'est validable.
            self.erreur.set(str(exc))
            self.valider_bouton.configure(state='disabled')
            self.table.delete(*self.table.get_children())
            self.articles.delete(*self.articles.get_children())
            self.resume.set('Corrigez le nombre de parts ou le plafond pour recalculer.')
            return
        self.plaques = calcul.proposer_plaques(len(self.parts), self.plaques)
        self.conteneurs = conteneurs.proposer(len(self.parts), self.conteneurs)
        self.etape_poids.pack(fill='x', before=self.zone_table)
        self.actualiser()

    def actualiser(self, *_):
        if self.parts is None:
            return
        self.table.delete(*self.table.get_children())
        try:
            proposition = calcul.preparer(self.fob, self.poids.get(), self.licence.get('produits'), **self.options())
        except ValueError as exc:
            self.erreur.set(str(exc))
            self.valider_bouton.configure(state='disabled')
            for i, fob in enumerate(self.parts, 1):
                c = self.conteneurs[i-1]
                self.table.insert('', 'end', values=(i, nombre(fob, 2), 'À corriger', self.plaques[i-1], c['conteneur'], c['scelle']))
            return
        self.erreur.set('')
        self.valider_bouton.configure(state='normal')
        for part, fob in zip(proposition['parts'], self.parts):
            c = self.conteneurs[part['numero']-1]
            self.table.insert('', 'end', values=(part['numero'], nombre(fob, 2), nombre(part['poids_kg']), self.plaques[part['numero']-1],
                                                 c['conteneur'], c['scelle']))
        self.afficher_articles(proposition['parts'])
        self.resume.set(f"{len(self.parts)} part(s) · Total FOB : {nombre(sum(self.parts), 2)} USD · Poids total proposé : {nombre(proposition['poids_total_kg'])} kg")

    def afficher_articles(self, parts):
        self.articles.delete(*self.articles.get_children())
        if not parts or not parts[0].get('articles'):
            self.articles.insert('', 'end', values=('', 'Quantités non divisées : les articles ne correspondent pas au FOB.', '', '', '', ''))
            return
        for i, produit in enumerate(self.licence.get('produits') or []):
            lignes = [p['articles'][i] for p in parts]
            quantites = sorted({Decimal(l['quantite']) for l in lignes}, reverse=True)
            valeurs = sorted({Decimal(l['valeur']) for l in lignes}, reverse=True)
            self.articles.insert('', 'end', values=(
                i + 1, lignes[0]['designation'], synthese_licence.libelle_unite(lignes[0]['unite']),
                synthese_licence.quantite(synthese_licence.decimal(produit.get('quantite'))),
                ' / '.join(synthese_licence.quantite(q) for q in quantites),
                ' / '.join(nombre(v, 2) for v in valeurs)))

    def valider(self):
        if self.app.session_verrouillee or self.parts is None:
            return
        try:
            licences_ouvertes.enregistrer_repartition(self.licence['numero_validation'], self.fob, self.poids.get(), plaques=self.plaques,
                                                    paires_conteneurs=self.conteneurs,
                                                    nombre_parts=self.options()['nombre'], plafond=self.options()['plafond'])
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.erreur.set(str(exc))
            return
        self.apres_validation()
        self.destroy()
