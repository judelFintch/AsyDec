"""Documents commerciaux natifs AsyDec : cinq présentations, un dossier, trois Word."""
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sqlite3
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED
from zoneinfo import ZoneInfo

from asydec import chemins
from asydec.declarations import factures, modeles_generes
from asydec.declarations.nombres_lettres import dollars_us, nombre as lettres
from asydec.declarations.quantites_entieres import pu_exact, pu_texte

BASE = chemins.DONNEES / 'factures_systeme.db'
STYLES = {
    'classique': dict(nom='Classique', couleur='1F2A44', pale='F4F5F7', police='Times New Roman', taille=10.5, grille=True, banniere=False, centre=True),
    'marine': dict(nom='Marine', couleur='153C59', pale='EEF4F8', police='Arial', taille=9.5, grille=False, banniere=True, centre=False),
    'epure': dict(nom='Épuré', couleur='2F3B4A', pale='F7F8FA', police='Calibri', taille=10.5, grille=False, banniere=False, centre=False),
    'registre': dict(nom='Registre', couleur='1E5A45', pale='EEF6F1', police='Calibri', taille=10.5, grille=True, banniere=True, centre=True),
    'compact': dict(nom='Compact', couleur='374151', pale='F3F4F6', police='Arial', taille=9, grille=True, banniere=False, centre=False),
}
# Version de la mise en page : une nouvelle version régénère les Word archivés, sans changer les numéros.
VERSION_MISE_EN_PAGE = 2
TITRES = {'facture': 'COMMERCIAL INVOICE', 'packing': 'PACKING LIST', 'manifeste': 'ROAD FREIGHT MANIFEST'}
# Références commerciales anglaises par code SH, indépendantes de l'ordre des Word.
DESIGNATIONS = {'630900': 'USED CLOTHING', '630419': 'USED BEDSPREADS',
                '621050': 'OTHER USED GARMENTS', '630420': 'MOSQUITO NETS FOR BEDS',
                '630190': 'USED BLANKETS', '621790': 'PARTS OF GARMENTS OR CLOTHING ACCESSORIES',
                '950790': 'FISHING EQUIPMENT AND ACCESSORIES', '732391': 'CAST IRON HOUSEHOLD ARTICLES'}
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
LARGEUR = 9906  # A4 (11 906) moins deux marges de 1 000 twips
CENTIME = Decimal('.01')


def _d(valeur, champ):
    try:
        d = Decimal(str(valeur).replace('\u00a0', '').replace(' ', '').replace(',', '.'))
    except (InvalidOperation, ValueError):
        raise ValueError(f'{champ} : nombre invalide.') from None
    if not d.is_finite() or d < 0:
        raise ValueError(f'{champ} : nombre positif attendu.')
    return d


def profil_dossier(modele):
    """Identités du XML du dossier, sans reprendre le client d'un autre Word."""
    profil = dict(fournisseur='', adresse_fournisseur='', adresse_client='', transporteur='',
                  depart='', destination='', conteneur='', scelle='')
    xml = modele.get('modele_xml') or modele.get('base_xml')
    if xml:
        racine = ET.fromstring(xml)
        def bloc(tag):
            return next(((e.text or '').strip() for e in racine.iter() if e.tag.split('}')[-1] == tag), '')
        vendeur = bloc('Exporter_name').splitlines()
        profil['fournisseur'] = vendeur[0].strip() if vendeur else ''
        profil['adresse_fournisseur'] = '\n'.join(vendeur[1:]).strip()
        acheteur = bloc('Consignee_name').splitlines()
        profil['adresse_client'] = '\n'.join(acheteur[1:]).strip()
    if modele.get('source') == 'xml':
        profil['depart'] = modele.get('depart', '').upper()
        profil['destination'] = modele.get('destination', '').upper()
    return profil


def propositions_articles(modele):
    info = modele['resultat'].get('info', {})
    sources = info.get('designations', [])
    codes = info.get('positions_tarifaires', [])
    n = len(modele['resultat'].get('resume', {}).get('articles', []))
    return [dict(source=sources[i] if i < len(sources) else '',
                 code=str(codes[i]) if i < len(codes) else '',
                 anglais=next((v for k, v in DESIGNATIONS.items() if i < len(codes) and str(codes[i]).startswith(k)), ''))
            for i in range(n)]


PAYS = {'TZ': 'TANZANIA', 'ZM': 'ZAMBIA', 'KE': 'KENYA', 'UG': 'UGANDA', 'RW': 'RWANDA', 'BI': 'BURUNDI',
        'ZA': 'SOUTH AFRICA', 'MZ': 'MOZAMBIQUE', 'AO': 'ANGOLA', 'MW': 'MALAWI', 'ZW': 'ZIMBABWE',
        'BW': 'BOTSWANA', 'NA': 'NAMIBIA', 'CD': 'DR CONGO', 'AE': 'UNITED ARAB EMIRATES', 'CN': 'CHINA',
        'IN': 'INDIA', 'PK': 'PAKISTAN', 'GB': 'UNITED KINGDOM', 'US': 'UNITED STATES', 'CA': 'CANADA',
        'BE': 'BELGIUM', 'NL': 'NETHERLANDS', 'DE': 'GERMANY', 'FR': 'FRANCE', 'IT': 'ITALY', 'KR': 'SOUTH KOREA',
        'JP': 'JAPAN', 'TR': 'TURKEY', 'OM': 'OMAN', 'SA': 'SAUDI ARABIA'}


