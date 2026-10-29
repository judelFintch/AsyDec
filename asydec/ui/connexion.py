"""Connexion administrateur locale, indépendante des écrans de références."""
import tkinter as tk
from tkinter import ttk

from asydec.systeme import gestion_locale as local
from asydec.ui import theme


def demander_connexion(parent=None):
    fen = tk.Tk() if parent is None else tk.Toplevel(parent)
    fen.title('AsyDec — Connexion')
    fen.geometry('520x500')
    fen.resizable(False, False)
    fen.configure(bg=theme.FOND)
    if parent is None:
        theme.appliquer(fen)
    elif parent.state() != 'withdrawn':
        fen.transient(parent)
    fen.resultat = None
    creation = not local.compte_existe()
    cadre = ttk.Frame(fen, padding=30)
    cadre.pack(fill='both', expand=True)
    ttk.Label(cadre, text='AsyDec', style='Titre.TLabel').pack(anchor='w')
    ttk.Label(cadre, text='Créer le compte administrateur' if creation else 'Ouvrir votre session',
              style='Section.TLabel').pack(anchor='w', pady=(8, 12))
    ttk.Label(cadre, text='Compte enregistré sur cet ordinateur.', style='Doux.TLabel').pack(anchor='w')
    identifiant = tk.StringVar()
    mot_de_passe = tk.StringVar()
    confirmation = tk.StringVar()
    ttk.Label(cadre, text='Identifiant').pack(anchor='w', pady=(15, 3))
    entree_id = ttk.Entry(cadre, textvariable=identifiant)
    entree_id.pack(fill='x')
    ttk.Label(cadre, text='Mot de passe' + (f' — {local.MIN_MOT_DE_PASSE} caractères minimum' if creation else '')).pack(anchor='w', pady=(12, 3))
    entree_mdp = ttk.Entry(cadre, textvariable=mot_de_passe, show='•')
    entree_mdp.pack(fill='x')
    if creation:
        ttk.Label(cadre, text='Confirmer le mot de passe').pack(anchor='w', pady=(12, 3))
        ttk.Entry(cadre, textvariable=confirmation, show='•').pack(fill='x')
    else:
        try:
            identifiant.set(local.identifiant_compte())
        except ValueError:
            pass
    erreur = tk.StringVar()
    ttk.Label(cadre, textvariable=erreur, style='Erreur.TLabel', wraplength=450).pack(anchor='w', pady=12)

    def valider(event=None):
        bouton.configure(state='disabled')
        fen.update_idletasks()
        try:
            if creation:
                if mot_de_passe.get() != confirmation.get():
                    raise ValueError('Les mots de passe ne correspondent pas.')
                utilisateur = local.creer_compte(identifiant.get(), mot_de_passe.get())
            else:
                if not local.authentifier(identifiant.get(), mot_de_passe.get()):
                    raise ValueError('Identifiant ou mot de passe incorrect.')
                utilisateur = local.identifiant_compte()
            mot_de_passe.set('')
            confirmation.set('')
            fen.resultat = utilisateur
            fen.destroy()
        except (ValueError, OSError) as exc:
            erreur.set(str(exc))
            mot_de_passe.set('')
            confirmation.set('')
            bouton.configure(state='normal')
            entree_mdp.focus_set()

    bouton = theme.bouton(cadre, 'Créer mon compte et continuer' if creation else 'Se connecter', valider, principal=True)
    bouton.pack(fill='x', pady=4)
    fen.bind('<Return>', valider)
    fen.protocol('WM_DELETE_WINDOW', fen.destroy)
    if creation:
        entree_id.focus_set()
    else:
        entree_mdp.focus_set()
    if parent is None:
        fen.mainloop()
    else:
        fen.grab_set()
        parent.wait_window(fen)
    return fen.resultat
