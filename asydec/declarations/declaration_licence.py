"""Étape 9 : déclaration (DCU) Word de chaque part, remplie depuis son XML sans changer la forme du modèle.

Le modèle (ressources/declaration/Declaration-modele.docx) est la déclaration fournie, dont chaque valeur
d'exemple a été remplacée par une balise {{CHAMP}} (scripts/preparer_modele_declaration.py). Seuls les textes
des balises changent : image de fond, zones de texte, polices et positions restent ceux du modèle.

Source de chaque part : E, L, Q, leurs dates, manifeste et plaques sont toujours ceux de l'étape 3 (projet) ;
le reste vient du XML SYDONIA importé à l'étape 8 pour cette part (version de la douane). Une autre case vide
dans ce XML est complétée depuis les données de la part dans AsyDec, et signalée ; une part sans XML SYDONIA
n'a pas de déclaration.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom
from zipfile import ZipFile, BadZipFile

from asydec.declarations.preparer_facture import texte, remplacer

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
BALISE = re.compile(r'\{\{([A-Z_0-9]+)\}\}')
# Champs sur plusieurs lignes : le paragraphe balisé est répété pour chaque ligne.
LISTES = ('PAYEUR', 'DESTINATAIRE', 'EXPORTATEUR', 'DECLARANT', 'TAXE_CODE', 'TAXE_TAUX', 'TAXE_BASE', 'TAXE_MONTANT')
# Case 47 : comme la déclaration originale, les TAXES_PREVUES premières taxes du XML, dans l'ordre du XML
# et la police du modèle ; les suivantes ne sont pas affichées.
TAXES = ('TAXE_CODE', 'TAXE_TAUX', 'TAXE_BASE', 'TAXE_MONTANT')
TAXES_PREVUES = 8
# Règle du formulaire : la police et la taille du modèle ne changent JAMAIS (ni l'interligne).
# Une valeur trop longue pour sa case est coupée (entre deux mots si possible) à ce qui tient
# à la taille du modèle, et la coupure est signalée. Word replie et déborde un peu avant les
# dimensions calculées : on ne compte que cette part de la largeur et de la hauteur.
EMU_PAR_POINT = 12700
# Calé sur Word : un texte à 94,4 % de la largeur utile tient, à 95,1 % il passe à la ligne.
MARGE_LARGEUR = 0.948
MARGE_HAUTEUR = 0.90
INTERLIGNE_ARIAL = 1.15  # hauteur d'une ligne simple en Arial, en multiple de la taille

# Libellés des cases pour les avertissements de coupure.
CASES = {'PAYEUR': 'case 9 · responsable financier', 'DESTINATAIRE': 'case 8 · destinataire',
         'EXPORTATEUR': 'case 2 · exportateur', 'DECLARANT': 'case 14 · déclarant',
         'TAXE_CODE': 'case 47 · codes taxes', 'TAXE_TAUX': 'case 47 · taux', 'TAXE_BASE': 'case 47 · bases',
         'TAXE_MONTANT': 'case 47 · montants'}


def _zone(paragraphe):
    """(largeur utile, hauteur utile) en points de la zone de texte qui contient le paragraphe, sinon None."""
    noeud = paragraphe.parentNode
    while noeud is not None and not (noeud.nodeType == 1 and noeud.localName == 'wsp'):
        noeud = noeud.parentNode
    if noeud is None:
        return None
    ext = noeud.getElementsByTagNameNS('http://schemas.openxmlformats.org/drawingml/2006/main', 'ext')
    corps = [n for n in noeud.childNodes if n.nodeType == 1 and n.localName == 'bodyPr']
    if not ext or not corps:
        return None
    largeur = int(ext[0].getAttribute('cx')) - sum(int(corps[0].getAttribute(m) or 91440) for m in ('lIns', 'rIns'))
    hauteur = int(ext[0].getAttribute('cy')) - sum(int(corps[0].getAttribute(m) or 45720) for m in ('tIns', 'bIns'))
    return largeur / EMU_PAR_POINT * MARGE_LARGEUR, hauteur / EMU_PAR_POINT * MARGE_HAUTEUR


def largeur_texte(contenu, demi_points):
    """Largeur en points du texte en Arial (chasses Helvetica, identiques)."""
    try:
        import pymupdf
        return pymupdf.get_text_length(contenu, fontname='helv', fontsize=demi_points / 2)
    except Exception:  # noqa: BLE001 - sans pymupdf : estimation moyenne d'Arial
        return len(contenu) * 0.55 * demi_points / 2


def _taille(paragraphe):
    tailles = [int(n.getAttribute('w:val')) for n in paragraphe.getElementsByTagNameNS(W, 'sz')
               if n.getAttribute('w:val').isdigit()]
    return max(tailles or [16])


def lignes_possibles(paragraphe):
    """Nombre de lignes que la zone du paragraphe affiche à la taille du modèle (None sans zone)."""
    zone = _zone(paragraphe)
    if not zone:
        return None
    taille = _taille(paragraphe) / 2
    espacements = paragraphe.getElementsByTagNameNS(W, 'spacing')
    apres = sum(int(espacements[0].getAttribute(c) or 0) for c in ('w:after', 'w:before')) / 20 if espacements else 0
    return max(1, int((zone[1] + apres) // (taille * INTERLIGNE_ARIAL + apres)))


def replier(contenu, largeur, demi_points):
    """Lignes affichées par Word (repli entre les mots ; un mot trop long est coupé)."""
    lignes, courante = [], ''
    for mot in re.split(r'(\s+)', contenu):
        essai = courante + mot
        if courante and not mot.isspace() and largeur_texte(essai.rstrip(), demi_points) > largeur:
            lignes.append(courante.rstrip())
            courante = mot.lstrip()
        else:
            courante = essai
        while largeur_texte(courante.rstrip(), demi_points) > largeur and len(courante) > 1:
            coupe = len(courante)
            while coupe > 1 and largeur_texte(courante[:coupe], demi_points) > largeur:
                coupe -= 1
            lignes.append(courante[:coupe])
            courante = courante[coupe:]
    if courante.strip() or not lignes:
        lignes.append(courante.rstrip())
    return lignes


def _tabulations(paragraphe):
    """Tabulations du texte (pas les taquets définis dans le paragraphe)."""
    return [t for t in paragraphe.getElementsByTagNameNS(W, 'tab') if t.parentNode.localName == 'r']


def _segments(paragraphe):
    """Texte du paragraphe découpé aux tabulations, dans l'ordre des runs."""
    segments = ['']
    for run in paragraphe.getElementsByTagNameNS(W, 'r'):
        for enfant in run.childNodes:
            if enfant.nodeType != 1:
                continue
            if enfant.localName == 't':
                segments[-1] += ''.join(n.data for n in enfant.childNodes if n.nodeType == 3)
            elif enfant.localName == 'tab':
                segments.append('')
    return segments


