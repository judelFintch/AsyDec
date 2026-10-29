"""Accueil et catalogue des espaces métier d'AsyDec."""
from tkinter import ttk

from asydec.ui import theme

# Les écrans métier existants appartiennent au module Friperie.
MODULES = (
    ('friperie', 'Friperie',
     'Déclarations de friperie, articles, modèles, répartitions et références XML.', 'Ouvrir Friperie'),
    ('divers', 'Divers',
     'Déclarations de marchandises diverses, modèles dynamiques et positions tarifaires reprises du XML.', 'Ouvrir Divers'),
)


class PageAccueil(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        theme.entete_page(self, 'Bienvenue dans AsyDec',
                          'Choisissez votre module pour accéder à votre espace de travail.')
        for cle, titre, description, action in MODULES:
            carte = ttk.Frame(self, padding=24, relief='solid', borderwidth=1)
            carte.pack(fill='x', pady=(8, 12))
            ttk.Label(carte, text=titre, style='Titre.TLabel').pack(anchor='w')
            ttk.Label(carte, text=description, style='SousTitre.TLabel',
                      wraplength=700).pack(anchor='w', pady=(8, 18))
            theme.bouton(carte, action, lambda c=cle: app.ouvrir_module(c),
                         principal=cle == 'friperie').pack(anchor='w')


class PageDivers(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        theme.entete_page(self, 'Divers', 'Votre espace pour les marchandises diverses.')
        cadre = ttk.Frame(self, padding=24, relief='solid', borderwidth=1)
        cadre.pack(fill='x', pady=12)
        ttk.Label(cadre, text='Modèles dynamiques', style='Section.TLabel').pack(anchor='w')
        ttk.Label(cadre, text='Chargez un XML de référence pour reprendre ses articles, leurs positions tarifaires et leurs règles de calcul.',
                  wraplength=700, style='SousTitre.TLabel').pack(anchor='w', pady=12)
        theme.bouton(cadre, 'Produire un modèle Divers', lambda: app.ouvrir_module('divers')).pack(anchor='w')
