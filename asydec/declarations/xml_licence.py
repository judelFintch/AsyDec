"""Préremplissage ASYCUDA depuis une licence, avant les calculs du dossier complet."""
import copy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import re
import os
import tempfile
import xml.etree.ElementTree as ET

from asydec.calcul import moteur
from asydec.declarations import mise_a_jour_repartitions
from asydec.declarations.dates_documents import exiger_ouvrable
from asydec.declarations.informations_declaration import lire_date
from asydec.declarations.informations_declaration import CHAMPS, verifier

AVERTISSEMENT = ('XML de préparation à compléter : poids, colis, codes pays et unités, transport, '
                 'frais, taux de change, régime et taxes restent à renseigner ou à vérifier. '
                 'Aucun calcul de taxes ni validation SYDONIA n’a été effectué.')


def nombre(valeur, libelle):
    try:
        resultat = Decimal(str(valeur).replace(' ', '').replace(',', '.'))
    except InvalidOperation:
        raise ValueError(f'{libelle} : nombre invalide.') from None
    if not resultat.is_finite() or resultat <= 0:
        raise ValueError(f'{libelle} : nombre strictement positif requis.')
    return resultat


def ecrire(racine, chemin, valeur):
    element = racine.find(chemin)
    if element is None:
        raise ValueError(f'Le modèle XML ne contient pas le champ {chemin}.')
    moteur._ecrire(racine, chemin, str(valeur))


def bloc(partie):
    return '\n'.join(str(partie.get(cle, '')).strip() for cle in
                     ('nom', 'adresse', 'telephone', 'email', 'fax', 'identifiants')
                     if str(partie.get(cle, '')).strip())