def _taquets(paragraphe):
    return sorted(int(t.getAttribute('w:pos')) / 20 for t in paragraphe.getElementsByTagNameNS(W, 'tab')
                  if t.parentNode.localName == 'tabs' and t.getAttribute('w:pos').lstrip('-').isdigit())


def _largeur_tabulee(segments, taquets, demi_points):
    x = 0.0
    for i, segment in enumerate(segments):
        if i:
            suivant = next((t for t in taquets if t > x + 0.5), None)
            x = suivant if suivant is not None else (math.floor(x / 36) + 1) * 36  # taquets par défaut : 36 pt
        x += largeur_texte(segment.rstrip() if i == len(segments) - 1 else segment, demi_points)
    return x


def couper(paragraphe):
    """Nombre de caractères du texte gardés pour que le paragraphe tienne dans sa case à la taille du
    modèle (coupe en fin de texte, entre deux mots si possible) ; renvoie (gardés, texte retiré)."""
    contenu = texte(paragraphe)
    zone = _zone(paragraphe)
    if not zone or not contenu.strip():
        return len(contenu), ''
    taille, possibles = _taille(paragraphe), lignes_possibles(paragraphe)
    tabulee = bool(_tabulations(paragraphe))
    segments, taquets = (_segments(paragraphe), _taquets(paragraphe)) if tabulee else (None, None)

    def tient(k):
        if tabulee:
            reste, coupes = k, []
            for segment in segments:
                coupes.append(segment[:max(0, reste)])
                reste -= len(segment)
            return _largeur_tabulee(coupes, taquets, taille) <= zone[0]
        return len(replier(contenu[:k], zone[0], taille)) <= possibles

    if tient(len(contenu)):
        return len(contenu), ''
    candidats = [i for i in range(len(contenu) - 1, 0, -1) if contenu[i] == ' ' and contenu[i - 1] != ' ']
    garde = next((k for k in candidats if contenu[:k].strip() and tient(k)), None)
    if garde is None:
        garde = next((k for k in range(len(contenu) - 1, 0, -1) if tient(k)), 0)
    return garde, contenu[garde:].strip()


def tenir(paragraphe, lignes):
    """Lignes logiques gardées pour que la case les affiche à la taille du modèle : (gardées, retiré).

    retiré : texte non affiché (vide si tout tient). Une ligne trop longue est coupée entre deux mots."""
    zone, possibles = _zone(paragraphe), lignes_possibles(paragraphe)
    if not zone or _tabulations(paragraphe):
        return lignes, ''
    taille = _taille(paragraphe)
    gardees, retire, reste = [], [], possibles
    for ligne in lignes:
        if reste <= 0:
            retire.append(ligne.strip())
            continue
        visuelles = replier(ligne, zone[0], taille)
        if len(visuelles) <= reste:
            gardees.append(ligne)
            reste -= len(visuelles)
        else:
            gardees.append(' '.join(v.strip() for v in visuelles[:reste]) if ligne.strip() else ligne)
            # garder l'indentation éventuelle du modèle
            if visuelles and ligne[:len(ligne) - len(ligne.lstrip())]:
                gardees[-1] = ligne[:len(ligne) - len(ligne.lstrip())] + gardees[-1].lstrip()
            retire.append(' '.join(v.strip() for v in visuelles[reste:]))
            reste = 0
    return gardees, ' / '.join(r for r in retire if r)


def modele_defaut():
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
    return base / 'ressources' / 'declaration' / 'Declaration-modele.docx'


# ---------------------------------------------------------------------------
# Formats du formulaire (comme la déclaration fournie)
# ---------------------------------------------------------------------------