def _texte(racine, chemin):
    e = racine.find(chemin)
    return (e.text or '').strip() if e is not None and e.text else ''


def modele_depuis_xml(chemin):
    """Dossier Friperie en mémoire construit depuis une déclaration ASYCUDA (sans enregistrement)."""
    contenu = Path(chemin).read_bytes()
    try:
        racine = ET.fromstring(contenu)
    except ET.ParseError as exc:
        raise ValueError(f'XML illisible : {exc}') from None
    if racine.tag.split('}')[-1] != 'ASYCUDA':
        raise ValueError('Une déclaration ASYCUDA est attendue.')
    articles, colis, designations, codes, alertes = [], [], [], [], []
    for position, item in enumerate(racine.findall('Item'), 1):
        valeurs = {cle: _texte(item, champ) for cle, champ in (
            ('fob', 'Tarification/Item_price'), ('poids', 'Valuation_item/Weight_itm/Gross_weight_itm'),
            ('colis', 'Packages/Number_of_packages'), ('code', 'Tarification/HScode/Commodity_code'),
            ('nom', 'Goods_description/Commercial_Description'),
            ('libelle', 'Goods_description/Description_of_goods'))}
        if not any(valeurs.values()):
            continue
        fob = _d(valeurs['fob'] or 0, f'FOB article {position}')
        poids = _d(valeurs['poids'] or 0, f'Poids article {position}')
        nb = _d(valeurs['colis'] or 0, f'Colis article {position}')
        if not valeurs['code'] and fob == 0 and poids == 0 and nb == 0:
            continue
        articles.append(dict(fob=fob, poids=poids))
        colis.append(nb)
        designations.append(valeurs['nom'] or valeurs['libelle'])
        codes.append(valeurs['code'])
    if not articles:
        raise ValueError('Aucun article exploitable dans ce XML.')
    fob = sum((a['fob'] for a in articles), Decimal(0))
    poids = sum((a['poids'] for a in articles), Decimal(0))
    devise = _texte(racine, 'Valuation/Gs_Invoice/Currency_code')
    if devise and devise != 'USD':
        alertes.append(f'Devise du XML : {devise} ; les documents sont libellés en USD.')
    for libelle, champ, somme in (('FOB', 'Valuation/Total/Total_invoice', fob),
                                  ('Poids', 'Valuation/Total/Total_weight', poids),
                                  ('Colis', 'Property/Nbers/Total_number_of_packages', sum(colis, Decimal(0)))):
        total = _texte(racine, champ)
        try:
            if total and abs(_d(total, libelle) - somme) > CENTIME:
                alertes.append(f'{libelle} : total XML {total} différent de la somme des articles ({somme}).')
        except ValueError:
            alertes.append(f'{libelle} : total XML illisible.')
    plaque = (_texte(racine, 'Transport/Means_of_transport/Border_information/Identity')
              or _texte(racine, 'Transport/Means_of_transport/Departure_arrival_information/Identity'))
    importateur = _texte(racine, 'Traders/Consignee/Consignee_name').split('\n')[0].strip()
    return dict(id=0, source='xml', fichier=Path(chemin).name, empreinte_xml=hashlib.sha256(contenu).hexdigest(),
                importateur=importateur, plaque=plaque, modele_xml=contenu.decode('utf-8', 'replace'),
                destination=', '.join(x for x in (_texte(racine, 'Transport/Delivery_terms/Place'), 'DRC') if x),
                depart=PAYS.get(_texte(racine, 'General_information/Country/Export/Export_country_code'),
                                _texte(racine, 'General_information/Country/Export/Export_country_name')),
                alertes=alertes,
                resultat=dict(module='friperie', colis=colis,
                              info=dict(designations=designations, positions_tarifaires=codes),
                              resume=dict(articles=articles, fob=fob, poids=poids, colis=colis)))


