"""Note de 1 à 5 sur un modèle généré, donnée d'après ce que l'utilisateur voit ; elle guide les générations suivantes."""
import tkinter as tk
from tkinter import ttk

from asydec.declarations.modeles_generes import NOTES
from asydec.ui import theme


def etoiles(note):
    """« ★★★★☆ » pour 4 ; « — » sans note."""
    return '★' * note + '☆' * (5 - note) if note else '—'


class BarreNotation(ttk.Frame):
    """Cinq boutons (1 Mauvais … 5 Excellent) et un commentaire ; noter(note, commentaire) enregistre."""

    def __init__(self, parent, noter):
        super().__init__(parent)
        ttk.Label(self, text='Votre note', style='Doux.TLabel').pack(side='left', padx=(0, 6))
        self.boutons = []
        for note in sorted(NOTES):
            b = theme.bouton(self, f'{note} · {NOTES[note]}', lambda n=note: noter(n, self.var_commentaire.get()))
            b.pack(side='left', padx=2)
            self.boutons.append(b)
        ttk.Label(self, text='Commentaire', style='Doux.TLabel').pack(side='left', padx=(12, 4))
        self.var_commentaire = tk.StringVar()
        self.champ = ttk.Entry(self, textvariable=self.var_commentaire, width=34)
        self.champ.pack(side='left')
        self.var_actuelle = tk.StringVar()
        ttk.Label(self, textvariable=self.var_actuelle, style='Doux.TLabel').pack(side='left', padx=(10, 0))

    def definir(self, note, commentaire='', actif=True):
        """Affiche la note actuelle du modèle (None = pas encore noté)."""
        self.var_commentaire.set(commentaire or '')
        self.var_actuelle.set(f'Actuelle : {etoiles(note)} {NOTES[note]}' if note else 'Pas encore noté')
        etat = 'normal' if actif else 'disabled'
        for b in self.boutons:
            b.configure(state=etat)
        self.champ.configure(state=etat)