def _decimal(valeur):
    try:
        d = Decimal(str(valeur or '').replace(',', '').replace(' ', '').strip())
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def montant(valeur, decimales=0):
    """1234567.5 -> « 1,234,568 » (decimales=0) ou « 1,234,567.50 »."""
    d = _decimal(valeur)
    return '' if d is None else f'{d:,.{decimales}f}'


def date_dcu(valeur):
    """Date -> JJ/MM/AAAA.

    SYDONIA écrit m/j/aa (année à 2 chiffres, ex. 3/15/19) ; AsyDec (étape 3) écrit déjà JJ/MM/AAAA.
    Une année à 4 chiffres est donc toujours lue jour/mois : 05/11/2026 reste le 5 novembre,
    jamais le 11 mai."""
    texte_ = str(valeur or '').strip()
    formats = ('%m/%d/%y',) if re.fullmatch(r'\d{1,2}/\d{1,2}/\d{2}', texte_) else ('%d/%m/%Y', '%Y-%m-%d', '%d.%m.%Y')
    for format_ in formats:
        try:
            return datetime.strptime(texte_, format_).strftime('%d/%m/%Y')
        except ValueError:
            pass
    return texte_


def licence_courte(numero):
    """Case 44 « Licence No » : seulement le numéro DEC, sans la suite (DEC1707768-7CD6545D-RC -> DEC1707768)."""
    texte_ = str(numero or '').strip()
    return texte_.split('-', 1)[0] if re.match(r'^DEC\d+-', texte_, re.I) else texte_


def _t(element, chemin):
    noeud = element.find(chemin) if element is not None else None
    return ' '.join((noeud.text or '').split()) if noeud is not None and noeud.text else ''


def _lignes(element, chemin):
    noeud = element.find(chemin)
    if noeud is None or not noeud.text:
        return []
    return [' '.join(l.split()) for l in noeud.text.splitlines() if l.strip()]


def nom_banque(nom):
    """Case 28 : le nom de la banque seul, dans la police du modèle ; ce qui suit « / » (ville, agence…) est retiré."""
    return nom.split('/')[0].strip()


