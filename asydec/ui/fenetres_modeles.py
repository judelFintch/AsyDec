"""Fenêtres secondaires de « Modèles générés » : fiche, anomalies, comparaisons enregistrées."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

from asydec.calcul import anomalies
from asydec.declarations import modeles_generes as service
from asydec.formats import date_locale, nombre
from asydec.references.import_references import extraire
from asydec.ui import comparaison as fenetre_comparaison
from asydec.ui import theme


def _fenetre(parent, titre, taille, entete, sous_titre):
    """Fenêtre standard : titre, taille, en-tête de page ; renvoie (fenêtre, cadre)."""
    fen = tk.Toplevel(parent)
    fen.title(titre)
    fen.geometry(taille)
    cadre = ttk.Frame(fen, padding=16)
    cadre.pack(fill='both', expand=True)
    theme.entete_page(cadre, entete, sous_titre)
    return fen, cadre


def texte_comparaisons(d):
    dates = [date_locale(e['date_utc']) for e in d['evenements'] if e['action'] == service.COMPARAISON]
    return f'Comparé {len(dates)} fois, dernière le {dates[-1]}.' if dates else 'Jamais comparé avec un XML.'


# -----------------------------------------------------------------------------
# Fiche d'un modèle
# -----------------------------------------------------------------------------
def fiche(page, d):
    identifiant = d['id']
    fen, cadre = _fenetre(page, f'Modèle conservé n° {identifiant}', '1020x650',
        f"Modèle n° {identifiant} · {service.STATUTS[d['statut']]}",
        f"{d['importateur']} · plaque {d['plaque'] or '—'} · créé le {date_locale(d['cree_utc'])} par {d['auteur']}. "
        f"{texte_comparaisons(d)} Validation locale uniquement.")
    _etat_fichier_xml(cadre, d)
    _tableau_articles(cadre, d)
    _historique(cadre, d)
    _boutons_fiche(page, cadre, fen, d)
    return fen


def _etat_fichier_xml(cadre, d):
    chemin, etat = service.fichier_xml_genere(d)
    ttk.Label(cadre, text=f"Fichier XML généré : {Path(chemin).name if chemin else '—'}",
              style='Section.TLabel').pack(anchor='w', pady=(6, 0))
    alerte = {'foreground': theme.ERREUR} if 'MODIFIÉ' in etat or 'introuvable' in etat else {}
    ttk.Label(cadre, text=f'{chemin} · {etat}' if chemin else etat, wraplength=960, **alerte).pack(anchor='w')


def _tableau_articles(cadre, d):
    zone, table = theme.tableau(cadre, [
        ('art', 'Art. / Position tarifaire', 180, 'w'), ('poids', 'Poids kg', 100, 'e'), ('fob', 'FOB USD', 120, 'e'),
        ('colis', 'Colis', 80, 'e'), ('ratio', 'Ratio FOB/kg', 130, 'e'), ('cif', 'CIF CDF', 140, 'e'),
        ('taxes', 'Taxes CDF', 140, 'e')], 9)
    zone.pack(fill='x', pady=8)
    r = d['resultat']
    sources = [a for a in extraire(d['base_xml'])['articles'] if a['fob'] is not None and float(a['fob']) != 0]
    for source, a, colis in zip(sources, r['resume']['articles'], r['colis']):
        ratio = nombre(a['fob'] / a['poids'], 4) if a['poids'] > 0 else '—'
        table.insert('', 'end', values=(f"{source['position']} · {source['code']}", nombre(a['poids']), nombre(a['fob'], 2), colis,
                                        ratio, nombre(a['cif']), nombre(a['taxes'])))


def _historique(cadre, d):
    texte = tk.Text(cadre, height=9, wrap='word', font=(theme.POLICE, 11))
    texte.pack(fill='both', expand=True)
    texte.insert('1.0', '\n'.join(f"{date_locale(e['date_utc'])} · {e['auteur']} · {service.resume_evenement(e)}"
                                  for e in d['evenements']))
    texte.configure(state='disabled')


def _boutons_fiche(page, cadre, fen, d):
    identifiant = d['id']
    compare = any(e['action'] == service.COMPARAISON for e in d['evenements'])
    boutons = ttk.Frame(cadre)
    boutons.pack(fill='x', pady=8)
    actions = [('Fermer', fen.destroy, True),
               ('Détails des taxes…', lambda: page.details_taxes(d, fen), True),
               ('Comparaisons enregistrées…', lambda: page.voir_comparaisons(d, fen), compare),
               ('Corriger le dossier…', lambda: page.corriger_dossier(identifiant, fen), True),
               ('Reprendre pour modifier', lambda: page.reprendre(identifiant, fen), True)]
    if d['statut'] == 'valide':
        actions += [('Télécharger le XML…', lambda: page.telecharger_xml(identifiant, fen), True),
                    ('Plaque…', lambda: page.saisir_plaque(identifiant, fen), True),
                    ('Imprimer en PDF…', lambda: page.imprimer(identifiant, fen), True)]
    for k, (texte, commande, actif) in enumerate(actions):
        theme.bouton(boutons, texte, commande, state='normal' if actif else 'disabled').pack(
            side='right', padx=(0 if k == 0 else 8, 0))


# -----------------------------------------------------------------------------
# Anomalies
# -----------------------------------------------------------------------------
def anomalies_modele(parent, identifiant, alertes):
    """Alertes d'un modèle, de la plus grave à la simple information."""
    fen, cadre = _fenetre(parent, f'Anomalies · modèle n° {identifiant}', '1050x460',
        f'Modèle n° {identifiant} · {anomalies.LIBELLES[anomalies.niveau(alertes)]}',
        'Comparaison avec les dossiers connus de la bibliothèque des références et avec vos autres modèles. '
        'Indicatif : aucune référence ne prouve un rejet SYDONIA ; vérifiez chaque point.')
    zone, table = theme.tableau(cadre, [('niveau', 'Niveau', 120, 'w'), ('article', 'Article', 130, 'w'),
                                        ('message', 'Explication', 760, 'w')], 12)
    zone.pack(fill='both', expand=True)
    table.tag_configure('eleve', foreground=theme.ERREUR)
    table.tag_configure('moyen', foreground=theme.ALERTE)
    for a in alertes:
        table.insert('', 'end', tags=(a['niveau'],),
                     values=(anomalies.LIBELLES[a['niveau']], a['article'] or '—', a['message']))
    if not alertes:
        table.insert('', 'end', values=('—', '—', 'Aucun signal par rapport aux dossiers connus.'))
    theme.bouton(cadre, 'Fermer', fen.destroy).pack(anchor='e', pady=8)
    return fen