def preparer_donnees(modele, profil):
    if modele.get('supprime'):
        raise ValueError('Restaurez le dossier avant de générer ses documents.')
    if modele['resultat'].get('module', 'friperie') != 'friperie':
        raise ValueError('Ce générateur attend un dossier Friperie.')
    client = str(modele.get('importateur') or '').strip()
    plaque = str(modele.get('plaque') or '').strip()
    fournisseur = str(profil.get('fournisseur') or '').strip()
    if not client or not plaque or not fournisseur:
        raise ValueError('Importateur, plaque et fournisseur sont obligatoires.')
    resultat = modele['resultat']
    resume = resultat['resume']
    articles = resume.get('articles') or []
    colis = resultat.get('colis', resume.get('colis', []))
    libelles = profil.get('designations')
    if libelles is None:
        libelles = [p['anglais'] for p in propositions_articles(modele)]
    if not articles or len(articles) != len(colis) or len(articles) != len(libelles):
        raise ValueError('Articles, colis et désignations doivent correspondre ligne par ligne.')
    if len(articles) > 24:
        raise ValueError('Ce format sur une page accepte au maximum 24 articles.')
    lignes = []
    for i, (a, q, libelle) in enumerate(zip(articles, colis, libelles), 1):
        libelle = ' '.join(str(libelle).split())
        if not libelle or len(libelle) > 100:
            raise ValueError(f'Article {i} : renseignez une désignation anglaise de 100 caractères maximum.')
        poids, valeur, quantite = _d(a['poids'], f'Poids {i}'), _d(a['fob'], f'FOB {i}'), _d(q, f'Colis {i}')
        if poids <= 0 or quantite <= 0 or quantite != quantite.to_integral_value():
            raise ValueError(f'Article {i} : poids positif et colis entiers positifs requis.')
        if valeur != valeur.quantize(CENTIME):
            raise ValueError(f'Article {i} : le FOB doit être exprimé au centime.')
        prix = pu_exact(poids, valeur) if valeur else Decimal('0')
        if prix is None:
            raise ValueError(f'Article {i} : impossible de présenter un prix au kg cohérent au centime.')
        lignes.append(dict(designation=libelle, poids=poids, colis=quantite, fob=valeur, prix=prix))
    fob = sum((l['fob'] for l in lignes), Decimal(0))
    poids = sum((l['poids'] for l in lignes), Decimal(0))
    if abs(fob - _d(resume['fob'], 'FOB total')) > CENTIME or abs(poids - _d(resume['poids'], 'Poids total')) > CENTIME:
        raise ValueError('Les totaux du dossier ne correspondent pas à la somme de ses articles.')
    propres = {k: str(profil.get(k) or '').strip() for k in profil_dossier({})}
    for k, valeur in propres.items():
        if len(valeur) > (300 if k.startswith('adresse') else 100):
            raise ValueError(f'Champ {k} trop long pour le format sur une page.')
    donnees = dict(modele_id=modele['id'], client=client, plaque=plaque, profil=propres, lignes=lignes,
                   fob=fob, poids=poids, colis=sum((l['colis'] for l in lignes), Decimal(0)))
    if modele.get('source') == 'xml':
        # L'empreinte du XML distingue ses documents ; les dossiers enregistrés gardent leur empreinte.
        donnees['source_xml'] = modele['empreinte_xml']
    return donnees


def _fmt(d, dec=2):
    return f'{d:,.{dec}f}'


# ---------------------------------------------------------------------------
# Mise en page professionnelle : blocs encadrés, marges de cellules généreuses,
# totaux intégrés au tableau, attestation et signature. Une seule page A4.
# ---------------------------------------------------------------------------
GRIS = '6B7280'
TRAIT = 'D5DBE1'


def _rpr(s, gras=False, taille=None, couleur=None, majuscules_espacees=False, italique=False):
    taille = taille or s['taille']
    return (f'<w:rPr><w:rFonts w:ascii="{s["police"]}" w:hAnsi="{s["police"]}" w:cs="{s["police"]}"/>'
            + ('<w:b/>' if gras else '') + ('<w:i/>' if italique else '')
            + (f'<w:color w:val="{couleur}"/>' if couleur else '')
            + ('<w:spacing w:val="12"/>' if majuscules_espacees else '')
            + f'<w:sz w:val="{round(taille*2)}"/><w:szCs w:val="{round(taille*2)}"/></w:rPr>')


def _r(t, s, **k):
    lignes = str(t).splitlines() or ['']
    return '<w:r>' + _rpr(s, **k) + '<w:br/>'.join(
        '<w:t xml:space="preserve">' + escape(x) + '</w:t>' for x in lignes) + '</w:r>'


def _p(runs, align='left', avant=0, apres=0, interligne=252, bas=None, fond=None, gauche=None, haut=None):
    bords = ''
    if bas or gauche or haut:
        bords = '<w:pBdr>' + (f'<w:top w:val="single" w:sz="{haut[1]}" w:space="6" w:color="{haut[0]}"/>' if haut else '') \
                + (f'<w:left w:val="single" w:sz="{gauche[1]}" w:space="8" w:color="{gauche[0]}"/>' if gauche else '') \
                + (f'<w:bottom w:val="single" w:sz="{bas[1]}" w:space="4" w:color="{bas[0]}"/>' if bas else '') + '</w:pBdr>'
    return (f'<w:p><w:pPr><w:keepNext/>{bords}' + (f'<w:shd w:val="clear" w:color="auto" w:fill="{fond}"/>' if fond else '')
            + f'<w:spacing w:before="{avant}" w:after="{apres}" w:line="{interligne}" w:lineRule="auto"/>'
            + f'<w:jc w:val="{align}"/></w:pPr>' + runs + '</w:p>')


def _espace(hauteur):
    return f'<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="{hauteur}" w:lineRule="exact"/></w:pPr></w:p>'


def _bords(cotes, couleur=TRAIT, taille=4):
    return ''.join(f'<w:{c} w:val="single" w:sz="{taille}" w:space="0" w:color="{couleur}"/>' if c in cotes
                   else f'<w:{c} w:val="nil"/>' for c in ('top', 'left', 'bottom', 'right'))