def valeurs(contenu_xml):
    """Valeurs des balises depuis un XML ASYCUDA (texte). Le formulaire porte le premier article."""
    r = ET.fromstring(contenu_xml.encode('utf-8') if isinstance(contenu_xml, str) else contenu_xml)
    items = [i for i in r.findall('Item') if _t(i, 'Tarification/HScode/Commodity_code')]
    item = items[0] if items else None
    reference = _t(r, 'Declarant/Reference/Number')
    annee, _, suite = reference.partition('/') if re.match(r'\d{4}/', reference) else ('', '', reference)
    taxes = [t for t in (item.findall('Taxation/Taxation_line') if item is not None else []) if _t(t, 'Duty_tax_code')]
    documents = [_t(d, 'Attached_document_code') for d in (item.findall('Attached_documents') if item is not None else [])]
    v = {
        'NUMERO_E': _t(r, 'Identification/Registration/Number'), 'DATE_E': date_dcu(_t(r, 'Identification/Registration/Date')),
        'NUMERO_L': _t(r, 'Identification/Assessment/Number'), 'DATE_L': date_dcu(_t(r, 'Identification/Assessment/Date')),
        'NUMERO_Q': _t(r, 'Identification/receipt/Number'), 'DATE_Q': date_dcu(_t(r, 'Identification/receipt/Date')),
        'MANIFESTE': _t(r, 'Identification/Manifest_reference_number'),
        'PROCEDURE': _t(r, 'Identification/Type/Declaration_gen_procedure_code'),
        'CODE_BUREAU': _t(r, 'Identification/Office_segment/Customs_clearance_office_code'),
        'NOM_BUREAU': _t(r, 'Identification/Office_segment/Customs_Clearance_office_name'),
        'FORMULAIRE': _t(r, 'Property/Forms/Number_of_the_form') or '1',
        'TOTAL_FORMULAIRES': _t(r, 'Property/Forms/Total_number_of_forms') or '1',
        'NOMBRE_ARTICLES': _t(r, 'Property/Nbers/Total_number_of_items'),
        'TOTAL_COLIS': _t(r, 'Property/Nbers/Total_number_of_packages'),
        'REF_ANNEE': annee, 'REF_SUITE': suite,
        'EXPORTATEUR': _lignes(r, 'Traders/Exporter/Exporter_name'),
        'DESTINATAIRE': _lignes(r, 'Traders/Consignee/Consignee_name'),
        'CODE_DESTINATAIRE': _t(r, 'Traders/Consignee/Consignee_code'),
        'PAYEUR': _lignes(r, 'Traders/Financial/Financial_name') or _lignes(r, 'Traders/Consignee/Consignee_name'),
        'CODE_PAYEUR': _t(r, 'Traders/Financial/Financial_code') or _t(r, 'Traders/Consignee/Consignee_code'),
        'DECLARANT': _lignes(r, 'Declarant/Declarant_name'), 'CODE_DECLARANT': _t(r, 'Declarant/Declarant_code'),
        'PAYS_TRANSACTION': _t(r, 'General_information/Country/Trading_country')
                            or _t(r, 'General_information/Country/Export/Export_country_code'),
        'CODE_PAYS_EXPORT': _t(r, 'General_information/Country/Export/Export_country_code'),
        'NOM_PAYS_EXPORT': _t(r, 'General_information/Country/Export/Export_country_name'),
        'NOM_PAYS_ORIGINE': _t(r, 'General_information/Country/Country_of_origin_name'),
        'CODE_DESTINATION': _t(r, 'General_information/Country/Destination/Destination_country_code'),
        'NOM_DESTINATION': _t(r, 'General_information/Country/Destination/Destination_country_name'),
        'FRAIS': montant(_t(r, 'General_information/Value_details')),
        'PLAQUE_ARRIVEE': _t(r, 'Transport/Means_of_transport/Departure_arrival_information/Identity'),
        'NATIONALITE_ARRIVEE': _t(r, 'Transport/Means_of_transport/Departure_arrival_information/Nationality'),
        'PLAQUE_FRONTIERE': _t(r, 'Transport/Means_of_transport/Border_information/Identity'),
        'MODE_FRONTIERE': _t(r, 'Transport/Means_of_transport/Border_information/Mode'),
        'MODE_INTERIEUR': _t(r, 'Transport/Means_of_transport/Inland_mode_of_transport'),
        'CODE_LIVRAISON': _t(r, 'Transport/Delivery_terms/Code'), 'LIEU_LIVRAISON': _t(r, 'Transport/Delivery_terms/Place'),
        'CODE_BUREAU_FRONTIERE': _t(r, 'Transport/Border_office/Code'),
        'NOM_BUREAU_FRONTIERE': _t(r, 'Transport/Border_office/Name'),
        'LIEU_MARCHANDISES': _t(r, 'Transport/Location_of_goods'),
        'CODE_BANQUE': _t(r, 'Financial/Bank/Code'), 'NOM_BANQUE': nom_banque(_t(r, 'Financial/Bank/Name')),
        'AGENCE_BANQUE': _t(r, 'Financial/Bank/Branch'),
        'CODE_TERMES': _t(r, 'Financial/Terms/Code'), 'LIBELLE_TERMES': _t(r, 'Financial/Terms/Description'),
        'MODE_PAIEMENT': _t(r, 'Financial/Mode_of_payment'),
        'GARANTIE': montant(_t(r, 'Financial/Guarantee/Amount') or 0),
        'TAXES_GLOBALES': montant(_t(r, 'Financial/Amounts/Global_taxes')),
        'TOTAL_TAXES': montant(_t(r, 'Financial/Amounts/Totals_taxes')),
        'DEVISE': _t(r, 'Valuation/Gs_Invoice/Currency_code'),
        'TOTAL_FACTURE': montant(_t(r, 'Valuation/Total/Total_invoice') or _t(r, 'Valuation/Gs_Invoice/Amount_foreign_currency'), 2),
        'TAUX': montant(_t(r, 'Valuation/Gs_Invoice/Currency_rate'), 4),
    }
    if item is not None:
        unite = item.find('Tarification/Supplementary_unit')
        v.update({
            'DESIGNATION': _t(item, 'Goods_description/Description_of_goods'),
            'NUMERO_LICENCE': licence_courte(_t(item, 'Licence_number')),
            'MARQUES': _t(item, 'Packages/Marks1_of_packages'),
            'NOMBRE_COLIS': montant(_t(item, 'Packages/Number_of_packages'), 2),
            'CODE_COLIS': _t(item, 'Packages/Kind_of_packages_code'), 'NOM_COLIS': _t(item, 'Packages/Kind_of_packages_name'),
            'CODE_SH': _t(item, 'Tarification/HScode/Commodity_code') + _t(item, 'Tarification/HScode/Precision_1'),
            'CODE_ORIGINE': _t(item, 'Goods_description/Country_of_origin_code'),
            'POIDS_BRUT': montant(_t(item, 'Valuation_item/Weight_itm/Gross_weight_itm'), 3),
            'POIDS_NET': montant(_t(item, 'Valuation_item/Weight_itm/Net_weight_itm'), 3),
            'PROCEDURE_ETENDUE': _t(item, 'Tarification/Extended_customs_procedure'),
            'PROCEDURE_NATIONALE': _t(item, 'Tarification/National_customs_procedure'),
            'DOCUMENT_PRECEDENT': _t(item, 'Previous_doc/Summary_declaration'),
            'CODE_UNITE': _t(unite, 'Suppplementary_unit_code'),
            'QUANTITE_UNITE': montant(_t(unite, 'Suppplementary_unit_quantity'), 3),
            'PRIX_ARTICLE': montant(_t(item, 'Tarification/Item_price'), 2),
            'DETAIL_VALEUR': _t(item, 'Tarification/Value_item'),
            'DOCUMENTS_JOINTS': ''.join(dict.fromkeys(d for d in documents if d)),
            'TAUX_AJUSTEMENT': montant(_t(item, 'Valuation_item/Rate_of_adjustement') or 1, 4),
            'VALEUR_STATISTIQUE': montant(_t(item, 'Valuation_item/Statistical_value')),
            'TAXES_ARTICLE': montant(_t(item, 'Taxation/Item_taxes_amount')),
            'TAXE_CODE': [_t(t, 'Duty_tax_code') for t in taxes],
            'TAXE_TAUX': [montant(_t(t, 'Duty_tax_rate'), 4) for t in taxes],
            'TAXE_BASE': [montant(_t(t, 'Duty_tax_Base')) for t in taxes],
            'TAXE_MONTANT': [montant(_t(t, 'Duty_tax_amount')) for t in taxes],
        })
    return v


