"""Fenêtre de comparaison descriptive, sans import ni modification des fichiers."""
import tkinter as tk
from tkinter import ttk
from ui import theme
from ui.theme import nombre


def afficher(parent, rapport):
    fen = tk.Toplevel(parent)
    fen.title('Comparer l’aperçu avec un XML')
    fen.geometry('1240x720')
    fen.transient(parent.winfo_toplevel())
    cadre = ttk.Frame(fen, padding=16)
    cadre.pack(fill='both', expand=True)
    theme.entete_page(cadre, 'Aperçu / fichier fourni',
        'Écart = fichier fourni − prévu. Un écart ne prouve pas une erreur de calcul ou une acceptation douanière.')
    ttk.Label(cadre, text=f"Fichier fourni : {rapport['fichier']}\n"
        f"Devise prévue : {rapport['devise_prevue'] or 'absente'} · devise fournie : {rapport['devise_fournie'] or 'absente'}",
        wraplength=1150).pack(anchor='w', pady=6)
    message = theme.Message(cadre)
    message.pack(fill='x', pady=6)
    contexte = rapport['contexte']
    message.afficher('alerte' if contexte else 'ok',
        'Contexte différent ou incomplet : interprétez les écarts fiscaux avec prudence' if contexte else 'Aucune différence détectée dans les champs de contexte comparés',
        contexte[:8])
    zone, table = theme.tableau(cadre, [
        ('article', 'Position · Code', 160, 'w'), ('metrique', 'Mesure', 130, 'w'),
        ('prevu', 'Prévu', 150, 'e'), ('fourni', 'Fichier fourni', 150, 'e'),
        ('ecart', 'Écart', 130, 'e'), ('pourcentage', 'Écart %', 110, 'e'), ('etat', 'Observation', 290, 'w')], 17)
    zone.pack(fill='both', expand=True)
    for ligne in rapport['lignes']:
        decimales = {'ratio': 4, 'poids': 3, 'colis': 0}.get(ligne['metrique'], 2)
        table.insert('', 'end', tags=('total',) if ligne['position'] == 'Total global' else (), values=(
            f"{ligne['position']} · {ligne['code']}", ligne['libelle'],
            nombre(ligne['prevu'], decimales), nombre(ligne['fourni'], decimales),
            nombre(ligne['ecart'], decimales), nombre(ligne['pourcentage'], 2), ligne['etat']))
    details = contexte + rapport['avertissements']
    if details:
        ttk.Label(cadre, text='Détails du contexte et des données', style='Section.TLabel').pack(anchor='w', pady=(8, 2))
        texte = tk.Text(cadre, height=5, wrap='word', font=(theme.POLICE, 11))
        texte.pack(fill='x')
        texte.insert('1.0', '\n'.join(details))
        texte.configure(state='disabled')
    theme.bouton(cadre, 'Fermer', fen.destroy).pack(anchor='e', pady=8)
    return fen