def _cellule(contenu, largeur, fond=None, bords=None, span=1, valign='center', marges=None):
    mar = ''
    if marges:
        h, l = marges
        mar = (f'<w:tcMar><w:top w:w="{h}" w:type="dxa"/><w:left w:w="{l}" w:type="dxa"/>'
               f'<w:bottom w:w="{h}" w:type="dxa"/><w:right w:w="{l}" w:type="dxa"/></w:tcMar>')
    return (f'<w:tc><w:tcPr><w:tcW w:w="{largeur}" w:type="dxa"/>' + (f'<w:gridSpan w:val="{span}"/>' if span > 1 else '')
            + (f'<w:tcBorders>{bords}</w:tcBorders>' if bords is not None else '')
            + (f'<w:shd w:val="clear" w:color="auto" w:fill="{fond}"/>' if fond else '') + mar
            + f'<w:vAlign w:val="{valign}"/></w:tcPr>' + (contenu or '<w:p/>') + '</w:tc>')


def _tableau(lignes, largeurs, marges=(60, 110), sans_bords=True):
    assert sum(largeurs) == LARGEUR, (sum(largeurs), LARGEUR)
    bords = '<w:tblBorders>' + ''.join(f'<w:{c} w:val="nil"/>' for c in
                                       ('top', 'left', 'bottom', 'right', 'insideH', 'insideV')) + '</w:tblBorders>'
    h, l = marges
    return (f'<w:tbl><w:tblPr><w:tblW w:w="{LARGEUR}" w:type="dxa"/><w:tblLayout w:type="fixed"/>'
            + (bords if sans_bords else '')
            + f'<w:tblCellMar><w:top w:w="{h}" w:type="dxa"/><w:left w:w="{l}" w:type="dxa"/>'
            f'<w:bottom w:w="{h}" w:type="dxa"/><w:right w:w="{l}" w:type="dxa"/></w:tblCellMar></w:tblPr>'
            '<w:tblGrid>' + ''.join(f'<w:gridCol w:w="{w}"/>' for w in largeurs) + '</w:tblGrid>'
            + ''.join(lignes) + '</w:tbl>')


def _tr(cellules, entete=False, hauteur=None):
    return ('<w:tr><w:trPr><w:cantSplit/>' + ('<w:tblHeader/>' if entete else '')
            + (f'<w:trHeight w:val="{hauteur}" w:hRule="atLeast"/>' if hauteur else '') + '</w:trPr>'
            + ''.join(cellules) + '</w:tr>')


def _etiquette(t, s, couleur=None, align='left', apres=40):
    return _p(_r(t.upper(), s, gras=True, taille=7.5, couleur=couleur or s['couleur'], majuscules_espacees=True),
              align, apres=apres)