# ---------------------------------------------------------------------------
# Remplissage du Word
# ---------------------------------------------------------------------------

def remplir(modele, donnees, coupures=None):
    """Octets du .docx rempli. Les balises sans valeur sont vidées ; une balise inconnue est refusée.

    La police et la taille du modèle ne changent jamais : une valeur trop longue pour sa case est coupée,
    et chaque coupure est ajoutée à la liste `coupures` (libellé de la case et texte non affiché)."""
    coupures = [] if coupures is None else coupures
    plans = {}
    try:
        archive = ZipFile(BytesIO(modele))
    except BadZipFile:
        raise ValueError('Le modèle de déclaration doit être un .docx préparé avec les balises.') from None
    with archive:
        doc = minidom.parseString(archive.read('word/document.xml'))
        trouvees = set()
        for p in list(doc.getElementsByTagNameNS(W, 'p')):
            if p.getElementsByTagNameNS(W, 'p'):
                continue  # paragraphe qui contient une zone de texte : ses propres paragraphes sont traités
            contenu = texte(p)
            balises = list(BALISE.finditer(contenu))
            if not balises:
                continue
            liste = next((m.group(1) for m in balises if m.group(1) in LISTES), None)
            if liste:
                lignes = [str(x) for x in donnees.get(liste) or []] or ['']
                cle_plan = ('liste', liste)
                if cle_plan not in plans and liste in TAXES:
                    # Case 47 : les 4 colonnes gardent le même nombre de lignes ; un montant n'est jamais coupé.
                    plans[cle_plan] = lignes[:TAXES_PREVUES]
                    if len(lignes) > TAXES_PREVUES and ('liste', 'taxes') not in plans:
                        plans[('liste', 'taxes')] = True
                        coupures.append(f'case 47 · calcul des impositions : {len(lignes) - TAXES_PREVUES} taxe(s) '
                                        f'au-delà des {TAXES_PREVUES} lignes du formulaire non affichée(s)')
                if cle_plan not in plans:
                    gardees, retire = tenir(p, lignes)
                    plans[cle_plan] = gardees
                    if retire:
                        coupures.append(f"{CASES.get(liste, liste)} : non affiché faute de place « {retire} »")
                lignes = plans[cle_plan] or ['']
                # Ordre conservé : les copies sont insérées après le paragraphe d'origine, dans l'ordre.
                suivant = p.nextSibling
                for ligne in lignes[1:]:
                    copie = p.cloneNode(True)
                    remplacer(copie, 0, len(texte(copie)), ligne)
                    p.parentNode.insertBefore(copie, suivant)
                remplacer(p, 0, len(contenu), lignes[0])
                trouvees.add(liste)
                continue
            for m in reversed(balises):
                cle = m.group(1)
                if cle not in CHAMPS:
                    raise ValueError(f'Champ de déclaration inconnu dans le modèle : {cle}.')
                trouvees.add(cle)
                remplacer(p, m.start(), m.end(), str(donnees.get(cle) or ''))
            # Même texte pour la zone de texte et sa copie de secours (Word ancien) : plan calculé une fois.
            cle_plan = ('texte', contenu)
            rempli = texte(p)
            if cle_plan not in plans:
                garde, retire = couper(p)
                plans[cle_plan] = garde
                if retire:
                    noms = [m.group(1) for m in balises]
                    libelle = next((l for c, l in ESSENTIELS if c in noms), ', '.join(noms))
                    coupures.append(f"{libelle} : non affiché faute de place « {retire} »")
            if plans[cle_plan] < len(rempli):
                remplacer(p, plans[cle_plan], len(rempli), '')  # seule la fin est retirée
        if not {'NUMERO_E', 'DESIGNATION', 'TOTAL_FACTURE'} <= trouvees:
            raise ValueError('Modèle de déclaration non préparé : balises {{NUMERO_E}}, {{DESIGNATION}}, {{TOTAL_FACTURE}} absentes.')
        sortie = BytesIO()
        with ZipFile(sortie, 'w') as cible:
            for info in archive.infolist():
                cible.writestr(info, doc.toxml(encoding='UTF-8') if info.filename == 'word/document.xml'
                               else archive.read(info.filename))
        return sortie.getvalue()


