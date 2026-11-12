"""Fiche imprimable d'un dossier : informations de la licence et toutes ses répartitions.

PDF A4 mis en page par PyMuPDF (HTML + CSS), numéroté « page x / n ». Document de travail : il ne
modifie ni la licence, ni les répartitions, ni les fichiers générés.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import escape
from io import BytesIO

from asydec.declarations import informations_declaration
from asydec.formats import nombre

BLEU = '#183650'
DOUX = '#60758A'

CSS = f'''
* {{ font-family: sans-serif; }}
body {{ font-size: 8.5pt; color: #111827; }}
h1 {{ font-size: 17pt; color: {BLEU}; margin: 0 0 2pt 0; }}
h2 {{ font-size: 10pt; color: {BLEU}; margin: 9pt 0 4pt 0; padding-bottom: 2pt; border-bottom: 1pt solid {BLEU}; }}
h3 {{ font-size: 9pt; color: {BLEU}; margin: 8pt 0 3pt 0; }}
p {{ margin: 0; }}
.sous {{ color: {DOUX}; font-size: 9pt; margin-bottom: 4pt; }}
.chiffres td {{ padding: 4pt 6pt; background-color: #EDF2F7; border: 0.5pt solid #FFFFFF; }}
.libelle {{ color: {DOUX}; font-size: 7pt; }}
.valeur {{ font-size: 11pt; font-weight: bold; color: {BLEU}; }}
table {{ width: 100%; border-collapse: collapse; }}
.grille td, .grille th {{ border: 0.5pt solid #CAD5DF; padding: 2.5pt 3pt; font-size: 7.5pt; }}
.grille th {{ background-color: {BLEU}; color: #FFFFFF; font-weight: bold; text-align: center; }}
.grille tr.total td {{ background-color: #EDF2F7; font-weight: bold; }}
.fiche td {{ padding: 2pt 4pt; vertical-align: top; font-size: 8pt; }}
.fiche td.cle {{ color: {DOUX}; }}
.n {{ text-align: right; }}
.c {{ text-align: center; }}
.vide {{ color: #9CA3AF; }}
'''


def _decimal(valeur):
    try:
        resultat = Decimal(str(valeur).replace(' ', '').replace(',', '.'))
    except (InvalidOperation, TypeError):
        return None
    return resultat if resultat.is_finite() else None


def _montant(valeur):
    d = _decimal(valeur)
    return nombre(d, 2) if d is not None else '—'


def _pu(valeur):
    from asydec.declarations.quantites_entieres import pu_texte
    d = _decimal(valeur)
    return pu_texte(d, ' ').replace('.', ',') if d is not None else '—'


def _quantite(valeur):
    d = _decimal(valeur)
    if d is None:
        return '—'
    return nombre(d, 0 if d == d.to_integral_value() else 3)


def _date(valeur):
    if not valeur:
        return ''
    try:
        return informations_declaration.lire_date(valeur).strftime('%d/%m/%Y')
    except (ValueError, TypeError):
        return str(valeur)


def _t(valeur):
    texte = ' '.join(str(valeur or '').split())
    return escape(texte) if texte else '<span class="vide">—</span>'


def _multiligne(valeur):
    lignes = [escape(' '.join(l.split())) for l in str(valeur or '').splitlines() if l.strip()]
    return '<br/>'.join(lignes) if lignes else '<span class="vide">—</span>'


def _unite(unite):
    texte = str(unite or '').casefold()
    if 'piece' in texte or 'pièce' in texte or 'unite' in texte:
        return 'pcs'
    if 'kilo' in texte or texte == 'kg':
        return 'kg'
    return escape(str(unite or '').strip())


def _fiche(lignes, largeur_cle=88):
    corps = ''.join(f'<tr><td class="cle" style="width:{largeur_cle}pt">{escape(cle)}</td><td>{valeur}</td></tr>'
                    for cle, valeur in lignes)
    return f'<table class="fiche">{corps}</table>'


class Tableau:
    """Tableau découpable entre les pages : chaque morceau répète l'en-tête."""

    def __init__(self, entetes, lignes, total=None):
        self.tete = '<tr>' + ''.join(f'<th>{escape(t)}</th>' for t, _ in entetes) + '</tr>'
        self.lignes = ['<tr>' + ''.join(f'<td class="{c}">{v}</td>' for v, (_, c) in zip(l, entetes)) + '</tr>'
                       for l in lignes]
        if total:
            self.lignes.append('<tr class="total">' + ''.join(f'<td class="{c}">{v}</td>'
                                                              for v, (_, c) in zip(total, entetes)) + '</tr>')

    def html(self, debut=0, fin=None):
        return f'<table class="grille">{self.tete}{"".join(self.lignes[debut:fin])}</table>'