def _en_tete(d, genre, s):
    p = d['profil']
    banniere = s['banniere']
    texte = 'FFFFFF' if banniere else None
    discret = 'E5E7EB' if banniere else GRIS
    numero = d['manifeste'] if genre == 'manifeste' else d['numero']
    date = d['date_manifeste'] if genre == 'manifeste' else d['date_facture']
    refs = [('Manifest No.' if genre == 'manifeste' else 'Invoice No.', numero), ('Date', date)]
    if genre != 'facture':
        refs.append(('Invoice Ref.', d['numero']))
    def ref(libelle, valeur, align):
        return _p(_r(libelle + '   ', s, taille=8.5, couleur=discret) + _r(valeur, s, gras=True, taille=10.5, couleur=texte),
                  align, apres=50)
    fournisseur = (_p(_r(p['fournisseur'], s, gras=True, taille=s['taille'] + 7, couleur=texte or s['couleur']), apres=60)
                   + _p(_r(p['adresse_fournisseur'], s, taille=8.5, couleur=discret), interligne=240))
    if s['centre']:
        corps = (_p(_r(p['fournisseur'], s, gras=True, taille=s['taille'] + 8, couleur=texte or s['couleur']), 'center', apres=60)
                 + _p(_r(p['adresse_fournisseur'].replace('\n', ' · '), s, taille=8.5, couleur=discret), 'center',
                      apres=s['bloc'] // 2)
                 + _p(_r(TITRES[genre], s, gras=True, taille=15, couleur=texte or s['couleur'], majuscules_espacees=True),
                      'center', apres=s['bloc'] // 3)
                 + _p('   ·   '.join(_r(l + '  ', s, taille=8.5, couleur=discret) + _r(v, s, gras=True, taille=10.5, couleur=texte)
                                    for l, v in refs).replace('   ·   ', _r('     |     ', s, couleur=discret)), 'center'))
        cellule = _cellule(corps, LARGEUR, fond=s['couleur'] if banniere else None,
                           marges=(s['entete'], 240) if banniere else (0, 0))
        xml = _tableau([_tr([cellule])], [LARGEUR], marges=(0, 0))
    else:
        g, dr = 5600, LARGEUR - 5600
        droite = (_p(_r(TITRES[genre], s, gras=True, taille=17, couleur=texte or s['couleur'], majuscules_espacees=True),
                     'right', apres=140) + ''.join(ref(l, v, 'right') for l, v in refs))
        marges = (s['entete'], 240) if banniere else (0, 0)
        fond = s['couleur'] if banniere else None
        xml = _tableau([_tr([_cellule(fournisseur, g, fond=fond, marges=marges, valign='top'),
                             _cellule(droite, dr, fond=fond, marges=marges, valign='top')])], [g, dr], marges=(0, 0))
    if not banniere:
        xml += _p('', bas=(s['couleur'], 18), apres=0, interligne=120)
    return xml


def _parties(d, genre, s):
    p = d['profil']
    gauche_titre = 'Shipper / Carrier' if genre == 'manifeste' else 'Seller / Exporter'
    gauche = (_etiquette(gauche_titre, s) + _p(_r(p['fournisseur'], s, gras=True), apres=40)
              + _p(_r(p['adresse_fournisseur'] or '—', s, taille=8.5, couleur=GRIS), interligne=240))
    droite = (_etiquette('Buyer / Consignee', s) + _p(_r(d['client'], s, gras=True), apres=40)
              + _p(_r(p['adresse_client'] or '—', s, taille=8.5, couleur=GRIS), interligne=240))
    bloc, ecart = 4853, LARGEUR - 2 * 4853
    cadre = _bords('top left bottom right'.split()) if s['grille'] else _bords(['top'], s['couleur'], 12)
    return _tableau([_tr([_cellule(gauche, bloc, fond=s['pale'], bords=cadre, valign='top', marges=(s['cadre'], 170)),
                          _cellule('', ecart, bords=_bords([])),
                          _cellule(droite, bloc, fond=s['pale'], bords=cadre, valign='top', marges=(s['cadre'], 170))])],
                    [bloc, ecart, bloc], marges=(0, 0))


def _expedition(d, genre, s):
    p = d['profil']
    tiret = lambda v: v or '—'
    if genre == 'manifeste':
        champs = [[('Carrier', tiret(p['transporteur'])), ('Vehicle Reg. No.', d['plaque']),
                   ('Place of Loading', tiret(p['depart'])), ('Destination', tiret(p['destination']))],
                  [('Container No.', tiret(p['conteneur'])), ('Seal No.', tiret(p['scelle'])),
                   ('Invoice No.', d['numero']), ('Invoice Date', d['date_facture'])]]
    elif genre == 'packing':
        champs = [[('Vehicle Reg. No.', d['plaque']), ('Place of Loading', tiret(p['depart'])),
                   ('Destination', tiret(p['destination'])), ('Packing', 'Pressed bales')]]
    else:
        champs = [[('Vehicle Reg. No.', d['plaque']), ('Place of Loading', tiret(p['depart'])),
                   ('Destination', tiret(p['destination'])), ('Terms · Currency', 'FOB · USD')]]
    largeur = LARGEUR // 4
    largeurs = [largeur] * 3 + [LARGEUR - 3 * largeur]
    lignes = []
    for rang in champs:
        cellules = []
        for i, (libelle, valeur) in enumerate(rang):
            cellules.append(_cellule(_etiquette(libelle, s, couleur=GRIS, apres=30) + _p(_r(valeur, s, gras=True)),
                                     largeurs[i], bords=_bords(['bottom'] + (['left'] if i else [])), valign='top',
                                     marges=(s['cadre'] - 30, 150)))
        lignes.append(_tr(cellules))
    return _tableau(lignes, largeurs, marges=(0, 0))


def _articles(d, genre, s):
    marge = (s['ligne'], 120)
    if genre == 'facture':
        entetes = ['No.', 'Description of Goods', 'Bales', 'Net Weight (kg)', 'Unit Price (USD/kg)', 'Amount (USD)']
        largeurs = [560, 3226, 1000, 1600, 1620, 1900]
        lignes = [[str(i), l['designation'], _fmt(l['colis'], 0), _fmt(l['poids']), pu_texte(l['prix']), _fmt(l['fob'])]
                  for i, l in enumerate(d['lignes'], 1)]
        final = ('TOTAL FOB VALUE (USD)', _fmt(d['fob']))
    else:
        entetes = ['No.', 'Description of Goods', 'Bales', 'Net Weight (kg)', 'Avg. kg / Bale']
        largeurs = [560, 4546, 1400, 1800, 1600]
        lignes = [[str(i), l['designation'], _fmt(l['colis'], 0), _fmt(l['poids']),
                   _fmt((l['poids'] / l['colis']).quantize(CENTIME, ROUND_HALF_UP))]
                  for i, l in enumerate(d['lignes'], 1)]
    aligns = ['center', 'left'] + ['right'] * (len(entetes) - 2)
    grille = _bords('top left bottom right'.split()) if s['grille'] else _bords(['bottom'])
    rows = [_tr([_cellule(_p(_r(t.upper(), s, gras=True, taille=7.5, couleur='FFFFFF', majuscules_espacees=True), aligns[i]),
                          w, fond=s['couleur'], bords=_bords([]) if not s['grille'] else grille, marges=(110, 120))
                 for i, (t, w) in enumerate(zip(entetes, largeurs))], entete=True)]
    for n, ligne in enumerate(lignes):
        fond = s['pale'] if n % 2 else None
        rows.append(_tr([_cellule(_p(_r(t, s), aligns[i]), w, fond=fond, bords=grille, marges=marge)
                         for i, (t, w) in enumerate(zip(ligne, largeurs))]))
    total_lisible = ('Total', _fmt(d['colis'], 0), _fmt(d['poids']),
                     _fmt((d['poids'] / d['colis']).quantize(CENTIME, ROUND_HALF_UP)))
    if genre == 'facture':
        cellules = [_cellule(_p(_r('TOTAL', s, gras=True), 'right'), largeurs[0] + largeurs[1], span=2,
                             bords=_bords(['top'], s['couleur'], 12), marges=(120, 120)),
                    _cellule(_p(_r(_fmt(d['colis'], 0), s, gras=True), 'right'), largeurs[2], bords=_bords(['top'], s['couleur'], 12), marges=(120, 120)),
                    _cellule(_p(_r(_fmt(d['poids']), s, gras=True), 'right'), largeurs[3], bords=_bords(['top'], s['couleur'], 12), marges=(120, 120)),
                    _cellule(_p(_r('', s)), largeurs[4], bords=_bords(['top'], s['couleur'], 12)),
                    _cellule(_p(_r(_fmt(d['fob']), s, gras=True), 'right'), largeurs[5], bords=_bords(['top'], s['couleur'], 12), marges=(120, 120))]
        rows.append(_tr(cellules))
        rows.append(_tr([_cellule(_p(''), sum(largeurs[:3]), span=3, bords=_bords([])),
                         _cellule(_p(_r(final[0], s, gras=True, taille=9, couleur='FFFFFF', majuscules_espacees=True), 'left'),
                                  largeurs[3] + largeurs[4], span=2, fond=s['couleur'], bords=_bords([]), marges=(150, 140)),
                         _cellule(_p(_r(final[1], s, gras=True, taille=s['taille'] + 2, couleur='FFFFFF'), 'right'),
                                  largeurs[5], fond=s['couleur'], bords=_bords([]), marges=(150, 140))]))
    else:
        haut = _bords(['top'], s['couleur'], 12)
        rows.append(_tr([_cellule(_p(_r('TOTAL', s, gras=True), 'right'), largeurs[0] + largeurs[1], span=2, bords=haut, marges=(130, 120))]
                        + [_cellule(_p(_r(v, s, gras=True), 'right'), w, bords=haut, marges=(130, 120))
                           for v, w in zip(total_lisible[1:], largeurs[2:])]))
    return _tableau(rows, largeurs, marges=(0, 0), sans_bords=True)


def _en_lettres(libelle, texte, s):
    contenu = (_etiquette(libelle, s, apres=50) + _p(_r(texte, s, gras=True, taille=9.5), interligne=260))
    bords = _bords(['left'], s['couleur'], 24)
    return _tableau([_tr([_cellule(contenu, LARGEUR, fond=s['pale'], bords=bords, marges=(130, 200))])],
                    [LARGEUR], marges=(0, 0))


def _signatures(d, genre, s):
    moitie = LARGEUR // 2
    def bloc(titre, sous_titre, align):
        return (_p(_r(titre, s, gras=True, taille=9), align, apres=s['signature'])
                + _p(_r(sous_titre, s, taille=8, couleur=GRIS), align, avant=0, haut=('9CA3AF', 6)))
    if genre == 'manifeste':
        g = bloc('Driver / Carrier', 'Name, signature and date', 'left')
        dr = bloc('Customs Office', 'Official stamp and signature', 'right')
    else:
        g = bloc('Received by the Consignee', 'Signature and date', 'left')
        dr = bloc('For ' + d['profil']['fournisseur'], 'Authorised signature and company stamp', 'right')
    return _tableau([_tr([_cellule(g, moitie - 400, valign='bottom', bords=_bords([])),
                          _cellule('', 800, bords=_bords([])),
                          _cellule(dr, LARGEUR - moitie - 400, valign='bottom', bords=_bords([]))])],
                    [moitie - 400, 800, LARGEUR - moitie - 400], marges=(0, 0))


DECLARATIONS = {
    'facture': 'We hereby certify that this invoice shows the actual price of the goods described, '
               'that all particulars are true and correct, and that payment is due on the FOB value stated above.',
    'packing': 'We hereby certify that the goods listed above have been packed and loaded as stated, '
               'and that the number of bales and net weights are true and correct.',
    'manifeste': 'The goods listed above are carried as per the commercial invoice and packing list referenced. '
                 'The carrier acknowledges receipt of the cargo in apparent good order and condition.',
}


def _document(d, genre, style_id):
    s = dict(STYLES[style_id])
    n = len(d['lignes'])
    # Trois densités pour tenir sur une page A4 : aérée, moyenne, serrée (police jamais sous 8,5 pt).
    densite = (dict(bloc=240, ligne=85, cadre=130, entete=220, signature=700) if n <= 8 else
               dict(bloc=150, ligne=45, cadre=100, entete=160, signature=560) if n <= 14 else
               dict(bloc=90, ligne=12, cadre=70, entete=110, signature=440))
    s.update(densite)
    if n > 8:
        s['taille'] = min(s['taille'], 9.5 if n <= 14 else 8.5)
    bloc = s['bloc']
    xml = _en_tete(d, genre, s) + _espace(bloc)
    xml += _parties(d, genre, s) + _espace(bloc - 40)
    xml += _expedition(d, genre, s) + _espace(bloc)
    xml += _articles(d, genre, s) + _espace(bloc)
    if genre == 'facture':
        xml += _en_lettres('Amount in words', dollars_us(d['fob']), s)
    else:
        xml += _en_lettres('Total net weight in words', lettres(d['poids']) + ' KILOGRAMS', s)
    xml += _p(_r(DECLARATIONS[genre], s, taille=8, couleur=GRIS, italique=True), avant=bloc, apres=bloc, interligne=264)
    xml += _signatures(d, genre, s)
    pied = ' · '.join(x for x in (d['profil']['fournisseur'], d['profil']['adresse_fournisseur'].replace('\n', ', ')) if x)
    xml += _p(_r(pied, s, taille=7, couleur='9CA3AF'), 'center', avant=bloc, bas=None)
    return _docx(xml)


def _docx(corps):
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:document xmlns:w="{W}"><w:body>' + corps
                + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="800" w:bottom="700" '
                'w:left="1000" w:right="1000" w:header="360" w:footer="360"/></w:sectPr></w:body></w:document>')
    types = ('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    out = BytesIO()
    with ZipFile(out,'w',ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',types);z.writestr('_rels/.rels',rels);z.writestr('word/document.xml',document)
    return out.getvalue()


@contextmanager
def connexion(base=None):
    path = Path(base) if base is not None else BASE
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.executescript('''CREATE TABLE IF NOT EXISTS dossiers (
          id INTEGER PRIMARY KEY, modele_id INTEGER NOT NULL, empreinte TEXT UNIQUE NOT NULL,
          numero TEXT UNIQUE NOT NULL, manifeste TEXT UNIQUE NOT NULL, date_facture TEXT NOT NULL,
          date_manifeste TEXT NOT NULL, auteur TEXT NOT NULL, cree_le TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS documents (
          dossier_id INTEGER NOT NULL REFERENCES dossiers(id), style TEXT NOT NULL,
          facture BLOB NOT NULL, packing BLOB NOT NULL, manifeste BLOB NOT NULL,
          PRIMARY KEY(dossier_id,style));''')
        db.execute('PRAGMA foreign_keys=ON')
        with db:
            yield db
    finally:
        db.close()


GABARIT = 'gabarit:'


def modeles_bibliotheque(modele=None, base=None):
    """Modèles Word de la bibliothèque commune (« Modèles de facture »), quel que soit le module qui les a
    importés ; classés pour le dossier (même importateur et mêmes articles d'abord) lorsqu'il est fourni."""
    gabarits = factures.lister_modeles(base)
    return factures.classer_gabarits(gabarits, modele) if modele else gabarits


def _gabarit(gabarit_id, base=None):
    with factures.connexion(base) as db:
        g = db.execute('SELECT id,nom,contenu,articles_json,retire FROM gabarits WHERE id=?', (gabarit_id,)).fetchone()
    if g is None:
        raise ValueError('Modèle de facture introuvable dans la bibliothèque.')
    if g['retire']:
        raise ValueError('Ce modèle a été retiré de la bibliothèque. Rechargez le Word pour l’utiliser à nouveau.')
    from asydec.declarations.preparer_facture import preparer_plaque
    contenu = preparer_plaque(g['contenu'])
    champs = factures.inspecter(contenu)
    if 'PLAQUE' not in champs:
        raise ValueError('Ce modèle ne prévoit aucune zone de plaque. Ajoutez {{PLAQUE}} dans le Word, puis rechargez-le.')
    descriptions = json.loads(g['articles_json']) or factures.analyser_gabarit(contenu)['articles']
    return dict(id=g['id'], nom=g['nom'], contenu=contenu, champs=champs, articles=descriptions,
                fournisseur=factures.analyser_gabarit(contenu)['fournisseur'])


def correspondance_gabarit(gabarit_id, modele, profil, base=None):
    """Articles du Word face aux articles du dossier, pour confirmation avant remplissage."""
    g = _gabarit(gabarit_id, base)
    d = preparer_donnees(modele, profil)
    if g['articles'] and len(g['articles']) != len(d['lignes']):
        raise ValueError(f'Le modèle « {g["nom"]} » contient {len(g["articles"])} articles ; '
                         f'ce dossier en contient {len(d["lignes"])}. Choisissez un modèle correspondant.')
    return dict(nom=g['nom'], fournisseur=g['fournisseur'],
                lignes=[(g['articles'][i] if i < len(g['articles']) else '', l['designation'], l['colis'], l['poids'], l['fob'])
                        for i, l in enumerate(d['lignes'])])


def _document_gabarit(gabarit_id, d, base=None):
    from asydec.formats import nombre
    from asydec.declarations import preparer_facture as P
    g = _gabarit(gabarit_id, base)
    if g['articles'] and len(g['articles']) != len(d['lignes']):
        raise ValueError(f'Le modèle « {g["nom"]} » contient {len(g["articles"])} articles ; ce dossier en contient {len(d["lignes"])}.')
    valeurs = dict(POIDS=nombre(d['poids'], 2), FOB=nombre(d['fob'], 2), COLIS=nombre(d['colis']),
                   IMPORTATEUR=d['client'], PLAQUE=d['plaque'], MODELE_ID=str(d['modele_id'] or 'XML'),
                   FRET=nombre(0, 2), ASSURANCE=nombre(0, 2), CIF_USD=nombre(d['fob'], 2),
                   FOB_LETTRES=lettres(d['fob'], monnaie=True), POIDS_LETTRES=lettres(d['poids']),
                   DATE_FACTURE=d['date_facture'], NUMERO_FACTURE=d['numero'], NUMERO_MANIFESTE=d['manifeste'])
    for i, l in enumerate(d['lignes'], 1):
        # PU exact : colis/poids × PU redonne le FOB de l'article au centime.
        decimales = max(2, -l['prix'].normalize().as_tuple().exponent)
        valeurs.update({f'COLIS_{i}': nombre(l['colis']), f'FOB_{i}': nombre(l['fob'], 2),
                        f'POIDS_{i}': nombre(l['poids'], 2), f'PRIX_UNITAIRE_{i}': nombre(l['prix'], decimales)})
    contenu = P.retirer_page_vide(P.preparer_date(P.preparer_lettres(P.preparer_manifeste(g['contenu']))))
    contenu = factures.remplir(contenu, valeurs)
    contenu = P.cadrer_immatriculation(P.libelles_anglais(contenu), plaque=d['plaque'])
    return P.dater_manifeste(contenu, d['date_manifeste'])


def generer(modele_id, style, profil, auteur, base=None, base_modeles=None, base_gabarits=None):
    modele = modeles_generes.detail(modele_id, base=base_modeles)
    return generer_modele(modele, style, profil, auteur, base=base, base_gabarits=base_gabarits)


def generer_xml(chemin, style, profil, auteur, base=None, base_gabarits=None):
    """Facture, packing list et manifeste directement depuis une déclaration XML."""
    return generer_modele(modele_depuis_xml(chemin), style, profil, auteur, base=base, base_gabarits=base_gabarits)


def generer_modele(modele, style, profil, auteur, base=None, base_gabarits=None):
    """style : une présentation AsyDec (STYLES) ou « gabarit:<id> » pour un modèle Word de la bibliothèque.
    Le dossier garde les mêmes numéros et dates quelle que soit la présentation choisie."""
    gabarit_id = int(style[len(GABARIT):]) if style.startswith(GABARIT) else None
    if gabarit_id is None and style not in STYLES:
        raise ValueError('Présentation inconnue.')
    d = preparer_donnees(modele, profil)
    if gabarit_id is not None:
        # Refuser un modèle inutilisable avant de réserver un numéro.
        g = _gabarit(gabarit_id, base_gabarits)
        destinataire = factures.analyser_gabarit(g['contenu'])['destinataire']
        if not factures.correspond_importateur(dict(destinataire=destinataire), modele):
            raise ValueError(f'Le modèle « {g["nom"]} » est établi au nom de « {destinataire or "inconnu"} », '
                             f'pas de {modele.get("importateur")}. Choisissez un modèle de cet importateur '
                             'ou une présentation AsyDec.')
    modele_id = modele['id']
    empreinte = hashlib.sha256(json.dumps(d,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
    cle = style if gabarit_id is not None else f'{style}#v{VERSION_MISE_EN_PAGE}'
    with connexion(base) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM dossiers WHERE empreinte=?',(empreinte,)).fetchone()
        if row is None:
            now = datetime.now(ZoneInfo('Africa/Lubumbashi'))
            numero, manifeste = factures._reserver_numeros(base)
            date = factures.date_facture(now.date()).strftime('%d/%m/%Y')
            dm = factures.date_manifeste(date,numero)
            identifiant = db.execute('INSERT INTO dossiers(modele_id,empreinte,numero,manifeste,date_facture,date_manifeste,auteur,cree_le) '
                                     'VALUES(?,?,?,?,?,?,?,?)',(modele_id,empreinte,numero,manifeste,date,dm,auteur,now.isoformat())).lastrowid
            row = db.execute('SELECT * FROM dossiers WHERE id=?',(identifiant,)).fetchone()
        d.update(numero=row['numero'],manifeste=row['manifeste'],date_facture=row['date_facture'],date_manifeste=row['date_manifeste'])
        archive = db.execute('SELECT facture,packing,manifeste FROM documents WHERE dossier_id=? AND style=?',(row['id'],cle)).fetchone()
        if archive is None:
            if gabarit_id is not None:
                # Le Word de la bibliothèque contient déjà ses propres pages (facture, packing list…).
                documents = dict(facture=_document_gabarit(gabarit_id, d, base_gabarits), packing=b'', manifeste=b'')
            else:
                documents = {genre:_document(d,genre,style) for genre in TITRES}
            db.execute('INSERT INTO documents VALUES(?,?,?,?,?)',(row['id'],cle,documents['facture'],documents['packing'],documents['manifeste']))
        else:
            documents = dict(archive)
    documents = {k: v for k, v in documents.items() if v}
    return dict(id=row['id'],style=style,numero=d['numero'],manifeste=d['manifeste'],date_facture=d['date_facture'],
                date_manifeste=d['date_manifeste'],documents=documents,importateur=d['client'],plaque=d['plaque'])


def exporter(resultat, dossier):
    dossier = Path(dossier)
    dossier.mkdir(parents=True,exist_ok=True)
    plaque = re.sub(r'[^A-Za-z0-9._-]+','-',resultat['plaque']).strip('.-') or 'camion'
    fichiers = {}
    for genre, contenu in resultat['documents'].items():
        style = re.sub(r'[^A-Za-z0-9._-]+','-',resultat['style'])
        nom = f'{plaque}-{resultat["numero"]}-{style}-{genre}.docx'
        cible = dossier / nom
        # Écriture atomique : aucun Word partiellement écrit en cas d'interruption.
        temporaire = cible.with_suffix('.docx.tmp')
        temporaire.write_bytes(contenu)
        temporaire.replace(cible)
        fichiers[genre] = cible
    return fichiers
