"""Synthèse affichée en tête du traitement d'une licence : chiffres clés et articles par part."""
from decimal import Decimal, InvalidOperation
import tkinter as tk
from tkinter import ttk

from asydec.declarations import informations_declaration
from asydec.formats import nombre
from asydec.ui import theme


def libelle_unite(unite):
    texte = str(unite or '').casefold()
    if 'piece' in texte or 'pièce' in texte or 'unite' in texte:
        return 'pièces'
    if 'kilo' in texte or texte == 'kg':
        return 'kg'
    return str(unite or '').strip() or 'unités'


def decimal(valeur):
    try:
        resultat = Decimal(str(valeur).replace(' ', '').replace(',', '.'))
    except InvalidOperation:
        return None
    return resultat if resultat.is_finite() else None


def quantite(valeur):
    if valeur is None:
        return '—'
    return nombre(valeur, 0 if valeur == valeur.to_integral_value() else 3)


def date_texte(valeur):
    try:
        return informations_declaration.lire_date(valeur).strftime('%d/%m/%Y')
    except (ValueError, TypeError):
        return 'Non renseignée'


def quantites_globales(produits):
    """Totaux par unité : {'pièces': Decimal, 'kg': Decimal}."""
    totaux = {}
    for produit in produits:
        q = decimal(produit.get('quantite'))
        if q is not None:
            cle = libelle_unite(produit.get('unite'))
            totaux[cle] = totaux.get(cle, Decimal(0)) + q
    return totaux


def lignes_articles(licence):
    """Une ligne par article : totaux de la licence et division par part."""
    produits = licence.get('produits') or []
    parts = (licence.get('repartition') or {}).get('parts') or []
    from asydec.declarations.repartition_licence import valeurs_articles
    # Valeur totale déjà corrigée de l'écart d'arrondi des quantités : la somme est le FOB de la licence.
    ajustees = valeurs_articles(produits, licence.get('montant_fob')) or []
    lignes = []
    for i, produit in enumerate(produits):
        q, pu = decimal(produit.get('quantite')), decimal(produit.get('prix_unitaire'))
        valeur = ajustees[i] if i < len(ajustees) else (q * pu if q is not None and pu is not None else None)
        par_part = [p['articles'][i] for p in parts if len(p.get('articles') or []) > i]
        quantites = sorted({decimal(a['quantite']) for a in par_part}, reverse=True)
        valeurs = sorted({decimal(a['valeur']) for a in par_part}, reverse=True)
        lignes.append(dict(
            numero=i + 1,
            designation=' '.join(str(produit.get('designation', '')).split()),
            unite=libelle_unite(produit.get('unite')),
            quantite=quantite(q),
            prix=nombre(pu, 2) if pu is not None else '—',
            valeur=nombre(valeur, 2) if valeur is not None else '—',
            quantite_part=' / '.join(quantite(v) for v in quantites) if quantites else '—',
            valeur_part=' / '.join(nombre(v, 2) for v in valeurs) if valeurs else '—'))
    return lignes