def _controler(licence):
    """Contrôles communs aux deux générations ; renvoie (numéro licence, DEC, lignes, FOB total).
    lignes : [(produit, quantité, prix, valeur, devise)]."""
    numero = str(licence.get('numero_validation', '')).strip()
    dec = str(licence.get('numero_dec', '')).strip()
    if not numero or not dec:
        raise ValueError('Numéro licence et numéro DEC requis.')
    for cle, libelle in [('date_validation', 'La date de validation'), ('date_bl', 'La date du BL')]:
        if licence.get(cle):
            exiger_ouvrable(lire_date(licence[cle]), libelle)
    produits = licence.get('produits') or []
    attendu = licence.get('nombre_produits_attendu')
    if not produits or (attendu is not None and len(produits) != attendu):
        raise ValueError('Complétez la liste des produits avant de générer le XML.')
    for partie in ('soussigne', 'fournisseur'):
        if not licence.get(partie, {}).get('nom', '').strip():
            raise ValueError('Renseignez le nom du soussigné et du fournisseur étranger.')
    lignes = []
    for i, produit in enumerate(produits, 1):
        code = produit.get('tarif_douanier', '').strip()
        if not re.fullmatch(r'\d{10}', code):
            raise ValueError(f'Article {i} : tarif douanier de 10 chiffres requis.')
        if not produit.get('designation', '').strip():
            raise ValueError(f'Article {i} : désignation requise.')
        q = nombre(produit.get('quantite'), f'Article {i}, quantité')
        pu = nombre(produit.get('prix_unitaire'), f'Article {i}, prix unitaire')
        devise = produit.get('devise', '').strip().upper()
        if not re.fullmatch(r'[A-Z]{3}', devise):
            raise ValueError(f'Article {i} : devise de trois lettres requise.')
        # Valeur de l'article dans la part (répartition) si connue : elle seule garantit total = FOB de la part.
        montant = (nombre(produit['valeur'], f'Article {i}, valeur') if produit.get('valeur')
                   else (q * pu).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
        lignes.append((produit, q, pu, montant, devise))
    devises = {l[4] for l in lignes}
    if len(devises) != 1:
        raise ValueError('Tous les articles doivent avoir la même devise pour ce XML.')
    total = nombre(licence.get('montant_fob'), 'Montant FOB')
    if sum(l[3] for l in lignes) != total.quantize(Decimal('.01')):
        raise ValueError('La somme quantité × prix unitaire des articles ne correspond pas au FOB de la licence.')
    return numero, dec, lignes, total


def preparer(licence, modele):
    """Modèle de la bibliothèque : XML de préparation (structure gardée, aucune donnée de l'ancien dossier).
    Base de licence (dossier XML_LICENCES) : XML complet, voir preparer_complet."""
    if est_base_licence(modele):
        return preparer_complet(licence, modele)
    numero, dec, lignes, total = _controler(licence)
    produits = licence.get('produits') or []
    arbre = moteur.charger(modele)
    racine = arbre.getroot()
    if racine.tag != 'ASYCUDA' or racine.find('Item') is None:
        raise ValueError('Choisissez un modèle XML ASYCUDA contenant un article.')
    # Éviter toute fuite d'identités, références, taxes ou numéros du modèle choisi.
    for element in racine.iter():
        if not len(element):
            element.text = None
        element.attrib.clear()
    anciens = racine.findall('Item')
    emplacement = list(racine).index(anciens[0])
    gabarit = copy.deepcopy(anciens[0])
    for ancien in anciens:
        racine.remove(ancien)
    for i, (produit, q, pu, montant, devise) in enumerate(lignes):
        item = copy.deepcopy(gabarit)
        code = produit['tarif_douanier'].strip()
        valeurs = {'Tarification/HScode/Commodity_code': code[:8],
                   'Tarification/HScode/Precision_1': code[8:],
                   'Tarification/Item_price': format(montant, 'f'),
                   'Goods_description/Description_of_goods': produit['designation'],
                   'Goods_description/Commercial_Description': produit['designation'],
                   'Licence_number': numero,
                   'Valuation_item/Item_Invoice/Amount_foreign_currency': format(montant, 'f'),
                   'Valuation_item/Item_Invoice/Currency_code': devise}
        for chemin, valeur in valeurs.items():
            ecrire(item, chemin, valeur)
        unites = item.findall('Tarification/Supplementary_unit')
        if unites:
            ecrire(unites[0], 'Suppplementary_unit_name', produit.get('unite', ''))
            ecrire(unites[0], 'Suppplementary_unit_quantity', format(q, 'f'))
        pays = produit.get('pays_origine', '').strip()
        if re.fullmatch(r'[A-Z]{2}', pays):
            ecrire(item, 'Goods_description/Country_of_origin_code', pays)
        # Conserver les libellés de la licence même si leur code douanier reste à compléter.
        ecrire(item, 'Free_text_1', f"Origine licence : {pays} ; unité : {produit.get('unite', '')} ; quantité : {q} ; prix unitaire : {pu} {devise}")
        racine.insert(emplacement + i, item)
    ecrire(racine, 'Property/Nbers/Total_number_of_items', len(produits))
    ecrire(racine, 'Valuation/Gs_Invoice/Currency_code', lignes[0][4])
    ecrire(racine, 'Valuation/Gs_Invoice/Amount_foreign_currency', format(total, 'f'))
    ecrire(racine, 'Valuation/Total/Total_invoice', format(total, 'f'))
    if racine.find('Financial/Total_invoice') is not None:
        ecrire(racine, 'Financial/Total_invoice', format(total, 'f'))
    identifiants = licence['soussigne'].get('identifiants', '')
    nif = re.search(r'imp[oô]t\s*:\s*([A-Z0-9-]+)', identifiants, re.I)
    moteur.ecrire_importateur(racine, nif[1] if nif else '', bloc(licence['soussigne']))
    ecrire(racine, 'Traders/Exporter/Exporter_name', bloc(licence['fournisseur']))
    informations = licence.get('informations_declaration')
    if informations:
        informations = verifier(informations)
        for cle, _, chemin in CHAMPS:
            if chemin and informations.get(cle) and cle != 'plaque':
                valeur = informations[cle]
                if cle in ('date_declaration', 'date_enregistrement', 'date_liquidation', 'date_quittance'):
                    valeur = datetime.strptime(valeur, '%d/%m/%Y').strftime('%m/%d/%y')
                ecrire(racine, chemin, valeur)
        # Plaque de la part : champs Identity d'arrivée et de frontière, comme les XML réels.
        if informations.get('plaque') and any(racine.find(c) is not None for c in moteur.CHEMINS_PLAQUE):
            moteur.ecrire_plaque(racine, informations['plaque'])
    ecrire(racine, 'General_information/Comments_free_text', _commentaire(licence, AVERTISSEMENT + '\n'))
    return arbre


# ---------------------------------------------------------------------------
# XML complet à partir d'une vraie déclaration de licence (dossier XML_LICENCES)
# ---------------------------------------------------------------------------

def bases_licence():
    """Vraies déclarations SYDONIA de licence servant de base, la plus récente d'abord."""
    from asydec import chemins
    dossier = Path(chemins.XML_LICENCES)
    if not dossier.is_dir():
        return []
    return sorted(dossier.glob('*.xml'), key=lambda c: c.stat().st_mtime, reverse=True)


def ajouter_base_licence(chemin):
    """Copie une vraie déclaration SYDONIA de licence dans XML_LICENCES (base des XML complets) ; renvoie la copie."""
    import shutil
    from asydec import chemins
    source = Path(chemin)
    try:
        racine = ET.parse(source).getroot()
    except (ET.ParseError, OSError) as exc:
        raise ValueError(f'XML illisible : {exc}') from None
    if racine.tag != 'ASYCUDA' or racine.find('Item') is None or racine.find('Valuation/Gs_Invoice/Currency_rate') is None:
        raise ValueError('Choisissez une vraie déclaration SYDONIA (ASYCUDA) avec au moins un article et un taux de change.')
    dossier = Path(chemins.XML_LICENCES)
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / source.name
    if cible.resolve() != source.resolve():
        n = 2
        while cible.exists():
            cible = dossier / f'{source.stem} ({n}){source.suffix}'
            n += 1
        shutil.copy2(source, cible)
    return cible


def est_base_licence(chemin):
    from asydec import chemins
    try:
        return Path(chemin).resolve().parent == Path(chemins.XML_LICENCES).resolve()
    except OSError:
        return False


PAYS = {  # pays d'origine de la licence -> (code ISO, nom SYDONIA)
    'india': ('IN', 'Inde'), 'inde': ('IN', 'Inde'), 'china': ('CN', 'Chine'), 'chine': ('CN', 'Chine'),
    'united arab emirates': ('AE', 'Emirats arabes unis'), 'emirats arabes unis': ('AE', 'Emirats arabes unis'),
    'uae': ('AE', 'Emirats arabes unis'), 'tanzania': ('TZ', 'Tanzanie, République-unie de'),
    'tanzanie': ('TZ', 'Tanzanie, République-unie de'), 'zambia': ('ZM', 'Zambie'), 'zambie': ('ZM', 'Zambie'),
    'south africa': ('ZA', 'Afrique du Sud'), 'afrique du sud': ('ZA', 'Afrique du Sud'), 'kenya': ('KE', 'Kenya'),
    'japan': ('JP', 'Japon'), 'japon': ('JP', 'Japon'), 'thailand': ('TH', 'Thaïlande'), 'thailande': ('TH', 'Thaïlande'),
    'indonesia': ('ID', 'Indonésie'), 'indonesie': ('ID', 'Indonésie'), 'vietnam': ('VN', 'Viet Nam'),
    'viet nam': ('VN', 'Viet Nam'), 'malaysia': ('MY', 'Malaisie'), 'malaisie': ('MY', 'Malaisie'),
    'pakistan': ('PK', 'Pakistan'), 'turkey': ('TR', 'Turquie'), 'turquie': ('TR', 'Turquie'),
    'korea': ('KR', 'Corée, République de'), 'south korea': ('KR', 'Corée, République de'),
    'united states': ('US', 'Etats-Unis'), 'usa': ('US', 'Etats-Unis'), 'germany': ('DE', 'Allemagne'),
    'allemagne': ('DE', 'Allemagne'), 'france': ('FR', 'France'), 'italy': ('IT', 'Italie'), 'italie': ('IT', 'Italie'),
    'belgium': ('BE', 'Belgique'), 'belgique': ('BE', 'Belgique'), 'netherlands': ('NL', 'Pays-Bas'),
    'united kingdom': ('GB', 'Royaume-Uni'), 'royaume-uni': ('GB', 'Royaume-Uni'),
}


def pays(valeur):
    """(code, nom) du pays d'origine de la licence ; (None, None) si inconnu."""
    texte = ' '.join(str(valeur or '').split())
    if re.fullmatch(r'[A-Za-z]{2}', texte):
        code = texte.upper()
        return code, next((n for c, n in PAYS.values() if c == code), None)
    return PAYS.get(texte.casefold(), (None, None))


def _unite(unite):
    """Unité supplémentaire SYDONIA (code, nom) ; None pour le kilogramme (déjà donné par le poids)."""
    texte = str(unite or '').casefold()
    if 'kilo' in texte or texte in ('kg', 'kgs'):
        return None
    if 'paire' in texte or 'pair' in texte:
        return 'PR', 'Paire'
    return 'UNT', 'Unité'


def _vider(element):
    """Champ sans valeur (forme SYDONIA <champ><null/></champ>)."""
    if element is None:
        return
    for enfant in list(element):
        element.remove(enfant)
    element.text = None
    ET.SubElement(element, 'null')


def _date_xml(valeur):
    """Date au format SYDONIA des documents joints (ex. 2/1/24)."""
    jour = lire_date(valeur)
    return f'{jour.month}/{jour.day}/{jour:%y}'


def colis(quantite, unite, poids):
    """Colis d'un article : une par pièce (arrondie au-dessus), sinon un colis par 50 kg."""
    import math
    if _unite(unite) is None:
        return max(1, round(float(poids) / 50))
    return max(1, math.ceil(float(quantite)))


def preparer_complet(licence, base):
    """XML complet d'une part depuis une vraie déclaration de licence.

    Gardés de la base : bureau, déclarant, type et procédure, pays de destination, transport (modes, lieu),
    banque, conditions de paiement, documents joints, nature des colis, taux de change, fret, assurance
    et taux des taxes. Remplacés : importateur, exportateur, articles (code SH, désignation, origine,
    unité, quantité, licence, colis, poids), FOB, E/L/Q, manifeste, plaques, référence et facture (FCM).
    Valeurs, CIF, montants en CDF et taxes sont recalculés par le moteur des XML friperie."""
    numero, dec, lignes, total = _controler(licence)
    arbre = moteur.charger(base)
    racine = arbre.getroot()
    if racine.tag != 'ASYCUDA' or racine.find('Item') is None:
        raise ValueError('La base de licence doit être un XML ASYCUDA contenant un article.')
    cif0 = moteur._fl(moteur._txt(racine, 'Valuation/Total_CIF'))
    globales0 = moteur._fl(moteur._txt(racine, 'Financial/Amounts/Global_taxes'))
    taux_globales = globales0 / cif0 if cif0 > 0 else None

    # Données propres à l'ancien dossier : effacées avant d'écrire celles de la part.
    for chemin in ('Identification/Manifest_reference_number', 'Identification/Registration/Number',
                   'Identification/Registration/Date', 'Identification/Assessment/Number', 'Identification/Assessment/Date',
                   'Identification/receipt/Number', 'Identification/receipt/Date', 'Declarant/Reference/Number',
                   'General_information/Comments_free_text', 'Traders/Exporter/Exporter_code',
                   *moteur.CHEMINS_PLAQUE):
        element = racine.find(chemin)
        if element is not None:
            if element.tag in ('Date',):
                for enfant in list(element):
                    element.remove(enfant)
                element.text = None
            else:
                _vider(element)

    poids = list(licence.get('poids_articles') or [])
    if len(poids) != len(lignes):
        raise ValueError('Poids des articles de la part inconnus : refaites la répartition.')
    facture = licence.get('facture_part') or {}
    anciens = racine.findall('Item')
    emplacement = list(racine).index(anciens[0])
    gabarit = copy.deepcopy(anciens[0])
    for ancien in anciens:
        racine.remove(ancien)
    nombres_colis = []
    for i, (produit, q, pu, montant, devise) in enumerate(lignes):
        item = copy.deepcopy(gabarit)
        code = produit['tarif_douanier'].strip()
        designation = ' '.join(str(produit['designation']).split())
        ecrire(item, 'Tarification/HScode/Commodity_code', code[:8])
        ecrire(item, 'Tarification/HScode/Precision_1', code[8:])
        ecrire(item, 'Goods_description/Description_of_goods', designation)
        ecrire(item, 'Goods_description/Commercial_Description', designation)
        code_pays, _ = pays(produit.get('pays_origine'))
        if code_pays:
            ecrire(item, 'Goods_description/Country_of_origin_code', code_pays)
        ecrire(item, 'Licence_number', numero)
        ecrire(item, 'Valuation_item/Item_Invoice/Currency_code', devise)
        unites = item.findall('Tarification/Supplementary_unit')
        unite = _unite(produit.get('unite'))
        if unites and unite:
            moteur._ecrire(unites[0], 'Suppplementary_unit_code', unite[0])
            moteur._ecrire(unites[0], 'Suppplementary_unit_name', unite[1])
            moteur._ecrire(unites[0], 'Suppplementary_unit_quantity', format(q.normalize(), 'f'))
        ecrire(item, 'Free_text_1', f"Quantité licence : {q} {produit.get('unite', '')} ; prix unitaire : {pu} {devise}")
        nombres_colis.append(colis(q, produit.get('unite'), poids[i]))
        # Documents joints : facture de la part ; références propres à l'ancien dossier effacées.
        for document in item.findall('Attached_documents'):
            genre = document.findtext('Attached_document_code') or ''
            reference = document.find('Attached_document_reference')
            date_document = document.find('Attached_document_date')
            if genre == 'FCM' and facture.get('numero'):
                moteur._ecrire(document, 'Attached_document_reference', facture['numero'])
                if date_document is not None and facture.get('date'):
                    date_document.text = _date_xml(facture['date'])
            elif genre in ('CAA', 'FRI'):
                _vider(reference)
                if date_document is not None:
                    date_document.text = None
            elif genre == 'TTR' and date_document is not None and licence.get('date_bl'):
                date_document.text = _date_xml(licence['date_bl'])
        racine.insert(emplacement + i, item)

    # En-tête : nombre d'articles et de formulaires (1 article sur le premier, 3 par suite).
    n = len(lignes)
    ecrire(racine, 'Property/Nbers/Total_number_of_items', n)
    if racine.find('Property/Forms/Total_number_of_forms') is not None:
        ecrire(racine, 'Property/Forms/Total_number_of_forms', 1 + -(-(n - 1) // 3))
    code_pays, nom_pays = pays(lignes[0][0].get('pays_origine'))
    if code_pays:
        for chemin, valeur in (('General_information/Country/Export/Export_country_code', code_pays),
                               ('General_information/Country/Export/Export_country_name', nom_pays),
                               ('General_information/Country/Country_of_origin_name', nom_pays)):
            if valeur and racine.find(chemin) is not None:
                ecrire(racine, chemin, valeur)
    ecrire(racine, 'Valuation/Gs_Invoice/Currency_code', lignes[0][4])
    identifiants = licence['soussigne'].get('identifiants', '')
    nif = re.search(r'imp[oô]t\s*:\s*([A-Z0-9-]+)', identifiants, re.I)
    moteur.ecrire_importateur(racine, nif[1] if nif else '', bloc(licence['soussigne']))
    ecrire(racine, 'Traders/Exporter/Exporter_name', bloc(licence['fournisseur']))

    informations = licence.get('informations_declaration')
    if informations:
        informations = verifier(informations)
        for cle, _, chemin in CHAMPS:
            if chemin and informations.get(cle) and cle != 'plaque' and racine.find(chemin) is not None:
                valeur = informations[cle]
                if cle in ('date_declaration', 'date_enregistrement', 'date_liquidation', 'date_quittance'):
                    valeur = datetime.strptime(valeur, '%d/%m/%Y').strftime('%m/%d/%y')
                ecrire(racine, chemin, valeur)
        if informations.get('plaque'):
            moteur.ecrire_plaque(racine, informations['plaque'])
            if not informations.get('reference') and informations.get('date_enregistrement'):
                reference = moteur.reference_dossier(informations['plaque'], lire_date(informations['date_enregistrement']))
                if reference:
                    moteur.ecrire_reference(racine, reference)

    # Valeur, fret et assurance répartis, CIF, montants en CDF et taxes : moteur des XML friperie.
    moteur.recalculer(arbre, [(float(montant), float(p)) for (_, _, _, montant, _), p in zip(lignes, poids)],
                      colis=nombres_colis, taux_globales=taux_globales)
    ecrire(racine, 'General_information/Comments_free_text', _commentaire(licence))
    return arbre


def _commentaire(licence, entete=''):
    numero = str(licence.get('numero_validation', '')).strip()
    dec = str(licence.get('numero_dec', '')).strip()
    informations = licence.get('informations_declaration')
    commentaire = f'{entete}Numéro licence : {numero}\nNuméro DEC : {dec}'
    for cle, titre in [('date_validation', 'Validation licence'), ('date_bl', 'Date BL calculée')]:
        valeur = licence.get(cle)
        if valeur:
            if isinstance(valeur, date):
                valeur = valeur.strftime('%d/%m/%Y')
            else:
                try:
                    valeur = date.fromisoformat(valeur).strftime('%d/%m/%Y')
                except ValueError:
                    pass
            commentaire += f'\n{titre} : {valeur}'
    part = licence.get('part_generee')
    if part:
        commentaire += (f"\nPart {part['numero']} sur {part['total']} · FOB part : {part['fob']} "
                        f"(licence : {part['fob_licence']}) · Poids part : {part['poids_kg']} kg")
        if len(part.get('identiques') or []) > 1:
            commentaire += '\nMême montant et mêmes quantités pour les parts : ' + ', '.join(map(str, part['identiques']))
        if part.get('conteneur'):
            commentaire += f"\nConteneur : {part['conteneur']} · Scellé : {part['scelle']}"
    if informations:
        if informations.get('numero_bl'):
            commentaire += '\nNuméro BL : ' + informations['numero_bl']
        if informations.get('observations'):
            commentaire += '\nObservations : ' + informations['observations']
    return commentaire


def _parts(licence):
    parts = (licence.get('repartition') or {}).get('parts') or []
    if not parts:
        raise ValueError('Validez la répartition avant la génération XML.')
    return parts


def _signature(part):
    """Montant et articles d'une part : deux parts de même signature donnent le même XML (hors numéros)."""
    return (str(Decimal(str(part['fob']))),
            tuple((str(Decimal(str(a['quantite']))), str(Decimal(str(a['valeur'])))) for a in part.get('articles') or []))


def groupes_parts(licence):
    """Parts regroupées par montant et articles identiques, dans l'ordre des parts :
    [dict(part=première part du groupe, numeros=[n° des parts identiques])]. Un XML par groupe."""
    groupes = {}
    for part in _parts(licence):
        groupes.setdefault(_signature(part), dict(part=part, numeros=[]))['numeros'].append(part['numero'])
    return list(groupes.values())


def vue_part(licence, part, identiques=None):
    """Vue de la licence limitée à une part : FOB, quantités des articles, plaques, E/L/Q et manifeste de la part.
    identiques : numéros des parts de même montant couvertes par ce XML (commentaire)."""
    parts = _parts(licence)
    articles = part.get('articles') or []
    produits = licence.get('produits') or []
    if len(articles) != len(produits):
        raise ValueError(f"Les quantités de la part {part['numero']} ne sont pas calculées : refaites la répartition.")
    vue = copy.deepcopy(licence)
    vue['montant_fob'] = part['fob']
    vue['produits'] = [dict(produit, quantite=article['quantite'], valeur=article['valeur'],
                            prix_unitaire=article.get('prix_unitaire') or produit.get('prix_unitaire'))
                       for produit, article in zip(produits, articles)]
    vue['nombre_produits_attendu'] = len(produits)
    if part.get('informations_declaration'):
        vue['informations_declaration'] = copy.deepcopy(part['informations_declaration'])
    from asydec.declarations import facture_licence
    # Poids de chaque article : même répartition que la packing list de la part.
    vue['poids_articles'] = facture_licence.repartir_poids([a['quantite'] for a in articles], part.get('poids_kg') or 0) \
        if part.get('poids_kg') else []
    try:
        numero_facture, date_facture = facture_licence.references_facture(licence)
        vue['facture_part'] = dict(numero=facture_licence.numero_part(numero_facture, part), date=date_facture)
    except ValueError:
        vue['facture_part'] = {}
    vue['part_generee'] = dict(numero=part['numero'], total=len(parts), fob=part['fob'], poids_kg=part.get('poids_kg'),
                               conteneur=part.get('conteneur', ''), scelle=part.get('scelle', ''),
                               fob_licence=licence.get('montant_fob'),
                               identiques=list(identiques or [part['numero']]))
    return vue


def premiere_part(licence):
    """Vue de la licence limitée à la part 1 : celle qui porte les informations saisies."""
    groupe = groupes_parts(licence)[0]
    return vue_part(licence, groupe['part'], groupe['numeros'])


def libelle_parts(numeros):
    return f"part {numeros[0]}" if len(numeros) == 1 else 'parts ' + '-'.join(str(n) for n in numeros)


def candidats_modele(licence):
    """XML ASYCUDA pouvant servir de structure, le plus pertinent d'abord :
    dernier modèle utilisé pour la licence, modèles locaux, puis XML validés du dossier de travail."""
    from asydec import chemins
    from asydec.systeme import espace_travail
    vus, sortie = set(), []

    def ajouter(chemin):
        chemin = Path(chemin)
        cle = str(chemin.resolve()) if chemin.exists() else None
        if cle and cle not in vus and chemin.suffix.lower() == '.xml':
            vus.add(cle)
            sortie.append(chemin)

    if licence.get('modele_structure'):
        ajouter(licence['modele_structure'])
    if Path(chemins.MODELES_XML).is_dir():
        for chemin in sorted(Path(chemins.MODELES_XML).glob('*.xml'), key=lambda c: c.stat().st_mtime, reverse=True):
            ajouter(chemin)
    racine = espace_travail.racine()
    if racine is not None:
        for module in (espace_travail.FRIPERIE, espace_travail.DIVERS):
            dossier = racine / module
            if dossier.is_dir():
                valides = dossier.glob(f"*/{espace_travail.RANGEMENT['valides']}/*.xml")
                for chemin in sorted(valides, key=lambda c: c.stat().st_mtime, reverse=True):
                    ajouter(chemin)
    return sortie


def vues_a_generer(licence):
    """Une vue par groupe de parts au montant différent (les parts identiques ne sont générées qu'une fois)."""
    return [vue_part(licence, g['part'], g['numeros']) for g in groupes_parts(licence)]


def proposer_modele(licence, limite=40):
    """Premier modèle avec lequel les XML de toutes les parts différentes se préparent sans erreur ; None sinon.
    Les vraies déclarations de licence (XML complet) passent avant les modèles de structure (XML de préparation)."""
    vues = vues_a_generer(licence)
    for chemin in bases_licence() + candidats_modele(licence)[:limite]:
        try:
            for vue in vues:
                preparer(vue, chemin)
        except (ValueError, OSError, ET.ParseError):
            continue
        return chemin
    return None


def apercu(licence, vue=None):
    """Ce qui sera écrit dans le XML d'une part (par défaut la part 1) : [(libellé, valeur)]."""
    vue = vue or premiere_part(licence)
    part = vue['part_generee']
    infos = vue.get('informations_declaration') or {}
    lignes = [('Part générée', f"Part {part['numero']} sur {part['total']}"
               + (f" (identique aux parts {', '.join(map(str, part['identiques'][1:]))})" if len(part['identiques']) > 1 else '')),
              ('FOB de la part', f"{part['fob']} USD (licence : {part['fob_licence']} USD)"),
              ('Poids de la part (commentaire)', f"{part['poids_kg']} kg"),
              ('Articles', f"{len(vue['produits'])} article(s)"),
              ('Numéro DEC', vue.get('numero_dec', '')),
              ('Numéro licence', vue.get('numero_validation', ''))]
    for cle, titre in (('numero_e', 'Numéro E'), ('date_enregistrement', 'Date E'),
                       ('numero_liquidation', 'Numéro liquidation'), ('date_liquidation', 'Date liquidation'),
                       ('numero_quittance', 'Numéro Q'), ('date_quittance', 'Date quittance'), ('date_cvi', 'Date CVI'),
                       ('manifeste', 'Manifeste'), ('plaque', 'Plaques')):
        if infos.get(cle):
            lignes.append((titre, infos[cle]))
    if part.get('conteneur'):
        lignes.append(('Conteneur · scellé (commentaire)', f"{part['conteneur']} · {part['scelle']}"))
    return lignes, vue['produits']


def exporter(licence, modele, destination, vue=None):
    """vue : part à exporter (vue_part) ; par défaut la part 1."""
    mise_a_jour_repartitions.exiger_numeros(licence.get('informations_declaration', {}))
    if not mise_a_jour_repartitions.est_a_jour(licence):
        raise ValueError('Validez la mise à jour des répartitions avant la génération XML.')
    destination = Path(destination)
    if destination.suffix.lower() != '.xml':
        raise ValueError('Choisissez un fichier .xml.')
    if destination.resolve() == Path(modele).resolve():
        raise ValueError('Le XML de référence ne doit pas être remplacé.')
    arbre = preparer(vue or premiere_part(licence), modele)
    # Même sérialisation que le générateur existant, publication sans écrasement.
    temporaire = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.asydec-', suffix='.xml', dir=destination.parent, delete=False) as fichier:
            temporaire = Path(fichier.name)
        moteur.enregistrer(arbre, temporaire)
        os.link(temporaire, destination)
    finally:
        if temporaire is not None:
            temporaire.unlink(missing_ok=True)
    return destination
