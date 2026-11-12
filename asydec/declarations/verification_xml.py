"""XML de vérification (étape 8) produits par AsyDec, sans passer par SYDONIA.

Quand le XML SYDONIA d'une part n'est pas disponible, AsyDec part du XML attendu de la part (étape 7)
et refait ce que la simulation SYDONIA change d'habitude : tous les montants en francs congolais
(valeurs, fret, assurance, CIF, bases et montants des taxes, totaux) sont recalculés au taux de change
retenu à l'étape 3. Les montants en dollars, les articles, les numéros E, L, Q et le manifeste ne
changent pas.

Ces fichiers ne sont jamais des déclarations réelles : ils portent une marque (commentaire et nom de
fichier) qui les exclut de la détection des déclarations réelles et des propositions de numéros ou de taux.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
import xml.etree.ElementTree as ET

MARQUE = 'AsyDec : XML de vérification généré sans SYDONIA - pas une déclaration réelle'
SUFFIXE = 'verification AsyDec'

# Montants en francs congolais, proportionnels au taux de change.
MONTANTS_CDF = ('Amount_national_currency', 'Total_CIF', 'Total_cost', 'Total_CIF_itm', 'Total_cost_itm',
                'Statistical_value', 'Duty_tax_Base', 'Duty_tax_amount', 'Item_taxes_amount', 'Global_taxes',
                'Totals_taxes', 'Value_details')


def est_verification(contenu):
    """True pour un XML de vérification AsyDec (texte ou octets)."""
    if isinstance(contenu, bytes):
        return MARQUE.encode('utf-8') in contenu
    return MARQUE in str(contenu or '')


def nom_fichier(numero_licence, libelle):
    return f"{re.sub(r'[^A-Za-z0-9._-]', '-', numero_licence)} - {libelle} - {SUFFIXE}.xml"


def _decimal(texte):
    try:
        valeur = Decimal(str(texte).replace(',', '').strip())
    except (InvalidOperation, ValueError):
        return None
    return valeur if valeur.is_finite() else None


def _format(valeur, modele):
    """Même nombre de décimales que la valeur d'origine."""
    decimales = len(modele.split('.', 1)[1]) if '.' in modele and 'E' not in modele.upper() else 0
    return format(valeur.quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP), 'f')


def simuler(reference, taux=None):
    """XML de vérification (texte) à partir du XML attendu d'une part ; taux = CDF pour 1 USD (ou None)."""
    racine = ET.fromstring(reference)
    anciens = [_decimal(e.text) for e in racine.iter('Currency_rate') if _decimal(e.text)]
    ancien = anciens[0] if anciens else None
    if taux and ancien and Decimal(str(taux)) != ancien:
        rapport = Decimal(str(taux)) / ancien
        for element in racine.iter():
            if element.tag == 'Currency_rate' and _decimal(element.text):
                element.text = format(Decimal(str(taux)).normalize(), 'f')
            elif element.tag in MONTANTS_CDF and element.text and _decimal(element.text) is not None:
                element.text = _format(_decimal(element.text) * rapport, element.text.strip())
            elif element.tag == 'Value_item' and element.text:
                # « 11,311,600+0+226,232+0-0 » : fret, frais, assurance… en CDF.
                element.text = re.sub(r'[\d,]+(?:\.\d+)?', lambda m: f'{(_decimal(m.group()) * rapport).quantize(Decimal(1), rounding=ROUND_HALF_UP):,}',
                                      element.text)
        # Total des taxes d'un article = somme de ses lignes (évite les écarts d'arrondi).
        for item in racine.iter('Item'):
            montants = [_decimal(l.findtext('Duty_tax_amount')) for l in item.iter('Taxation_line')]
            total = item.find('Taxation/Item_taxes_amount')
            if total is not None and montants and all(m is not None for m in montants):
                total.text = _format(sum(montants, Decimal(0)), total.text or '0')
        # Total général = taxes des articles + taxes globales.
        articles = [_decimal(t.text) for t in racine.iter('Item_taxes_amount')]
        globales = racine.find('Financial/Amounts/Global_taxes')
        general = racine.find('Financial/Amounts/Totals_taxes')
        if general is not None and globales is not None and _decimal(globales.text) is not None \
                and articles and all(a is not None for a in articles):
            general.text = _format(sum(articles, Decimal(0)) + _decimal(globales.text), general.text or '0')
    texte = ET.tostring(racine, encoding='unicode')
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<!-- {MARQUE} -->\n{texte}\n'


def a_completer(references, imports):
    """Références (XML attendus) dont aucune part n'est couverte par un XML importé."""
    couvertes = {n for i in imports for n in (i.get('parts') or [])}
    return [r for r in references if not set(r['parts']) & couvertes]