# -----------------------------------------------------------------------------
# Comparaisons enregistrées
# -----------------------------------------------------------------------------
def comparaisons_enregistrees(parent, d):
    """Liste des comparaisons conservées ; double-clic : la fenêtre de comparaison telle qu'enregistrée."""
    liste = service.comparaisons(d)
    fen, cadre = _fenetre(parent, f"Comparaisons enregistrées · modèle n° {d['id']}", '1100x420',
        f"Comparaisons du modèle n° {d['id']}",
        'Double-cliquez une ligne pour revoir la comparaison complète : répartition et total des taxes.')
    zone, table = theme.tableau(cadre, [
        ('date', 'Date', 150, 'w'), ('fichier', 'Fichier comparé', 360, 'w'),
        ('estime', 'Total taxes estimé', 150, 'e'), ('compare', 'Total taxes comparé', 150, 'e'),
        ('ecart', 'Écart CDF', 130, 'e'), ('auteur', 'Par', 90, 'w')], 10)
    zone.pack(fill='both', expand=True)
    for k, c in enumerate(liste):
        table.insert('', 'end', iid=str(k), values=(
            date_locale(c['date_utc']), Path(c['fichier']).name, nombre(c['total_estime']),
            nombre(c['total_compare']), nombre(c['ecart_total']), c['auteur']))

    def revoir(_evenement=None):
        choix = table.selection()
        if choix:
            _rouvrir(fen, liste[int(choix[0])])

    table.bind('<Double-1>', revoir)
    boutons = ttk.Frame(cadre)
    boutons.pack(fill='x', pady=8)
    theme.bouton(boutons, 'Fermer', fen.destroy).pack(side='right')
    theme.bouton(boutons, 'Revoir la comparaison', revoir, principal=True).pack(side='right', padx=8)
    if liste:
        table.selection_set('0')
    return fen


def _rouvrir(parent, comparaison):
    if not comparaison['rapport']:
        messagebox.showinfo('Comparaison ancienne', 'Cette comparaison date d’avant l’enregistrement complet : '
                            'seuls ses totaux sont conservés.', parent=parent)
        return
    rapport = dict(comparaison['rapport'])
    rapport['source'] = f"{rapport.get('source', 'XML généré')} · comparaison du {date_locale(comparaison['date_utc'])}"
    fenetre_comparaison.afficher(parent, rapport)
