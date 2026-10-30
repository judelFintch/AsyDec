"""Gestion dynamique des articles : catalogue des articles connus et composition d'une base.

Un article est reconnu par sa position tarifaire et sa désignation normalisée. Il emporte
tout ce qui lui est propre dans le XML : position tarifaire, procédures, origine, désignation,
lignes de taxes (taux), ratio FOB/kg de référence, bornes observées et rôle (ajustable ou borné).

Le catalogue se nourrit des XML classiques à huit articles. Une composition peut ensuite changer,
retirer ou ajouter des articles : chacun garde son ratio et son rôle, et les articles ajustables
absorbent l'écart de FOB comme dans le modèle à huit. Le XML du dossier n'est jamais modifié.
"""
import copy
import hashlib
import statistics
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from asydec.calcul import moteur

NOMBRE_ARTICLES = 8
# Parties d'un Item propres à l'article ; colis, marques et valeurs restent ceux du dossier.
PARTIES_ARTICLE = ('Tarification/HScode', 'Tarification/Extended_customs_procedure',
                   'Tarification/National_customs_procedure', 'Goods_description', 'Taxation')


def normaliser(texte):
    """Casse, accents et espaces ignorés : « Couvre-Lits » et « couvre-lits » se valent."""
    sans_accents = unicodedata.normalize('NFKD', texte or '').encode('ascii', 'ignore').decode()
    return ' '.join(sans_accents.casefold().split())


def _mots(texte):
    """Pour la recherche : la ponctuation compte comme un espace (« couvre lits » trouve « couvre-lits »)."""
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in normaliser(texte)).split())


def cle_item(item):
    return (moteur._txt(item, 'Tarification/HScode/Commodity_code'),
            normaliser(moteur._txt(item, 'Goods_description/Description_of_goods')))


def _taxes(item):
    return {moteur._txt(t, 'Duty_tax_code'): moteur._fl(moteur._txt(t, 'Duty_tax_rate'))
            for t in item.findall('Taxation/Taxation_line') if moteur._txt(t, 'Duty_tax_code')}


# --------------------------------------------------------------------------
# Catalogue
# --------------------------------------------------------------------------
def construire_catalogue(chemins, nombre=NOMBRE_ARTICLES):
    """Articles des XML, sans doublon de contenu ; les XML illisibles sont ignorés.

    nombre : ne retenir que les XML de ce nombre d'articles (8 pour la friperie), ou None pour tous (Divers).
    Un article est ajustable s'il a occupé une ligne ajustable (4, 7 ou 8) d'un XML classique à huit articles.
    """
    entrees, empreintes = {}, set()
    for chemin in chemins:
        try:
            contenu = Path(chemin).read_bytes()
            empreinte = hashlib.sha256(contenu).hexdigest()
            if empreinte in empreintes:
                continue
            empreintes.add(empreinte)
            items = moteur.articles(moteur.charger(chemin).getroot())
        except Exception:  # noqa: BLE001 - un XML illisible n'empêche pas les autres
            continue
        if nombre is not None and len(items) != nombre:
            continue
        classique = len(items) == NOMBRE_ARTICLES and nombre is not None
        for position, item in enumerate(items):
            poids = moteur._fl(moteur._txt(item, 'Valuation_item/Weight_itm/Gross_weight_itm'))
            fob = moteur._fl(moteur._txt(item, 'Tarification/Item_price'))
            if poids <= 0 or fob <= 0:
                continue
            cle = cle_item(item)
            entree = entrees.setdefault(cle, {
                'cle': cle, 'code': cle[0],
                'designation': moteur._txt(item, 'Goods_description/Description_of_goods'),
                'origine': moteur._txt(item, 'Goods_description/Country_of_origin_code'),
                'taxes': _taxes(item), 'ratios': [], 'positions': set(), 'source': (str(chemin), position)})
            entree['ratios'].append(fob / poids)
            entree['positions'].add(position)
            entree['ajustable'] = entree.get('ajustable', False) or (classique and position in moteur.ARTICLES_VARIABLES)
    for entree in entrees.values():
        entree['ratio_min'], entree['ratio_max'] = min(entree['ratios']), max(entree['ratios'])
        entree['ratio'] = statistics.median(entree['ratios'])
    return dict(sorted(entrees.items(), key=lambda e: (min(e[1]['positions']), e[0])))


def libelle(entree):
    return f"{entree['code']} · {entree['designation']}"


def resume(entree):
    """« ajustable · ratio 0,36 – 0,45 · DDI 5 % · 66 XML » : ce que l'article apporte à la génération."""
    role = 'ajustable' if entree['ajustable'] else 'borné'
    ddi = entree['taxes'].get('DDI')
    taxe = f" · DDI {ddi:g} %" if ddi is not None else ''
    return (f"{role} · ratio {entree['ratio_min']:.4g} – {entree['ratio_max']:.4g}{taxe}"
            f" · {len(entree['ratios'])} XML")


