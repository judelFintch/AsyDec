"""Étape 8 : comparaison des XML renvoyés par SYDONIA avec les XML générés à l'étape 7 (un ou plusieurs à la fois)."""
from decimal import Decimal, InvalidOperation
import xml.etree.ElementTree as ET

# Contrôles prioritaires : (libellé, chemin) ; « Item[*] » = chaque article.
CONTROLES = (
    ('FOB (montant facture)', 'Valuation/Gs_Invoice/Amount_foreign_currency'),
    ('Devise', 'Valuation/Gs_Invoice/Currency_code'),
    ('Nombre d’articles', 'Property/Nbers/Total_number_of_items'),
    ('Numéro E', 'Identification/Registration/Number'),
    ('Date E', 'Identification/Registration/Date'),
    ('Numéro liquidation', 'Identification/Assessment/Number'),
    ('Date liquidation', 'Identification/Assessment/Date'),
    ('Numéro Q', 'Identification/receipt/Number'),
    ('Date quittance', 'Identification/receipt/Date'),
    ('Manifeste', 'Identification/Manifest_reference_number'),
    ('Plaques (arrivée)', 'Transport/Means_of_transport/Departure_arrival_information/Identity'),
    ('Plaques (frontière)', 'Transport/Means_of_transport/Border_information/Identity'),
    ('Code importateur', 'Traders/Consignee/Consignee_code'),
    ('Code tarifaire', 'Item[*]/Tarification/HScode/Commodity_code'),
    ('Quantité', 'Item[*]/Tarification/Supplementary_unit/Suppplementary_unit_quantity'),
    ('Valeur article', 'Item[*]/Valuation_item/Item_Invoice/Amount_foreign_currency'),
    ('Numéro licence', 'Item[*]/Licence_number'),
)

LIBELLES = {chemin.replace('Item[*]/', ''): libelle for libelle, chemin in CONTROLES}
LIBELLES.update({
    'General_information/Comments_free_text': 'Commentaire',
    'Valuation/Total/Total_invoice': 'Total facture',
    'Traders/Consignee/Consignee_name': 'Importateur',
    'Traders/Exporter/Exporter_name': 'Exportateur',
    'Goods_description/Description_of_goods': 'Désignation',
    'Tarification/Item_price': 'Prix article',
    'Tarification/HScode/Precision_1': 'Précision tarifaire',
    'Valuation_item/Weight_itm/Gross_weight_itm': 'Poids brut article',
    'Valuation_item/Weight_itm/Net_weight_itm': 'Poids net article',
    'Packages/Number_of_packages': 'Nombre de colis',
})

GENRES = {'modifie': 'Modifié', 'complete': 'Complété par SYDONIA', 'retire': 'Retiré par SYDONIA'}


def _texte(element):
    # SYDONIA écrit souvent <Champ><null/></Champ> pour un champ vide.
    if len(element) and all(enfant.tag == 'null' for enfant in element):
        return ''
    return ' '.join((element.text or '').split())


def aplatir(contenu):
    """{chemin: valeur} pour chaque champ terminal ; les balises répétées sont numérotées Item[1], Item[2]…"""
    if isinstance(contenu, str):
        contenu = contenu.encode('utf-8')
    try:
        racine = ET.fromstring(contenu)
    except ET.ParseError as exc:
        raise ValueError(f'XML illisible : {exc}') from None
    if racine.tag != 'ASYCUDA':
        raise ValueError('Ce fichier n’est pas un XML ASYCUDA / SYDONIA.')
    champs = {}

    def parcourir(element, chemin):
        enfants = [e for e in element if e.tag != 'null']
        if not enfants:
            champs[chemin] = _texte(element)
            return
        rangs = {}
        for enfant in enfants:
            rangs[enfant.tag] = rangs.get(enfant.tag, 0) + 1
            # Première occurrence sans rang (sauf Item) : les contrôles visent toujours le même chemin.
            rang = rangs[enfant.tag]
            nom = f'{enfant.tag}[{rang}]' if enfant.tag == 'Item' or rang > 1 else enfant.tag
            parcourir(enfant, f'{chemin}/{nom}' if chemin else nom)

    parcourir(racine, '')
    return champs