CHAMPS = frozenset({
    'PAYS_TRANSACTION', 'DESIGNATION', 'NUMERO_Q', 'DATE_Q', 'NUMERO_LICENCE', 'NUMERO_E', 'DATE_E', 'TAXES_ARTICLE',
    'TOTAL_TAXES', 'REF_ANNEE', 'REF_SUITE', 'NOM_PAYS_ORIGINE', 'NOM_PAYS_EXPORT', 'CODE_DESTINATAIRE', 'CODE_PAYEUR',
    'PROCEDURE', 'CODE_BUREAU', 'NOM_BUREAU', 'FORMULAIRE', 'TOTAL_FORMULAIRES', 'NOMBRE_ARTICLES', 'TOTAL_COLIS',
    'MANIFESTE', 'CODE_DECLARANT', 'FRAIS', 'CODE_PAYS_EXPORT', 'CODE_DESTINATION', 'NOM_DESTINATION',
    'PLAQUE_ARRIVEE', 'NATIONALITE_ARRIVEE', 'PLAQUE_FRONTIERE', 'CODE_LIVRAISON', 'LIEU_LIVRAISON', 'DEVISE',
    'TOTAL_FACTURE', 'TAUX', 'CODE_BANQUE', 'CODE_TERMES', 'LIBELLE_TERMES', 'NOM_BANQUE', 'AGENCE_BANQUE',
    'MODE_FRONTIERE', 'MODE_INTERIEUR', 'CODE_BUREAU_FRONTIERE', 'NOM_BUREAU_FRONTIERE', 'LIEU_MARCHANDISES',
    'MARQUES', 'NOMBRE_COLIS', 'CODE_COLIS', 'NOM_COLIS', 'CODE_SH', 'CODE_ORIGINE', 'POIDS_BRUT',
    'PROCEDURE_ETENDUE', 'PROCEDURE_NATIONALE', 'POIDS_NET', 'DOCUMENT_PRECEDENT', 'CODE_UNITE', 'QUANTITE_UNITE',
    'PRIX_ARTICLE', 'DETAIL_VALEUR', 'DOCUMENTS_JOINTS', 'TAUX_AJUSTEMENT', 'VALEUR_STATISTIQUE', 'MODE_PAIEMENT',
    'NUMERO_L', 'DATE_L', 'GARANTIE', 'TAXES_GLOBALES', *LISTES})


# ---------------------------------------------------------------------------
# Contrôle du XML SYDONIA (étape 8) et sources de l'étape 9
# ---------------------------------------------------------------------------

# Cases indispensables à la déclaration : (balise, libellé affiché).
ESSENTIELS = (
    ('NUMERO_E', 'N° E (case A)'), ('DATE_E', 'date E (case A)'), ('NUMERO_L', 'N° liquidation (case B)'),
    ('DATE_L', 'date liquidation (case B)'), ('NUMERO_Q', 'N° quittance (case B)'), ('DATE_Q', 'date quittance (case B)'),
    ('EXPORTATEUR', 'exportateur (case 2)'), ('DESTINATAIRE', 'destinataire (case 8)'),
    ('CODE_DESTINATAIRE', 'NIF destinataire (case 8)'), ('DECLARANT', 'déclarant (case 14)'),
    ('CODE_BUREAU', 'bureau (case A)'), ('REF_SUITE', 'référence (case 7)'), ('MANIFESTE', 'manifeste (case 40)'),
    ('PLAQUE_ARRIVEE', 'plaques (case 18)'), ('CODE_PAYS_EXPORT', 'pays de provenance (case 15)'),
    ('DEVISE', 'devise (case 22)'), ('TOTAL_FACTURE', 'montant facture (case 22)'), ('TAUX', 'taux de change (case 23)'),
    ('DESIGNATION', 'désignation (case 31)'), ('NOMBRE_COLIS', 'colis (case 31)'), ('CODE_SH', 'code SH (case 33)'),
    ('CODE_ORIGINE', 'origine (case 34)'), ('POIDS_BRUT', 'poids brut (case 35)'), ('PROCEDURE_ETENDUE', 'régime (case 37)'),
    ('POIDS_NET', 'poids net (case 38)'), ('QUANTITE_UNITE', 'quantité unité suppl. (case 41)'),
    ('PRIX_ARTICLE', 'prix article (case 42)'), ('NUMERO_LICENCE', 'licence (case 44)'),
    ('VALEUR_STATISTIQUE', 'valeur statistique (case 46)'), ('TAXE_CODE', 'calcul des impositions (case 47)'),
    ('TAXES_ARTICLE', 'total taxes article (case 47)'), ('TOTAL_TAXES', 'total général (case 48)'),
)


def _rempli(valeur):
    return any(str(x).strip() for x in valeur) if isinstance(valeur, list) else bool(str(valeur or '').strip())


# Cases qui ne viennent jamais du XML : elles sont prises dans le projet (étape 3 · informations de la part).
CHAMPS_PROJET = ('NUMERO_E', 'DATE_E', 'NUMERO_L', 'DATE_L', 'NUMERO_Q', 'DATE_Q', 'MANIFESTE',
                 'PLAQUE_ARRIVEE', 'PLAQUE_FRONTIERE')
# Position tarifaire (case 33) et désignation (case 31) : celles de l'article du dossier ouvert dans AsyDec
# (premier article de la part, son produit sur la licence), pas celles du XML. Gardées du XML si le dossier n'en a pas.
CHAMPS_ARTICLE = ('CODE_SH', 'DESIGNATION')


def article_part(licence, part):
    """{'CODE_SH', 'DESIGNATION'} du premier article de la part, d'après le dossier AsyDec ; valeurs vides omises."""
    produits = licence.get('produits') or []
    article = next(iter(part.get('articles') or []), None) or {}
    try:
        indice = int(article.get('article') or 1) - 1
    except (TypeError, ValueError):
        indice = 0
    produit = produits[indice] if 0 <= indice < len(produits) else {}
    designation = article.get('designation') or produit.get('designation') or ''
    valeurs = {'CODE_SH': ''.join(str(produit.get('tarif_douanier') or '').split()),
               'DESIGNATION': ' '.join(str(designation).split())}
    return {c: v for c, v in valeurs.items() if v}


