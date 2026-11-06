"""Étape de saisie des informations de déclaration."""
import sqlite3
import tkinter as tk
from tkinter import ttk
from asydec.declarations import informations_declaration as regles, licences_ouvertes
from asydec.ui import theme


class InformationsDeclaration(tk.Toplevel):
    def __init__(self, parent, app, licence, apres_validation):
        super().__init__(parent)
        self.app, self.licence = app, licence
        self.apres_validation = apres_validation
        self.title('Informations déclaration')
        self.geometry('820x780')
        self.minsize(740, 680)
        self.transient(parent.winfo_toplevel())
        cadre = ttk.Frame(self, padding=20)
        cadre.pack(fill='both', expand=True)
        theme.entete_page(cadre, '3 · Informations déclaration', licence['numero_validation'])
        reperes = ttk.Frame(cadre, padding=12, relief='solid', borderwidth=1)
        reperes.pack(fill='x', pady=(0, 12))
        for cle, titre in (('date_validation', 'Validation licence'), ('date_bl', 'Date du BL')):
            valeur = licence.get(cle)
            try:
                texte = regles.lire_date(valeur).strftime('%d/%m/%Y')
            except ValueError:
                texte = 'Non renseignée'
            colonne = ttk.Frame(reperes)
            colonne.pack(side='left', fill='x', expand=True)
            ttk.Label(colonne, text=titre, style='Doux.TLabel').pack(anchor='w')
            ttk.Label(colonne, text=texte, style='Section.TLabel').pack(anchor='w', pady=(4, 0))
        ttk.Label(cadre, text='Complétez les informations connues avant la dernière étape : génération XML.',
                  style='SousTitre.TLabel', wraplength=740).pack(anchor='w', pady=(0, 14))
        informations = licence.get('informations_declaration', {})
        self.calcul_possible = True
        try:
            proposition = regles.proposer_date_enregistrement(licence.get('date_bl'))
            date_auto = proposition['date'].strftime('%d/%m/%Y')
            anciennes = dict(informations)
            if anciennes.get('date_liquidation') and not anciennes.get('date_cvi'):
                anciennes['date_cvi'] = regles.proposer_date_cvi(anciennes['date_liquidation']).strftime('%d/%m/%Y')
            if anciennes.get('date_enregistrement') == date_auto and all(anciennes.get(c) for c in regles.DATES_AUTO):
                try:
                    regles.verifier(anciennes)
                    dates_auto = {c: anciennes[c] for c in regles.DATES_AUTO}
                except ValueError:
                    dates_auto = regles.proposer_dates_declaration(licence.get('date_bl'))
            else:
                dates_auto = regles.proposer_dates_declaration(licence.get('date_bl'))
            explication = f"BL du {regles.lire_date(licence['date_bl']):%d/%m/%Y} → date proposée : {date_auto}"
            explication += ' · Dernier jour ouvrable entre un et deux mois après le BL.'
            explication += ' · CVI : 2 à 4 jours après la liquidation.'
        except ValueError as exc:
            self.calcul_possible = False
            dates_auto = {c:'' for c in regles.DATES_AUTO}
            date_auto = ''
            explication = str(exc)
        ttk.Label(cadre, text=explication, style='Doux.TLabel' if self.calcul_possible else 'Erreur.TLabel',
                  wraplength=740).pack(anchor='w', pady=(0, 12))
        self.carnet = ttk.Notebook(cadre)
        self.carnet.pack(fill='x', pady=(0, 12))
        chronologie = ttk.Frame(self.carnet, padding=14)
        complements = ttk.Frame(self.carnet, padding=14)
        self.carnet.add(chronologie, text='Numéros et dates')
        self.carnet.add(complements, text='Déclaration et transport')
        self.champs = {}
        for page, champs in ((chronologie, regles.CHAMPS[:8]), (complements, regles.CHAMPS[8:])):
            for colonne in (0, 1):
                page.columnconfigure(colonne, weight=1, uniform='champ')
            for i, (cle, titre, _) in enumerate(champs):
                case = ttk.Frame(page, padding=(0, 0, 16 if i % 2 == 0 else 0, 12))
                case.grid(row=i//2, column=i%2, sticky='ew')
                ttk.Label(case, text=titre + (' *' if cle in ('numero_e','numero_liquidation','numero_quittance') else ''), style='Doux.TLabel').pack(anchor='w', pady=(0, 4))
                variable = tk.StringVar(value=dates_auto[cle] if cle in regles.DATES_AUTO else informations.get(cle, ''))
                self.champs[cle] = variable
                ttk.Entry(case, textvariable=variable, state='readonly' if cle in regles.DATES_AUTO else 'normal').pack(fill='x')
        ttk.Label(chronologie, text='Saisie pour la première part · E, liquidation et manifeste suivants : +1 à +6.\n'
                  'Q commun aux cinq premières parts, puis deuxième Q pour les suivantes.\n'
                  'Week-ends et fériés RDC exclus · E ≤ liquidation ≤ quittance ≤ aujourd’hui.',
                  style='Doux.TLabel', wraplength=700).grid(row=4, column=0, columnspan=2, sticky='w', pady=6)
        theme.bouton(chronologie, 'Reproposer liquidation, quittance et CVI', self.reproposer,
                     state='normal' if self.calcul_possible else 'disabled').grid(row=5,column=0,columnspan=2,sticky='w',pady=6)
        ttk.Label(cadre, text='Observations', style='Doux.TLabel').pack(anchor='w')
        self.observations = tk.Text(cadre, height=3, wrap='word', font=(theme.POLICE, 12))
        self.observations.pack(fill='both', expand=True, pady=(4, 12))
        self.observations.insert('1.0', informations.get('observations', ''))
        self.erreur = tk.StringVar()
        ttk.Label(cadre, textvariable=self.erreur, style='Erreur.TLabel', wraplength=740).pack(anchor='w')
        actions = ttk.Frame(cadre)
        actions.pack(fill='x', pady=(12, 0))
        theme.bouton(actions, 'Annuler', self.destroy).pack(side='left')
        theme.bouton(actions, 'Enregistrer les informations', self.enregistrer, principal=True,
                     state='normal' if self.calcul_possible else 'disabled').pack(side='right')

    def enregistrer(self):
        if self.app.session_verrouillee or not self.calcul_possible:
            return
        valeurs = {cle: v.get() for cle, v in self.champs.items()}
        valeurs['observations'] = self.observations.get('1.0', 'end-1c')
        try:
            licences_ouvertes.enregistrer_informations_declaration(self.licence['numero_validation'], valeurs)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.erreur.set(str(exc))
            return
        self.apres_validation()
        self.destroy()

    def reproposer(self):
        if self.app.session_verrouillee or not self.calcul_possible:
            return
        try:
            dates = regles.proposer_dates_declaration(self.licence.get('date_bl'))
        except ValueError as exc:
            self.erreur.set(str(exc))
            return
        for cle, valeur in dates.items():
            self.champs[cle].set(valeur)
        self.erreur.set('')
