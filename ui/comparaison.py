"""Fenêtre de comparaison descriptive, sans import ni modification des fichiers."""
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import export_pdf
from ui import theme
from ui.theme import nombre


def dossier_pdf(parent, importateur):
    """Dossier « 4 - PDF » de l'importateur, ou None si on ne peut pas le déterminer."""
    try:
        import generer
        table = getattr(parent.winfo_toplevel(), 'table_imp', None)
        return generer.dossier_rangement(importateur, 'pdf', table) if importateur else None
    except Exception:  # noqa: BLE001 - la fenêtre s'ouvrira alors à l'emplacement habituel
        return None


def enregistrer_pdf(parent, nom, fabrique, dossier=None):
    """Demande l'emplacement (dossier de rangement proposé), crée le PDF, puis propose de l'ouvrir."""
    options = {'initialdir': dossier} if dossier else {}
    chemin = filedialog.asksaveasfilename(parent=parent, title='Enregistrer en PDF',
        initialfile=nom, defaultextension='.pdf', filetypes=[('PDF', '*.pdf')], **options)
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
    """Comparaison centrée sur le total des taxes ; le détail complet reste accessible."""
    from comparaison_prediction import synthese_taxes
    from pathlib import Path
    fen = tk.Toplevel(parent)
    fen.title('Comparer le XML généré avec un fichier fourni')
    fen.geometry('1240x860')
    fen.transient(parent.winfo_toplevel())
    cadre = ttk.Frame(fen, padding=16)
    cadre.pack(fill='both', expand=True)
    theme.entete_page(cadre, 'Comparaison du total des taxes',
        'Écart = fichier comparé − XML généré. Un écart ne prouve ni une erreur de calcul ni une acceptation douanière.')
    plaque = f" · plaque {rapport.get('plaque') or '—'}" if rapport.get('plaque') or rapport.get('plaque_fournie') else ''
    ttk.Label(cadre, text=f"XML généré : {rapport.get('source', '—')}{plaque}\n"
        f"Fichier comparé : {Path(rapport['fichier']).name}"
        + (f" · plaque {rapport.get('plaque_fournie') or '—'}" if plaque else ''),
        style='Doux.TLabel', wraplength=1180).pack(anchor='w', pady=(4, 10))

    # 1. Les trois chiffres qui comptent.
    synthese = synthese_taxes(rapport)
    cartes = ttk.Frame(cadre)
    cartes.pack(fill='x')
    taux = lambda cle: f"taux {nombre(rapport.get(cle), 2)} CDF par {rapport.get('devise_prevue') or 'unité'}"
    ecart, pct = synthese['ecart'], synthese['pourcentage']
    fleche = '' if not ecart else ('▲ ' if ecart > 0 else '▼ ')
    for k, (libelle, valeur, detail, style) in enumerate((
            ('Total taxes estimé · XML généré', nombre(synthese['estime']), taux('taux_genere'), 'Valeur.TLabel'),
            ('Total taxes · fichier comparé', nombre(synthese['compare']), taux('taux_fourni'), 'Valeur.TLabel'),
            ('Différence (comparé − estimé)', f"{fleche}{nombre(ecart)} CDF" if ecart is not None else '—',
             f"{nombre(pct, 2)} %" if pct is not None else '', 'ValeurAccent.TLabel'))):
        cartes.columnconfigure(k, weight=1, uniform='cartes')
        carte = theme.Carte(cartes, libelle, detail=True, style_valeur=style)
        carte.grid(row=0, column=k, sticky='nsew', padx=(0 if k == 0 else 8, 0))
        carte.definir(valeur, detail)

    # 2. L'explication en phrases simples.
    message = theme.Message(cadre)
    message.pack(fill='x', pady=10)
    message.afficher('ok' if not ecart else 'alerte', 'Ce qu’il faut retenir', ['•  ' + p for p in synthese['phrases']])

    # 3. Répartition et taxes, article par article : « généré → comparé » quand les valeurs diffèrent.
    ttk.Label(cadre, text='Répartition et taxes par article', style='Section.TLabel').pack(anchor='w')
    zone, table = theme.tableau(cadre, [
        ('article', 'Article', 170, 'w'), ('poids', 'Poids kg', 140, 'e'), ('fob', 'FOB USD', 160, 'e'),
        ('colis', 'Colis', 100, 'e'), ('estime', 'Taxes estimées', 150, 'e'), ('compare', 'Taxes comparées', 150, 'e'),
        ('ecart', 'Écart taxes', 130, 'e'), ('pct', 'Écart %', 80, 'e')], 12)
    zone.pack(fill='both', expand=True, pady=(4, 0))
    for article, mesures in repartition(rapport):
        def valeur(cle, decimales=0):
            l = mesures.get(cle)
            if not l:
                return '—'
            if l['prevu'] == l['fourni']:
                return nombre(l['prevu'], decimales)
            return f"{nombre(l['prevu'], decimales)} → {nombre(l['fourni'], decimales)}"
        taxes = mesures.get('taxes') or {}
        table.insert('', 'end', tags=('total',) if article.startswith(('Taxes', 'TOTAL')) else (), values=(
            article, valeur('poids'), valeur('fob', 2), valeur('colis'), nombre(taxes.get('prevu')),
            nombre(taxes.get('fourni')), nombre(taxes.get('ecart')), nombre(taxes.get('pourcentage'), 2)))
    ttk.Label(cadre, text='« a → b » : valeur du XML généré → valeur du fichier comparé.',
              style='Doux.TLabel').pack(anchor='w')

    boutons = ttk.Frame(cadre)
    boutons.pack(fill='x', pady=8)
    theme.bouton(boutons, 'Fermer', fen.destroy).pack(side='right')
    theme.bouton(boutons, 'Détails des taxes…', lambda: afficher_taxes(fen, rapport),
        state='normal' if rapport.get('taxes_detail') else 'disabled').pack(side='right', padx=8)
    utilisateur = getattr(parent.winfo_toplevel(), 'utilisateur', '')
    importateur = rapport.get('importateur', '')
    nom_pdf = f"Comparaison {Path(rapport['fichier']).stem}.pdf"
    theme.bouton(boutons, 'Enregistrer en PDF…', lambda: enregistrer_pdf(fen, nom_pdf,
        lambda chemin: export_pdf.pdf_comparaison(rapport, chemin, utilisateur),
        dossier_pdf(parent, importateur))).pack(side='right')
    theme.bouton(boutons, 'Tout le détail (poids, FOB, colis, CIF)…',
                 lambda: afficher_detail_complet(fen, rapport)).pack(side='left')
    return fen