def projet_part(licence, numero):
    """E, L, Q, leurs dates, manifeste et plaques de la part, tels que traités à l'étape 3."""
    part = next((p for p in (licence.get('repartition') or {}).get('parts') or [] if p.get('numero') == numero), None)
    if part is None:
        return {}
    infos = part.get('informations_declaration') or licence.get('informations_declaration') or {}
    plaque = part.get('plaque') or infos.get('plaque') or ''
    return {'NUMERO_E': infos.get('numero_e', ''), 'DATE_E': date_dcu(infos.get('date_enregistrement', '')),
            'NUMERO_L': infos.get('numero_liquidation', ''), 'DATE_L': date_dcu(infos.get('date_liquidation', '')),
            'NUMERO_Q': infos.get('numero_quittance', ''), 'DATE_Q': date_dcu(infos.get('date_quittance', '')),
            'MANIFESTE': infos.get('manifeste', ''), 'PLAQUE_ARRIVEE': plaque, 'PLAQUE_FRONTIERE': plaque,
            **article_part(licence, part)}


def completer(sydonia, reference=None, projet=None):
    """Valeurs de la déclaration.

    projet (projet_part) : E, L, Q, dates, manifeste et plaques, toujours pris de l'étape 3, jamais du XML ;
    position tarifaire et désignation de l'article du dossier AsyDec quand il en a.
    Le reste vient du XML SYDONIA ; une case vide y est complétée depuis le XML attendu de la part.
    Renvoie (valeurs, contrôle) ; contrôle = dict(presentes, total, projet, completees, manquantes)
    en libellés des ESSENTIELS."""
    donnees = valeurs(sydonia)
    complement = valeurs(reference) if reference else {}
    projet = projet or {}
    completees = []
    for cle in CHAMPS:
        if cle in CHAMPS_PROJET and projet:
            donnees[cle] = projet.get(cle, '')
        elif cle in CHAMPS_ARTICLE and _rempli(projet.get(cle)):
            donnees[cle] = projet[cle]
        elif not _rempli(donnees.get(cle)) and _rempli(complement.get(cle)):
            donnees[cle] = complement[cle]
            completees.append(cle)
    libelles = dict(ESSENTIELS)
    du_projet = [c for c, _ in ESSENTIELS if (c in CHAMPS_PROJET and projet) or (c in CHAMPS_ARTICLE and _rempli(projet.get(c)))]
    controle = dict(presentes=sum(1 for c, _ in ESSENTIELS if c not in completees and c not in du_projet
                                  and _rempli(donnees.get(c))),
                    total=len(ESSENTIELS),
                    projet=[libelles[c] for c in du_projet if _rempli(donnees.get(c))],
                    completees=[libelles[c] for c, _ in ESSENTIELS if c in completees],
                    manquantes=[libelles[c] + (' (étape 3)' if c in du_projet else '')
                                for c, _ in ESSENTIELS if not _rempli(donnees.get(c))])
    return donnees, controle


def texte_controle(controle):
    """Résumé d'un contrôle pour l'affichage."""
    if controle['manquantes']:
        etat = '✗ manque : ' + ', '.join(controle['manquantes'])
    else:
        etat = '✓ prêt pour la déclaration'
    if controle.get('projet'):
        etat += ' · repris du dossier AsyDec : ' + ', '.join(controle['projet'])
    if controle['completees']:
        etat += ' · complété depuis AsyDec : ' + ', '.join(controle['completees'])
    return etat


def _groupes(licence):
    """{n° de part: [n° des parts de même montant]} : les parts qui partagent un XML à l'étape 7."""
    from asydec.declarations import xml_licence
    try:
        return {n: g['numeros'] for g in xml_licence.groupes_parts(licence) for n in g['numeros']}
    except (KeyError, TypeError, ValueError):
        return {}


def _couverture(licence):
    """{n° de part: (import SYDONIA, n° de la part importée)}. Une part sans XML SYDONIA à elle reprend
    celui d'une part de même montant (même XML à l'étape 7) : seuls E, L, Q, plaques et poids changent."""
    imports = (licence.get('recuperation_simulation') or {}).get('imports') or []
    couverture = {}
    for i in imports:  # XML SYDONIA propres à la part (ou au groupe quand la référence couvre plusieurs parts)
        parts = i.get('parts') or []
        for n in parts:
            if n is not None and n not in couverture:
                couverture[n] = (i, parts[0])
    for n, groupe in _groupes(licence).items():
        if n not in couverture:
            source = next((couverture[m] for m in groupe if m in couverture), None)
            if source:
                couverture[n] = source
    return couverture


def sources(licence):
    """[dict(part, contenu, reference, projet, origine, partage)] : un XML SYDONIA importé à l'étape 8 par part.
    L'étape 9 passe toujours par l'étape 8 ; une part sans XML SYDONIA à elle reprend celui d'une part
    de même montant (partage = n° de cette part)."""
    from asydec.declarations import licences_ouvertes
    imports = (licence.get('recuperation_simulation') or {}).get('imports') or []
    if not imports:
        raise ValueError('Importez d’abord les XML SYDONIA à l’étape 8 : la déclaration est remplie depuis eux.')
    references = {r['parts'][0]: r['contenu'] for r in licences_ouvertes.references_xml(licence) if len(r['parts']) == 1}
    resultat = []
    for n, (i, importee) in _couverture(licence).items():
        partage = importee if importee != n else None
        origine = 'XML SYDONIA ' + Path(i['fichier']).name + (f' (part {importee}, même montant)' if partage else '')
        resultat.append(dict(part=n, contenu=i['contenu'], reference=references.get(n), projet=projet_part(licence, n),
                             origine=origine, partage=partage))
    if not resultat:
        raise ValueError('Aucun XML SYDONIA associé à une part : importez-les à nouveau à l’étape 8.')
    return sorted(resultat, key=lambda s: s['part'])