def _deux_colonnes(lignes):
    moitie = (len(lignes) + 1) // 2
    return ('<table><tr><td style="width:50%; vertical-align:top; padding-right:8pt">' + _fiche(lignes[:moitie])
            + '</td><td style="width:50%; vertical-align:top">' + _fiche(lignes[moitie:]) + '</td></tr></table>')


def _tableau(entetes, lignes, total=None):
    return Tableau(entetes, lignes, total)


def _infos_part(part, licence):
    infos = dict(licence.get('informations_declaration') or {})
    infos.update({k: v for k, v in (part.get('informations_declaration') or {}).items() if v})
    return infos


def blocs(licence, maintenant=None):
    """Suite de fragments HTML et de Tableau, dans l'ordre de la fiche."""
    maintenant = maintenant or datetime.now()
    repartition = licence.get('repartition') or {}
    parts = repartition.get('parts') or []
    infos = licence.get('informations_declaration') or {}
    soussigne = licence.get('soussigne') or {}
    fournisseur = licence.get('fournisseur') or {}
    morceaux = []

    morceaux.append(f'<h1>Dossier {escape(str(licence.get("numero_validation", "")))}</h1>')
    morceaux.append(f'<p class="sous">{_t(soussigne.get("nom"))} · DEC {_t(licence.get("numero_dec"))} · '
                    f'imprimé le {maintenant:%d/%m/%Y à %H:%M}</p>')
    chiffres = [('FOB licence', _montant(licence.get('montant_fob')) + ' USD'),
                ('Répartitions', str(len(parts)) if parts else '—'),
                ('Poids total', (nombre(repartition['poids_total_kg']) + ' kg') if repartition.get('poids_total_kg') else '—'),
                ('Validation', _date(licence.get('date_validation')) or '—'),
                ('Date du BL', _date(licence.get('date_bl')) or '—')]
    morceaux.append('<table class="chiffres"><tr>' + ''.join(
        f'<td><p class="libelle">{escape(l)}</p><p class="valeur">{escape(v)}</p></td>' for l, v in chiffres)
        + '</tr></table>')

    facture = licence.get('numero_facture')
    dossier = [
        ('N° de validation', _t(licence.get('numero_validation'))),
        ('N° DEC', _t(licence.get('numero_dec'))),
        ('Montant FOB', _t(_montant(licence.get('montant_fob')) + ' USD')),
        ('Date de validation', _t(_date(licence.get('date_validation')))),
        ('Date du BL', _t(_date(licence.get('date_bl')))),
        ('Facture de la licence', _t(f"{facture} du {licence.get('date_facture', '')}" if facture else '')),
    ]
    if infos:
        champs = [(titre.replace(' · automatique', '').replace(' / quittance', ''), cle)
                  for cle, titre, _ in informations_declaration.CHAMPS]
        declaration = _fiche([(t, _t(infos.get(c))) for t, c in champs if infos.get(c)]
                             + ([('Observations', _multiligne(infos['observations']))] if infos.get('observations') else []))
    else:
        declaration = '<p class="vide">Informations de déclaration non encore saisies (étape 3).</p>'
    colonne = 'vertical-align:top; padding-right:10pt'
    morceaux.append(
        f'<table><tr><td style="width:25%; {colonne}"><h2>Dossier</h2>' + _fiche(dossier, 78) + '</td>'
        f'<td style="width:25%; {colonne}"><h2>Déclaration (1re part)</h2>' + declaration + '</td>'
        f'<td style="width:25%; {colonne}"><h2>Importateur</h2>' + _fiche([
            ('Nom', _t(soussigne.get('nom'))), ('Adresse', _multiligne(soussigne.get('adresse'))),
            ('Téléphone', _t(soussigne.get('telephone'))), ('E-mail', _t(soussigne.get('email'))),
            ('Identifiants', _t(soussigne.get('identifiants')))], 52) + '</td>'
        '<td style="width:25%; vertical-align:top"><h2>Fournisseur</h2>' + _fiche([
            ('Nom', _t(fournisseur.get('nom'))), ('Adresse', _multiligne(fournisseur.get('adresse'))),
            ('Téléphone', _t(fournisseur.get('telephone'))), ('E-mail', _t(fournisseur.get('email')))], 52)
        + '</td></tr></table>')

    morceaux.append('<h2>Articles de la licence</h2>')
    produits = licence.get('produits') or []
    lignes, total = [], Decimal(0)
    for i, p in enumerate(produits, 1):
        q, pu = _decimal(p.get('quantite')), _decimal(p.get('prix_unitaire'))
        valeur = (q * pu).quantize(Decimal('0.01')) if q is not None and pu is not None else None
        total += valeur or 0
        lignes.append([str(i), _t(p.get('tarif_douanier')), _t(p.get('designation')), _t(p.get('pays_origine')),
                       _quantite(q) + ' ' + _unite(p.get('unite')), _pu(pu), _montant(valeur)])
    morceaux.append(_tableau([('N°', 'c'), ('Code SH', 'c'), ('Désignation', ''), ('Origine', 'c'),
                              ('Quantité', 'n'), ('PU (USD)', 'n'), ('Valeur (USD)', 'n')], lignes,
                             ['', '', 'Total', '', '', '', _montant(total)] if produits else None)
                     if produits else '<p class="vide">Aucun article.</p>')

    morceaux.append('<h2>Répartitions</h2>')
    if not parts:
        morceaux.append('<p class="vide">Répartition non encore faite (étape 2).</p>')
    else:
        options = [f"{len(parts)} part(s)"]
        if repartition.get('poids_par_part_kg'):
            options.append(f"{nombre(repartition['poids_par_part_kg'])} kg par part")
        options.append('plafond de ' + _montant(repartition.get('plafond_usd')) + ' USD' if repartition.get('plafond_actif', True)
                       and repartition.get('plafond_usd') else 'sans plafond')
        morceaux.append(f'<p class="sous">{escape(" · ".join(options))}</p>')
        cles_dates = (('date_enregistrement', 'Enreg.'), ('date_liquidation', 'Liq.'),
                      ('date_quittance', 'Quitt.'), ('date_cvi', 'CVI'))
        infos_parts = [_infos_part(part, licence) for part in parts]
        # Dates par part seulement si elles diffèrent de celles de la première part (déjà affichées).
        dates_variables = [(c, t) for c, t in cles_dates
                           if len({str(i.get(c) or '') for i in infos_parts}) > 1]
        plusieurs_articles = len(produits) > 1 or any(len(p.get('articles') or []) > 1 for p in parts)
        lignes = []
        fob, poids, quantites = Decimal(0), Decimal(0), Decimal(0)
        for part, i in zip(parts, infos_parts):
            fob += _decimal(part.get('fob')) or 0
            poids += _decimal(part.get('poids_kg')) or 0
            articles = part.get('articles') or []
            q = sum((_decimal(a.get('quantite')) or 0 for a in articles), Decimal(0))
            quantites += q
            unite = _unite(articles[0].get('unite')) if articles else ''
            lignes.append([str(part.get('numero', '')), _montant(part.get('fob')), _quantite(part.get('poids_kg')),
                           (_quantite(q) + ' ' + unite) if articles else '—',
                           _t(part.get('plaque') or i.get('plaque')), _t(part.get('conteneur')), _t(part.get('scelle')),
                           _t(i.get('numero_e')), _t(i.get('numero_liquidation')), _t(i.get('numero_quittance')),
                           _t(i.get('manifeste'))] + [_t(i.get(c)) for c, _ in dates_variables])
        unites = {_unite(a.get('unite')) for p in parts for a in (p.get('articles') or [])}
        unite_totale = unites.pop() if len(unites) == 1 else ''
        morceaux.append(_tableau([('Part', 'c'), ('FOB (USD)', 'n'), ('Poids (kg)', 'n'), ('Quantité', 'n'),
                                  ('Plaques', 'c'), ('Conteneur', 'c'), ('Scellé', 'c'), ('E', 'c'),
                                  ('Liquidation', 'c'), ('Quittance', 'c'), ('Manifeste', 'c')]
                                 + [(t, 'c') for _, t in dates_variables], lignes,
                                 ['Total', _montant(fob), _quantite(poids), (_quantite(quantites) + ' ' + unite_totale).strip()]
                                 + [''] * (7 + len(dates_variables))))

        if plusieurs_articles:
            morceaux.append('<h2>Détail des articles par part</h2>')
            lignes = []
            for part in parts:
                for a in part.get('articles') or []:
                    lignes.append([str(part.get('numero', '')), _t(a.get('designation')),
                                   _quantite(a.get('quantite')) + ' ' + _unite(a.get('unite')),
                                   _pu(a.get('prix_unitaire')), _montant(a.get('valeur'))])
            morceaux.append(_tableau([('Part', 'c'), ('Désignation', ''), ('Quantité', 'n'), ('PU (USD)', 'n'),
                                      ('Valeur (USD)', 'n')], lignes))
    return morceaux


