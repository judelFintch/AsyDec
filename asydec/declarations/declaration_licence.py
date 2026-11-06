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
# Lignes que peut contenir chaque case d'adresse sur le formulaire fourni (au-delà, la case déborderait).
LIGNES_MAX = {'PAYEUR': 5, 'DESTINATAIRE': 4, 'EXPORTATEUR': 2, 'DECLARANT': 3}


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
    """Date SYDONIA m/j/aa -> JJ/MM/AAAA."""
    texte_ = str(valeur or '').strip()
    for format_ in ('%m/%d/%y', '%m/%d/%Y', '%d/%m/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(texte_, format_).strftime('%d/%m/%Y')
        except ValueError:
            pass
    return texte_


def _t(element, chemin):
    noeud = element.find(chemin) if element is not None else None
    return ' '.join((noeud.text or '').split()) if noeud is not None and noeud.text else ''


def _lignes(element, chemin):
    noeud = element.find(chemin)
    if noeud is None or not noeud.text:
        return []
    return [' '.join(l.split()) for l in noeud.text.splitlines() if l.strip()]


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
        'CODE_BANQUE': _t(r, 'Financial/Bank/Code'), 'NOM_BANQUE': _t(r, 'Financial/Bank/Name'),
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
            'NUMERO_LICENCE': _t(item, 'Licence_number'),
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

def remplir(modele, donnees):
    """Octets du .docx rempli. Les balises sans valeur sont vidées ; une balise inconnue est refusée."""
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
                lignes = [str(x) for x in donnees.get(liste) or []][:LIGNES_MAX.get(liste)] or ['']
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
            'MANIFESTE': infos.get('manifeste', ''), 'PLAQUE_ARRIVEE': plaque, 'PLAQUE_FRONTIERE': plaque}


def completer(sydonia, reference=None, projet=None):
    """Valeurs de la déclaration.

    projet (projet_part) : E, L, Q, dates, manifeste et plaques, toujours pris de l'étape 3, jamais du XML.
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
        elif not _rempli(donnees.get(cle)) and _rempli(complement.get(cle)):
            donnees[cle] = complement[cle]
            completees.append(cle)
    libelles = dict(ESSENTIELS)
    du_projet = [c for c, _ in ESSENTIELS if c in CHAMPS_PROJET and projet]
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
        etat += ' · E, L, Q, dates, manifeste et plaques repris de l’étape 3'
    if controle['completees']:
        etat += ' · complété depuis AsyDec : ' + ', '.join(controle['completees'])
    return etat


def sources(licence):
    """[dict(part, contenu, reference, origine)] : un XML SYDONIA importé à l'étape 8 par part.
    L'étape 9 passe toujours par l'étape 8 : une part sans XML SYDONIA n'a pas de déclaration."""
    from asydec.declarations import licences_ouvertes
    imports = (licence.get('recuperation_simulation') or {}).get('imports') or []
    if not imports:
        raise ValueError('Importez d’abord les XML SYDONIA à l’étape 8 : la déclaration est remplie depuis eux.')
    references = {r['parts'][0]: r['contenu'] for r in licences_ouvertes.references_xml(licence) if len(r['parts']) == 1}
    resultat, vues = [], set()
    for i in imports:
        n = (i.get('parts') or [None])[0]
        if n is None or n in vues or len(i.get('parts') or []) != 1:
            continue
        vues.add(n)
        resultat.append(dict(part=n, contenu=i['contenu'], reference=references.get(n), projet=projet_part(licence, n),
                             origine='XML SYDONIA ' + Path(i['fichier']).name))
    if not resultat:
        raise ValueError('Aucun XML SYDONIA associé à une part : importez-les à nouveau à l’étape 8.')
    return sorted(resultat, key=lambda s: s['part'])


def parts_sans_sydonia(licence):
    parts = [p['numero'] for p in (licence.get('repartition') or {}).get('parts') or []]
    importees = {(i.get('parts') or [None])[0] for i in (licence.get('recuperation_simulation') or {}).get('imports') or []}
    return [n for n in parts if n not in importees]


def generer(licence, modele):
    """[dict(part, contenu (octets .docx), origine, articles, controle)] pour les parts qui ont un XML SYDONIA,
    tous préparés avant tout enregistrement."""
    resultat = []
    for source in sources(licence):
        donnees, controle = completer(source['contenu'], source['reference'], source['projet'])
        resultat.append(dict(part=source['part'], origine=source['origine'], numero_e=donnees.get('NUMERO_E', ''),
                             articles=int(_decimal(donnees.get('NOMBRE_ARTICLES')) or 1), controle=controle,
                             contenu=remplir(modele, donnees)))
    return resultat


def nom_fichier(numero_licence, part):
    return f"{re.sub(r'[^A-Za-z0-9._-]', '-', numero_licence)} - part {part} - declaration.docx"


def fiche(resultats, fichiers, modele):
    return dict(modele=str(modele), genere_le=datetime.now(timezone.utc).isoformat(),
                fichiers=[dict(part=r['part'], origine=r['origine'], numero_e=r['numero_e'], fichier=str(f),
                               controle=r.get('controle'))
                          for r, f in zip(resultats, fichiers)])


def est_a_jour(licence):
    """Déclarations produites depuis les XML actuels (génération étape 7 et import étape 8)."""
    fiche = licence.get('declarations')
    return bool(fiche and fiche.get('fichiers')
                and fiche.get('xml_genere_le') == (licence.get('xml_genere') or {}).get('genere_le')
                and fiche.get('recuperation_le') == (licence.get('recuperation_simulation') or {}).get('importe_le'))