def construire(parent, licence):
    """Bloc complet de synthèse, à placer au-dessus des étapes."""
    cadre = ttk.Frame(parent)
    produits = licence.get('produits') or []
    repartition = licence.get('repartition') or {}
    parts = repartition.get('parts') or []

    identite = ttk.Frame(cadre, padding=14, relief='solid', borderwidth=1)
    identite.pack(fill='x', pady=(0, 12))
    ttk.Label(identite, text=licence.get('soussigne', {}).get('nom') or 'Soussigné non renseigné',
              style='Section.TLabel').grid(row=0, column=0, columnspan=4, sticky='w', pady=(0, 10))
    details = (('Numéro licence', licence.get('numero_validation', '')),
               ('Numéro DEC', licence.get('numero_dec', '')),
               ('Validation licence', date_texte(licence.get('date_validation'))),
               ('Date du BL', date_texte(licence.get('date_bl'))),
               ('Fournisseur', licence.get('fournisseur', {}).get('nom') or 'Non renseigné'))
    for i, (titre, valeur) in enumerate(details):
        identite.columnconfigure(i, weight=1, uniform='identite')
        ttk.Label(identite, text=titre, style='Doux.TLabel').grid(row=1, column=i, sticky='w', padx=(0, 12))
        ttk.Label(identite, text=valeur or '—', style='Total.TLabel', wraplength=260).grid(row=2, column=i, sticky='nw', padx=(0, 12))

    fob = decimal(licence.get('montant_fob'))
    globales = quantites_globales(produits)
    textes_quantites = [f'{quantite(v)} {u}' for u, v in sorted(globales.items(), key=lambda e: -e[1])]
    fobs_parts = sorted({decimal(p['fob']) for p in parts}, reverse=True)
    poids_parts = sorted({p['poids_kg'] for p in parts if p.get('poids_kg')})
    texte_poids = (f'{nombre(poids_parts[0])} kg' if len(poids_parts) == 1
                   else f'{nombre(poids_parts[0])} à {nombre(poids_parts[-1])} kg' if poids_parts else '—')
    indicateurs = (
        ('FOB total (USD)', nombre(fob, 2) if fob is not None else '—', f'{len(produits)} article(s)'),
        ('Quantité globale', textes_quantites[0] if textes_quantites else '—', ' · '.join(textes_quantites[1:])),
        ('Nombre de parts', str(len(parts)) if parts else '—',
         ('Choisi' if repartition.get('nombre_parts_choisi') else 'Automatique') + ' · '
         + ('plafond 120 000 USD par part' if repartition.get('plafond_actif', True) else 'sans plafond')),
        ('FOB par part (USD)', ' / '.join(nombre(v, 2) for v in fobs_parts) if fobs_parts else '—', 'Parts identiques'),
        ('Poids par part', texte_poids, 'Entre 22 000 et 24 000 kg'),
        ('Poids global', f"{nombre(repartition.get('poids_total_kg'))} kg" if parts else '—',
         (f'{len(parts)} × {texte_poids}' if len(poids_parts) == 1 else f'{len(parts)} parts') if parts else 'Répartition à faire'),
    )
    grille = ttk.Frame(cadre)
    grille.pack(fill='x', pady=(0, 12))
    for i, (libelle, valeur, detail) in enumerate(indicateurs):
        grille.columnconfigure(i % 3, weight=1, uniform='indicateur')
        carte = theme.Carte(grille, libelle, detail=True)
        carte.grid(row=i // 3, column=i % 3, sticky='nsew', padx=(0 if i % 3 == 0 else 6, 0), pady=(0, 6))
        carte.definir(valeur, detail)

    if parts:
        ttk.Label(cadre, text='Parts de la licence', style='Section.TLabel').pack(anchor='w', pady=(6, 6))
        colonnes_parts = [('numero', 'Part', 50, 'center'), ('fob', 'FOB (USD)', 120, 'e'), ('poids', 'Poids (kg)', 100, 'e'),
                          ('plaque', 'Plaques', 190, 'w'), ('conteneur', 'Conteneur', 140, 'w'), ('scelle', 'Scellé', 110, 'w')]
        zone_parts, table_parts = theme.tableau(cadre, colonnes_parts, hauteur=min(len(parts), 8) + 1)
        zone_parts.pack(fill='x', pady=(0, 12))
        table_parts.tag_configure('pair', background='#F7F9FC')
        for i, part in enumerate(parts):
            table_parts.insert('', 'end', values=(part['numero'], nombre(decimal(part['fob']), 2), nombre(part['poids_kg']),
                                                  part.get('plaque', ''), part.get('conteneur', ''), part.get('scelle', '')),
                               tags=('pair',) if i % 2 == 0 else ())
        table_parts.insert('', 'end', values=('Total', nombre(fob, 2) if fob is not None else '—',
                                              nombre(repartition.get('poids_total_kg')), '', '', ''), tags=('total',))

    ttk.Label(cadre, text='Articles de la licence' + (f' · division par part ({len(parts)} parts)' if parts else ''),
              style='Section.TLabel').pack(anchor='w', pady=(6, 6))
    colonnes = [('numero', 'N°', 40, 'center'), ('designation', 'Désignation', 280, 'w'), ('unite', 'Unité', 70, 'w'),
                ('quantite', 'Qté totale', 100, 'e'), ('quantite_part', 'Qté par part', 110, 'e'),
                ('prix', 'Prix unitaire', 100, 'e'), ('valeur', 'Valeur totale', 120, 'e'),
                ('valeur_part', 'Valeur par part', 130, 'e')]
    lignes = lignes_articles(licence)
    zone, table = theme.tableau(cadre, colonnes, hauteur=min(max(len(lignes), 3), 12) + 1)
    zone.pack(fill='x')
    table.tag_configure('pair', background='#F7F9FC')
    for i, ligne in enumerate(lignes):
        table.insert('', 'end', values=[ligne[c[0]] for c in colonnes], tags=('pair',) if i % 2 == 0 else ())
    if lignes:
        total_parts = ' / '.join(nombre(v, 2) for v in fobs_parts) if fobs_parts else '—'
        table.insert('', 'end', values=('', 'Total', '', ' · '.join(textes_quantites), '', '',
                                        nombre(fob, 2) if fob is not None else '—', total_parts), tags=('total',))
    if parts and not parts[0].get('articles'):
        ttk.Label(cadre, text='Les quantités par part ne sont pas calculées : la somme quantité × prix des articles '
                  'ne correspond pas au FOB de la licence.', style='Alerte.TLabel', wraplength=900).pack(anchor='w', pady=(6, 0))
    elif not parts:
        ttk.Label(cadre, text='Validez la répartition pour diviser les quantités entre les parts.',
                  style='Doux.TLabel').pack(anchor='w', pady=(6, 0))
    return cadre