def repartition(rapport):
    """Lignes (libellé, {mesure: ligne}) : articles, puis taxes des articles, globales et total en dernier."""
    articles, totaux = {}, []
    for l in rapport['lignes']:
        if l['position'] != 'Total global':
            articles.setdefault((l['position'], l['code']), {})[l['metrique']] = l
    sortie = [(f"Art. {p} · {c}", m) for (p, c), m in sorted(articles.items(), key=lambda t: str(t[0][0]).zfill(4))]
    for metrique, libelle in (('taxes_articles', 'Taxes des articles'), ('taxes_globales', 'Taxes globales'),
                              ('taxes', 'TOTAL DES TAXES')):
        l = next((l for l in rapport['lignes'] if l['position'] == 'Total global' and l['metrique'] == metrique), None)
        if l:
            mesures = {'taxes': l}
            if metrique == 'taxes':
                mesures.update({m: x for x in rapport['lignes'] if x['position'] == 'Total global'
                                for m in ('poids', 'fob', 'colis') if x['metrique'] == m})
            totaux.append((libelle, mesures))
    return sortie + totaux


def afficher_detail_complet(parent, rapport):
    """Ancien tableau complet : toutes les mesures, article par article, avec le contexte."""
    fen = tk.Toplevel(parent)
    fen.title('Comparaison : tout le détail')
    fen.geometry('1240x720')
    fen.transient(parent.winfo_toplevel())
    cadre = ttk.Frame(fen, padding=16)
    cadre.pack(fill='both', expand=True)
    theme.entete_page(cadre, 'Tout le détail', 'Écart = fichier comparé − XML généré.')
    zone, table = theme.tableau(cadre, [
        ('article', 'Position · Code', 160, 'w'), ('metrique', 'Mesure', 150, 'w'),
        ('prevu', 'XML généré', 150, 'e'), ('fourni', 'Fichier comparé', 150, 'e'),
        ('ecart', 'Écart', 130, 'e'), ('pourcentage', 'Écart %', 100, 'e'), ('etat', 'Observation', 290, 'w')], 20)
    zone.pack(fill='both', expand=True)
    for ligne in rapport['lignes']:
        decimales = {'ratio': 4, 'poids': 3, 'colis': 0}.get(ligne['metrique'], 2)
        table.insert('', 'end', tags=('total',) if ligne['position'] == 'Total global' else (), values=(
            f"{ligne['position']} · {ligne['code']}" if ligne['code'] else ligne['position'], ligne['libelle'],
            nombre(ligne['prevu'], decimales), nombre(ligne['fourni'], decimales),
            nombre(ligne['ecart'], decimales), nombre(ligne['pourcentage'], 2), ligne['etat']))
    details = rapport['contexte'] + rapport['avertissements']
    if details:
        ttk.Label(cadre, text='Contexte et données', style='Section.TLabel').pack(anchor='w', pady=(8, 2))
        texte = tk.Text(cadre, height=5, wrap='word', font=(theme.POLICE, 11))
        texte.pack(fill='x')
        texte.insert('1.0', '\n'.join(details))
        texte.configure(state='disabled')
    theme.bouton(cadre, 'Fermer', fen.destroy).pack(anchor='e', pady=8)
    return fen