def parts_sans_sydonia(licence):
    parts = [p['numero'] for p in (licence.get('repartition') or {}).get('parts') or []]
    couvertes = _couverture(licence)
    return [n for n in parts if n not in couvertes]


def propre_a_la_part(sydonia_modele, reference_modele, reference_part):
    """Cases du XML SYDONIA d'une autre part (le modèle) remplacées par celles de la répartition :
    toute case qui diffère entre le XML attendu de la part modèle et celui de cette part (référence
    déclarant, poids, colis…) est propre à la répartition et vient de son XML attendu."""
    if not reference_part:
        return {}
    propres = valeurs(reference_part)
    modele = valeurs(reference_modele) if reference_modele else {}
    return {c: v for c, v in propres.items()
            if c not in CHAMPS_PROJET and c not in CHAMPS_ARTICLE and (not reference_modele or v != modele.get(c)) and _rempli(v)
            and (reference_modele or c in ('POIDS_BRUT', 'POIDS_NET', 'REF_ANNEE', 'REF_SUITE'))}


def generer(licence, modele, progression=None):
    """[dict(part, contenu (octets .docx), origine, articles, controle)] pour chaque répartition couverte par
    un XML SYDONIA (le sien, ou celui d'une part de même montant pris comme modèle), tous préparés avant
    tout enregistrement."""
    from asydec.declarations import taux_declaration
    liste = sources(licence)
    references = {s['part']: s['reference'] for s in liste}
    taux = taux_declaration.du_dossier(licence)
    resultat = []
    if progression:
        progression(0, len(liste))
    for source in liste:
        donnees, controle = completer(source['contenu'], source['reference'], source['projet'])
        if source.get('partage'):
            donnees.update(propre_a_la_part(source['contenu'], references.get(source['partage']), source['reference']))
        if taux is not None:  # taux de l'étape 3 : affichage seulement (case 23), le XML n'est pas modifié
            donnees['TAUX'] = montant(taux, taux_declaration.DECIMALES)
        coupures = []
        contenu = remplir(modele, donnees, coupures)
        resultat.append(dict(part=source['part'], origine=source['origine'], numero_e=donnees.get('NUMERO_E', ''),
                             articles=int(_decimal(donnees.get('NOMBRE_ARTICLES')) or 1), controle=controle,
                             contenu=contenu, donnees=donnees, coupures=coupures))
        if progression:
            progression(len(resultat), len(liste))
    return resultat


def nom_fichier(numero_licence, part):
    return f"{re.sub(r'[^A-Za-z0-9._-]', '-', numero_licence)} - part {part} - declaration.docx"


def fiche(resultats, fichiers, modele):
    return dict(modele=str(modele), genere_le=datetime.now(timezone.utc).isoformat(), version_dates=VERSION_DATES, version_police=VERSION_POLICE,
                fichiers=[dict(part=r['part'], origine=r['origine'], numero_e=r['numero_e'], fichier=str(f),
                               controle=r.get('controle'), coupures=r.get('coupures') or [])
                          for r, f in zip(resultats, fichiers)])


# 2 : dates E, L, Q de l'étape 3 lues jour/mois (avant : 05/11 devenait 11/05 si le jour était ≤ 12).
VERSION_DATES = 2
# 1 : police et taille du modèle jamais modifiées (texte coupé et signalé) ; avant, la police était réduite.
VERSION_POLICE = 2  # 2 : case 44 limitée au numéro DEC


def _dates_ambigues(licence):
    """True si une date E, L ou Q a un jour ≤ 12 différent du mois : écrite à l'envers avant la version 2."""
    for part in (licence.get('repartition') or {}).get('parts') or []:
        for cle in ('date_enregistrement', 'date_liquidation', 'date_quittance'):
            valeur = str((part.get('informations_declaration') or {}).get(cle) or '')
            if re.fullmatch(r'\d{2}/\d{2}/\d{4}', valeur) and int(valeur[:2]) <= 12 and valeur[:2] != valeur[3:5]:
                return True
    return False


def est_a_jour(licence):
    """Déclarations produites depuis les XML actuels (génération étape 7 et import étape 8)."""
    fiche = licence.get('declarations')
    if fiche and (fiche.get('version_dates') or 1) < VERSION_DATES and _dates_ambigues(licence):
        return False
    if fiche and (fiche.get('version_police') or 0) < VERSION_POLICE:
        return False
    return bool(fiche and fiche.get('fichiers')
                and fiche.get('taux') == (licence.get('taux_change') or {}).get('valeur')
                and fiche.get('xml_genere_le') == (licence.get('xml_genere') or {}).get('genere_le')
                and fiche.get('recuperation_le') == (licence.get('recuperation_simulation') or {}).get('importe_le'))