ECHELLE_MINIMUM = 0.6  # en dessous, le texte devient trop petit : la fiche passe sur plusieurs pages


def _une_page(licence, maintenant, page, zone):
    """Fiche entière sur une seule page, réduite si besoin ; None si elle ne tient pas à l'échelle minimum."""
    import pymupdf
    fragments = [b.html() if isinstance(b, Tableau) else b for b in blocs(licence, maintenant)]
    contenu = '<body>' + ''.join(fragments) + '</body>'
    echelle = 1.0
    while echelle >= ECHELLE_MINIMUM - 1e-9:
        histoire = pymupdf.Story(html=contenu, user_css=CSS)
        cadre = pymupdf.Rect(0, 0, zone.width / echelle, zone.height / echelle)
        suite, _ = histoire.place(cadre)
        if not suite:
            sortie = BytesIO()
            redacteur = pymupdf.DocumentWriter(sortie)
            dispositif = redacteur.begin_page(page)
            histoire.draw(dispositif, pymupdf.Matrix(echelle, echelle).pretranslate(
                zone.x0 / echelle, zone.y0 / echelle))
            redacteur.end_page()
            redacteur.close()
            return sortie.getvalue()
        echelle -= 0.05
    return None


def pdf(licence, maintenant=None):
    """Octets du PDF A4 paysage de la fiche : une seule page si possible, sinon plusieurs pages."""
    import pymupdf
    maintenant = maintenant or datetime.now()
    sortie = BytesIO()
    page = pymupdf.paper_rect('a4-l')
    zone = page + (32, 30, -32, -34)
    unique = _une_page(licence, maintenant, page, zone)
    if unique is not None:
        return _finaliser(unique, licence, page)
    redacteur = pymupdf.DocumentWriter(sortie)
    etat = {'dispositif': None, 'y': zone.y0}

    def nouvelle_page():
        if etat['dispositif'] is not None:
            redacteur.end_page()
        etat['dispositif'] = redacteur.begin_page(page)
        etat['y'] = zone.y0

    def essayer(fragment, dessiner=False):
        """Hauteur occupée si le fragment tient dans la place restante, sinon None."""
        histoire = pymupdf.Story(html='<body>' + fragment + '</body>', user_css=CSS)
        reste = pymupdf.Rect(zone.x0, etat['y'], zone.x1, zone.y1)
        if reste.height <= 1:
            return None
        suite, rempli = histoire.place(reste)
        rempli = pymupdf.Rect(rempli)
        if suite:
            return None
        if dessiner:
            histoire.draw(etat['dispositif'])
            etat['y'] = rempli.y1
        return rempli.y1

    def poser(fragment):
        if essayer(fragment) is None and etat['y'] > zone.y0:
            nouvelle_page()
        if essayer(fragment, dessiner=True) is None:
            raise ValueError('Un élément de la fiche dépasse une page entière.')

    nouvelle_page()
    elements = blocs(licence, maintenant)
    i = 0
    while i < len(elements):
        element = elements[i]
        # Un titre reste avec ce qui le suit.
        prefixe = ''
        while isinstance(element, str) and element.startswith(('<h2', '<h3', '<p class="sous"')) and i + 1 < len(elements):
            prefixe += element
            i += 1
            element = elements[i]
        if not isinstance(element, Tableau):
            poser(prefixe + element)
            i += 1
            continue
        debut = 0
        while debut < len(element.lignes):
            # Plus grand nombre de lignes qui tient dans la place restante.
            bas, haut = 0, len(element.lignes) - debut
            while bas < haut:
                milieu = (bas + haut + 1) // 2
                if essayer(prefixe + element.html(debut, debut + milieu)) is not None:
                    bas = milieu
                else:
                    haut = milieu - 1
            if bas == 0:
                if etat['y'] == zone.y0:
                    raise ValueError('Une ligne de tableau dépasse une page entière.')
                nouvelle_page()
                continue
            # Au moins deux lignes avec un titre, sinon le titre passe à la page suivante.
            if prefixe and bas < min(2, len(element.lignes)) and etat['y'] > zone.y0:
                nouvelle_page()
                continue
            essayer(prefixe + element.html(debut, debut + bas), dessiner=True)
            etat['y'] += 2
            prefixe = ''
            debut += bas
        i += 1
    redacteur.end_page()
    redacteur.close()
    return _finaliser(sortie.getvalue(), licence, page)


def _finaliser(contenu, licence, page):
    """Pied de page « Dossier … · Page x / n » et métadonnées."""
    import pymupdf
    document = pymupdf.open('pdf', contenu)
    titre = f"Dossier {licence.get('numero_validation', '')} · AsyDec"
    for i, p in enumerate(document, 1):
        p.insert_text((32, page.height - 18), titre, fontsize=7, fontname='helv', color=(0.38, 0.46, 0.54))
        texte = f'Page {i} / {document.page_count}'
        p.insert_text((page.width - 32 - pymupdf.get_text_length(texte, 'helv', 7), page.height - 18), texte,
                      fontsize=7, fontname='helv', color=(0.38, 0.46, 0.54))
    document.set_metadata({'title': titre, 'creator': 'AsyDec'})
    return document.tobytes(garbage=3, deflate=True)