def afficher_taxes(parent, rapport, explication=''):
    """Taxes estimées (XML généré) et comparées (fichier fourni), ligne par ligne."""
    fen = tk.Toplevel(parent)
    fen.title('Détails des taxes : estimé / comparé')
    fen.geometry('1300x700')
    fen.transient(parent.winfo_toplevel())
    cadre = ttk.Frame(fen, padding=16)
    cadre.pack(fill='both', expand=True)
    theme.entete_page(cadre, 'Détails des taxes',
        'Estimé = XML généré, comparé = fichier fourni. Écart = comparé − estimé. '
        'Les lignes « Total » additionnent les articles par code de taxe ; « Globale » = taxes globales du XML.')
    zone, table = theme.tableau(cadre, [
        ('article', 'Art. · Code', 120, 'w'), ('taxe', 'Taxe', 70, 'w'),
        ('base_e', 'Base estimée', 125, 'e'), ('base_c', 'Base comparée', 125, 'e'),
        ('taux_e', 'Taux estimé', 85, 'e'), ('taux_c', 'Taux comparé', 85, 'e'),
        ('estime', 'Montant estimé', 125, 'e'), ('compare', 'Montant comparé', 125, 'e'),
        ('ecart', 'Écart', 110, 'e'), ('pct', 'Écart %', 75, 'e'), ('etat', 'Observation', 180, 'w')], 22)
    if explication:
        ttk.Label(cadre, text=explication, style='Section.TLabel', wraplength=1200).pack(anchor='w', pady=(0, 6))
    zone.pack(fill='both', expand=True)
    for l in rapport['taxes_detail']:
        table.insert('', 'end', tags=('total',) if l['position'] in ('Total', 'Globale') else (), values=(
            f"{l['position']} · {l['article']}" if l['article'] else l['position'], l['taxe'],
            nombre(l['base_estimee'], 2), nombre(l['base_comparee'], 2),
            nombre(l['taux_estime'], 3), nombre(l['taux_compare'], 3),
            nombre(l['estime'], 2), nombre(l['compare'], 2),
            nombre(l['ecart'], 2), nombre(l['pourcentage'], 2), l['etat']))
    theme.bouton(cadre, 'Fermer', fen.destroy).pack(anchor='e', pady=8)
    return fen
