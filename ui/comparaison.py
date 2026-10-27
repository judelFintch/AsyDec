"""Fenêtre de comparaison descriptive, sans import ni modification des fichiers."""
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import export_pdf
from ui import theme
from ui.theme import nombre


def enregistrer_pdf(parent, nom, fabrique):
    """Demande l'emplacement, crée le PDF par fabrique(chemin), puis propose de l'ouvrir."""
    chemin = filedialog.asksaveasfilename(parent=parent, title='Enregistrer en PDF',
        initialfile=nom, defaultextension='.pdf', filetypes=[('PDF', '*.pdf')])
    if not chemin:
        return None
    try:
        fabrique(chemin)
    except Exception as exc:
        messagebox.showerror('PDF non créé', str(exc), parent=parent)
        return None
    if sys.platform == 'darwin' and messagebox.askyesno('PDF enregistré',
            f'{chemin}\n\nOuvrir le PDF dans Aperçu pour l’imprimer (⌘P) ?', parent=parent):
        subprocess.run(['open', chemin], check=False)
    return chemin


def afficher(parent, rapport):
    fen = tk.Toplevel(parent)
    fen.title('Comparer le XML généré avec un fichier fourni')
    fen.geometry('1240x800')
    fen.transient(parent.winfo_toplevel())
    cadre = ttk.Frame(fen, padding=16)
    cadre.pack(fill='both', expand=True)
    theme.entete_page(cadre, 'XML généré / fichier fourni',
        'Écart = fichier fourni − XML généré. Un écart ne prouve pas une erreur de calcul ou une acceptation douanière.')
    ttk.Label(cadre, text=f"XML généré : {rapport.get('source', '—')}\nFichier fourni : {rapport['fichier']}\n"
        f"Devise du XML généré : {rapport['devise_prevue'] or 'absente'} · devise fournie : {rapport['devise_fournie'] or 'absente'}\n"
        f"Taux XML généré : 1 {rapport['devise_prevue'] or '?'} = {nombre(rapport.get('taux_genere'), 4)} CDF · "
        f"taux fichier fourni : 1 {rapport['devise_fournie'] or '?'} = {nombre(rapport.get('taux_fourni'), 4)} CDF",
        wraplength=1150).pack(anchor='w', pady=6)
    total = next((l for l in rapport['lignes'] if l['position'] == 'Total global' and l['metrique'] == 'taxes'), None)
    if total:
        ttk.Label(cadre, text=(f"Total déclaration estimé (XML généré) : {nombre(total['prevu'], 2)} CDF\n"
            f"Total déclaration comparée : {nombre(total['fourni'], 2)} CDF\n"
            f"Différence : {nombre(total['ecart'], 2)} CDF ({nombre(total['pourcentage'], 2)} %)"),
            style='Section.TLabel', wraplength=1150).pack(anchor='w', pady=(8, 2))
        ttk.Label(cadre, text='Taxes totales déclarées dans les deux XML.', style='Doux.TLabel').pack(anchor='w')
    globales = next((l for l in rapport['lignes'] if l['metrique'] == 'taxes_globales'), None)
    if globales:
        ttk.Label(cadre, text=(f"Taxes globales : XML généré {nombre(globales['prevu'], 2)} CDF · "
            f"Fichier fourni {nombre(globales['fourni'], 2)} CDF · "
            f"Écart {nombre(globales['ecart'], 2)} CDF ({nombre(globales['pourcentage'], 2)} %)"),
            style='Section.TLabel', wraplength=1150).pack(anchor='w', pady=8)
    message = theme.Message(cadre)
    message.pack(fill='x', pady=6)
    contexte = rapport['contexte']
    message.afficher('alerte' if contexte else 'ok',
        'Contexte différent ou incomplet : interprétez les écarts fiscaux avec prudence' if contexte else 'Aucune différence détectée dans les champs de contexte comparés',
        contexte[:8])
    zone, table = theme.tableau(cadre, [
        ('article', 'Position · Code', 160, 'w'), ('metrique', 'Mesure', 130, 'w'),
        ('prevu', 'XML généré', 150, 'e'), ('fourni', 'Fichier fourni', 150, 'e'),
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
    boutons = ttk.Frame(cadre)
    boutons.pack(fill='x', pady=8)
    theme.bouton(boutons, 'Fermer', fen.destroy).pack(side='right')
    utilisateur = getattr(parent.winfo_toplevel(), 'utilisateur', '')
    theme.bouton(boutons, 'Enregistrer en PDF…', lambda: enregistrer_pdf(fen, 'Comparaison XML.pdf',
        lambda chemin: export_pdf.pdf_comparaison(rapport, chemin, utilisateur))).pack(side='right', padx=8)
    return fen
