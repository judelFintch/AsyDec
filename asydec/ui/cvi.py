"""Compléments CVI : reprise de la première répartition et références proposées."""
import tkinter as tk
from tkinter import ttk
from asydec.declarations import cvi
from asydec.ui import theme


class ComplementsCVI(tk.Toplevel):
    def __init__(self, parent, licence):
        super().__init__(parent)
        self.title('CVI et BL · première répartition')
        self.transient(parent.winfo_toplevel())
        self.resultat = None
        self.geometry('880x760')
        self.minsize(740, 600)
        self.variables = {}
        valeurs = cvi.proposer_complements(licence)
        donnees = cvi.donnees(licence, cvi.premiere_part(licence), valeurs)
        cadre = ttk.Frame(self, padding=20)
        cadre.pack(fill='both', expand=True)
        theme.entete_page(cadre, 'Remplissage CVI et BL', 'CVI et BL · données de la licence')
        ttk.Label(cadre, text='Les références CVI sont réservées automatiquement, incrémentales et uniques. '
                  'Vérifiez-les. Infos BL reprend les valeurs du modèle fourni ; la description des marchandises sera PRODUIT.',
                  style='SousTitre.TLabel', wraplength=800).pack(anchor='w', pady=(0, 12))
        resume = ' · '.join(f'{c} : {donnees[c]}' for c in ('NUMERO_E', 'NUMERO_LIQUIDATION', 'NUMERO_QUITTANCE', 'PLAQUE'))
        ttk.Label(cadre, text=resume, wraplength=800).pack(anchor='w', pady=(0, 12))
        carnet = ttk.Notebook(cadre)
        carnet.pack(fill='both', expand=True)
        groupes = (
            ('CVI', [(cle, titre) for cle, titre in cvi.CHAMPS_COMPLEMENTAIRES.items() if cle not in cvi.CHAMPS_BL]),
            ('Infos BL', list(cvi.CHAMPS_BL.items())),
        )
        for titre_page, elements in groupes:
            champs = ttk.Frame(carnet, padding=12)
            carnet.add(champs, text=titre_page)
            for colonne in (0, 1):
                champs.columnconfigure(colonne, weight=1)
            for i, (cle, titre) in enumerate(elements):
                case = ttk.Frame(champs, padding=(0, 0, 12, 10))
                case.grid(row=i//2, column=i%2, sticky='ew')
                ttk.Label(case, text=titre, style='Doux.TLabel', wraplength=370).pack(anchor='w')
                variable = tk.StringVar(value=valeurs.get(cle, ''))
                self.variables[cle] = variable
                ttk.Entry(case, textvariable=variable, state='readonly' if cle in cvi.REFERENCES_CVI or cle == 'NUMERO_BL' else 'normal').pack(fill='x', pady=(4, 0))
        ttk.Label(cadre, text='BL : ' + (donnees.get('NUMERO_BL') or 'Non renseigné')
                  + ' · Date : ' + (donnees.get('DATE_BL') or 'absente'),
                  style='Doux.TLabel', wraplength=800).pack(anchor='w', pady=(8, 0))
        self.erreur = tk.StringVar()
        ttk.Label(cadre, textvariable=self.erreur, style='Erreur.TLabel', wraplength=800).pack(anchor='w')
        pied = ttk.Frame(cadre)
        pied.pack(fill='x', pady=(12, 0))
        theme.bouton(pied, 'Annuler', self.destroy).pack(side='left')
        theme.bouton(pied, 'Remplir CVI et BL', self.valider, principal=True).pack(side='right')
        self.grab_set()
        self.protocol('WM_DELETE_WINDOW', self.destroy)

    def valider(self):
        valeurs = {cle: v.get().strip() for cle, v in self.variables.items()}
        manquants = [titre for cle, titre in cvi.CHAMPS_COMPLEMENTAIRES.items() if not valeurs[cle]]
        if manquants:
            self.erreur.set('À compléter : ' + ', '.join(manquants))
            return
        valeurs['DESIGNATION'] = cvi.adapter_designation(valeurs['DESIGNATION'])
        self.resultat = valeurs
        self.destroy()