def rechercher(catalogue, texte):
    """Articles dont la position tarifaire ou le nom contient le texte saisi (casse et accents ignorés)."""
    cherche = _mots(texte)
    chiffres = cherche.replace(' ', '')
    return [e for e in catalogue.values()
            if not cherche or (chiffres.isdigit() and chiffres in e['code']) or cherche in _mots(e['designation'])]


def articles_du_xml(chemin):
    """Clés des articles d'un XML, dans l'ordre des lignes."""
    return [cle_item(item) for item in moteur.articles(moteur.charger(chemin).getroot())]


# --------------------------------------------------------------------------
# Composition
# --------------------------------------------------------------------------
def _remplacer(cible, source, chemin):
    parent_chemin, _, nom = chemin.rpartition('/')
    parent = cible.find(parent_chemin) if parent_chemin else cible
    ancien, nouveau = parent.find(nom), source.find(chemin)
    if nouveau is None:
        return
    if ancien is None:
        parent.append(copy.deepcopy(nouveau))
    else:
        parent.insert(list(parent).index(ancien), copy.deepcopy(nouveau))
        parent.remove(ancien)


def _nouvel_item(modele, source, entree):
    """Ligne pour un article absent du dossier : cadre du dossier, parties et poids de l'article."""
    item = copy.deepcopy(modele)
    for partie in PARTIES_ARTICLE:
        _remplacer(item, source, partie)
    for chemin in ('Valuation_item/Weight_itm/Gross_weight_itm', 'Valuation_item/Weight_itm/Net_weight_itm',
                   'Packages/Number_of_packages'):
        if item.find(chemin) is not None and source.find(chemin) is not None:
            item.find(chemin).text = source.find(chemin).text
    poids = Decimal(moteur._txt(item, 'Valuation_item/Weight_itm/Gross_weight_itm'))
    fob = (poids * Decimal(str(entree['ratio']))).quantize(Decimal('0.01'), ROUND_HALF_UP)
    moteur._ecrire(item, 'Tarification/Item_price', moteur._nombre(float(fob)))
    return item


def composer(base, cles, catalogue, dossier, exiger_ajustable=True):
    """Copie du XML du dossier avec les articles choisis, dans l'ordre choisi, plus ou moins nombreux.

    Un article déjà présent garde sa ligne du dossier (poids, FOB, colis). Un article ajouté prend
    les parties qui lui sont propres (position, procédures, origine, désignation, taxes) et son poids
    dans le XML où il a été vu, avec un FOB au ratio médian de l'article. Renvoie le chemin du XML
    du dossier si rien ne change, sinon celui de la base composée. exiger_ajustable : friperie (au moins
    un article ajustable équilibre le FOB) ; Divers n'en a pas, chaque article garde son ratio.
    """
    arbre = moteur.charger(base)
    racine = arbre.getroot()
    items = moteur.articles(racine)
    if not cles:
        raise ValueError("Gardez au moins un article.")
    inconnus = [k + 1 for k, cle in enumerate(cles) if cle not in catalogue]
    if inconnus:
        raise ValueError(f"Ligne(s) {', '.join(map(str, inconnus))} : article absent du catalogue. "
                         "Choisissez-le par sa position tarifaire ou son nom dans la liste.")
    doublons = sorted({libelle(catalogue[c]) for c in cles if cles.count(c) > 1})
    if doublons:
        raise ValueError('Un article ne peut occuper qu\'une ligne : ' + ' ; '.join(doublons))
    if exiger_ajustable and not any(catalogue[c]['ajustable'] for c in cles):
        raise ValueError("Gardez au moins un article ajustable (par exemple moustiquaires, articles de pêche "
                         "ou de ménage) : c'est lui qui équilibre le FOB total.")
    if [cle_item(it) for it in items] == list(cles):
        return str(base)
    du_dossier = {cle_item(it): it for it in items}
    sources, lignes = {}, []
    for cle in cles:
        if cle in du_dossier:
            lignes.append(du_dossier[cle])
            continue
        chemin, position = catalogue[cle]['source']
        if chemin not in sources:
            sources[chemin] = moteur.articles(moteur.charger(chemin).getroot())
        lignes.append(_nouvel_item(items[0], sources[chemin][position], catalogue[cle]))
    # Les lignes d'articles sont remplacées à leur place ; les Item vides du XML restent après.
    rang = list(racine).index(items[0])
    for item in items:
        racine.remove(item)
    for decalage, item in enumerate(lignes):
        racine.insert(rang + decalage, item)
    nombre = racine.find('Property/Nbers/Total_number_of_items')
    if nombre is not None:
        nombre.text = str(len(lignes))
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    empreinte = hashlib.sha256(Path(base).read_bytes() + repr(list(cles)).encode()).hexdigest()[:12]
    destination = dossier / f"{Path(base).stem} - articles {empreinte}.xml"
    if not destination.exists():
        moteur.enregistrer(arbre, destination)
    return str(destination)