def _egales(a, b):
    if a == b:
        return True
    try:
        return Decimal(a.replace(',', '.')) == Decimal(b.replace(',', '.'))
    except (InvalidOperation, AttributeError):
        return False


def libelle(chemin):
    sans_rang = chemin
    article = ''
    if chemin.startswith('Item['):
        rang, _, sans_rang = chemin.partition('/')
        article = f"Article {rang[5:-1]} · "
    return article + LIBELLES.get(sans_rang, sans_rang.replace('/', ' › '))


def comparer(genere, sydonia):
    """Différences champ par champ, puis contrôles clés."""
    a, b = aplatir(genere), aplatir(sydonia)
    differences = []
    for chemin in sorted(set(a) | set(b), key=lambda c: (not c.startswith('Item'), c)):
        avant, apres = a.get(chemin, ''), b.get(chemin, '')
        if _egales(avant, apres):
            continue
        genre = 'modifie' if avant and apres else ('complete' if apres else 'retire')
        differences.append(dict(chemin=chemin, libelle=libelle(chemin), genere=avant, sydonia=apres, genre=genre))
    controles = []
    nb_articles = max(sum(1 for c in a if c.startswith('Item[') and c.endswith('/Licence_number')),
                      sum(1 for c in b if c.startswith('Item[') and c.endswith('/Licence_number')), 1)
    for titre, chemin in CONTROLES:
        chemins = ([chemin.replace('Item[*]', f'Item[{i}]') for i in range(1, nb_articles + 1)]
                   if 'Item[*]' in chemin else [chemin])
        for c in chemins:
            avant, apres = a.get(c, ''), b.get(c, '')
            if not avant and not apres:
                continue
            controles.append(dict(chemin=c, libelle=libelle(c) if 'Item[' in c else titre,
                                  genere=avant, sydonia=apres, identique=_egales(avant, apres)))
    resume = {genre: sum(1 for d in differences if d['genre'] == genre) for genre in GENRES}
    resume['controles_differents'] = sum(1 for c in controles if not c['identique'])
    return dict(differences=differences, controles=controles, resume=resume)


def conclusion(resume):
    if resume['controles_differents']:
        return f"{resume['controles_differents']} contrôle(s) clé(s) différent(s) : à vérifier."
    if resume['modifie'] or resume['retire']:
        return 'Contrôles clés identiques · d’autres champs ont été modifiés ou retirés.'
    if resume['complete']:
        return 'Aucun changement sur les données générées · SYDONIA a seulement complété des champs.'
    return 'Aucun changement : le XML SYDONIA est identique au XML généré.'


def _cout(comparaison):
    r = comparaison['resume']
    return (r['controles_differents'], r['modifie'] + r['retire'])


def associer(references, sydonias):
    """Chaque XML SYDONIA comparé à la référence (XML attendu d'une part) qui lui ressemble le plus.

    references : [dict(parts, contenu, ...)] ; sydonias : [(fichier, contenu)].
    Renvoie [dict(fichier, contenu, reference, comparaison)] dans l'ordre des fichiers ;
    ValueError si aucune référence."""
    if not references:
        raise ValueError('Générez d’abord le XML à l’étape 7.')
    resultat = []
    for fichier, contenu in sydonias:
        meilleur = None
        for reference in references:
            comparaison = comparer(reference['contenu'], contenu)
            if meilleur is None or _cout(comparaison) < _cout(meilleur[1]):
                meilleur = (reference, comparaison)
        resultat.append(dict(fichier=fichier, contenu=contenu, reference=meilleur[0], comparaison=meilleur[1]))
    return resultat


def resume_global(resumes):
    """Somme des résumés de plusieurs comparaisons."""
    total = {genre: 0 for genre in GENRES}
    total['controles_differents'] = 0
    for resume in resumes:
        for cle in total:
            total[cle] += resume.get(cle, 0)
    return total
