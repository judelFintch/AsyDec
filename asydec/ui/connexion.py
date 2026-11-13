"""Connexion administrateur locale, indépendante des écrans de références."""
import tkinter as tk
from tkinter import ttk, messagebox

from asydec.systeme import gestion_locale as local
from asydec.ui import theme


def demander_connexion(parent=None):
    fen = tk.Tk() if parent is None else tk.Toplevel(parent)
    fen.title('AsyDec — Connexion')
    fen.geometry('560x660')
    fen.resizable(False, False)
    fen.configure(bg=theme.FOND)
    if parent is None:
        theme.appliquer(fen)
    elif parent.state() != 'withdrawn':
        fen.transient(parent)
    fen.resultat = None
    creation = not local.compte_existe()
    recuperation = False
    cadre = ttk.Frame(fen, padding=30)
    cadre.pack(fill='both', expand=True)
    ttk.Label(cadre, text='AsyDec', style='Titre.TLabel').pack(anchor='w')
    titre = tk.StringVar(value='Créer le compte administrateur' if creation else 'Ouvrir votre session')
    ttk.Label(cadre, textvariable=titre,
              style='Section.TLabel').pack(anchor='w', pady=(8, 12))
    ttk.Label(cadre, text='Compte enregistré sur cet ordinateur. Pour reprendre vos dossiers sur une autre machine, '
              'importez un export .asydec depuis Paramètres › Transfert après connexion.',
              wraplength=490, style='Doux.TLabel').pack(anchor='w')
    identifiant = tk.StringVar()
    mot_de_passe = tk.StringVar()
    confirmation = tk.StringVar()
    ttk.Label(cadre, text='Identifiant').pack(anchor='w', pady=(15, 3))
    entree_id = ttk.Entry(cadre, textvariable=identifiant)
    entree_id.pack(fill='x')
    ttk.Label(cadre, text=f'Mot de passe — {local.MIN_MOT_DE_PASSE} caractères minimum').pack(anchor='w', pady=(12, 3))
    entree_mdp = ttk.Entry(cadre, textvariable=mot_de_passe, show='•')
    entree_mdp.pack(fill='x')
    confirmation_cadre = ttk.Frame(cadre)
    ttk.Label(confirmation_cadre, text='Confirmer le mot de passe').pack(anchor='w', pady=(12, 3))
    ttk.Entry(confirmation_cadre, textvariable=confirmation, show='•').pack(fill='x')
    if creation:
        confirmation_cadre.pack(fill='x')
    erreur_initiale = ''
    if not creation:
        try:
            identifiant.set(local.identifiant_compte())
        except ValueError as exc:
            erreur_initiale = str(exc)
    erreur = tk.StringVar(value=erreur_initiale)
    erreur_label = ttk.Label(cadre, textvariable=erreur, style='Erreur.TLabel', wraplength=490)
    erreur_label.pack(anchor='w', pady=12)

    def valider(event=None):
        bouton.configure(state='disabled')
        fen.update_idletasks()
        try:
            if creation:
                if mot_de_passe.get() != confirmation.get():
                    raise ValueError('Les mots de passe ne correspondent pas.')
                if recuperation:
                    if not messagebox.askyesno('Créer un compte après sauvegarde',
                        'Le compte local est illisible. Une copie de son fichier sera conservée avant de créer '
                        'le nouveau compte.\n\nVos dossiers, factures, modèles et numéros réservés restent conservés.\n\n'
                        'Continuer ?', parent=fen):
                        bouton.configure(state='normal')
                        return
                    utilisateur, sauvegarde = local.recreer_compte_illisible(identifiant.get(), mot_de_passe.get())
                    messagebox.showinfo('Nouveau compte créé',
                        f'Vos données sont conservées.\nCopie de l’ancien compte :\n{sauvegarde}', parent=fen)
                else:
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

    def choisir_creation():
        nonlocal creation, recuperation
        recuperation = False
        if local.compte_existe():
            try:
                local.identifiant_compte()
            except local.CompteIllisible:
                recuperation = True
            except (ValueError, OSError) as exc:
                erreur.set(str(exc))
                return
            else:
                erreur.set('Un compte lisible existe déjà sur cet ordinateur. Connectez-vous avec ce compte.')
                return
        creation = True
        titre.set('Remplacer le compte illisible' if recuperation else 'Créer le compte administrateur')
        confirmation_cadre.pack(fill='x', before=erreur_label)
        bouton.configure(text='Créer mon compte et continuer')
        identifiant.set('')
        mot_de_passe.set('')
        confirmation.set('')
        erreur.set('Le fichier du compte illisible sera sauvegardé. Vos données restent conservées.' if recuperation else '')
        entree_id.focus_set()

    theme.bouton(cadre, 'Créer un compte', choisir_creation).pack(fill='x', pady=(8, 0))
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
