"""Composition Friperie avec un nombre choisi d'articles et des variantes XML explicites."""
import copy
import hashlib
import math
from pathlib import Path
import random
import xml.etree.ElementTree as ET

from asydec.calcul import articles, moteur


def catalogue(chemins):
    """Une entrée par variante et source : aucun ratio médian ni fusion de taxes."""
    sortie, vus = {}, set()
    for chemin in chemins:
        contenu = Path(chemin).read_bytes()
        sha = hashlib.sha256(contenu).hexdigest()
        if sha in vus:
            continue
        vus.add(sha)
        racine = ET.fromstring(contenu)
        for rang, item in enumerate(moteur.articles(racine)):
            p = moteur._fl(moteur._txt(item, 'Valuation_item/Weight_itm/Gross_weight_itm'))
            f = moteur._fl(moteur._txt(item, 'Tarification/Item_price'))
            if not all(math.isfinite(v) and v > 0 for v in (p, f)):
                continue
            identifiant = f'{sha}:{rang}'
            sortie[identifiant] = dict(id=identifiant, article=articles.cle_item(item),
                code=moteur._txt(item, 'Tarification/HScode/Commodity_code'),
                designation=moteur._txt(item, 'Goods_description/Description_of_goods'),
                ratio=f/p, taxes=articles._taxes(item), source=str(chemin), rang=rang+1,
                devise=moteur._txt(racine, 'Valuation/Gs_Invoice/Currency_code'),
                item=ET.tostring(item, encoding='utf-8'))
    return sortie


def verifier(selection, nombre):
    if isinstance(nombre, bool) or int(nombre) != nombre or nombre < 1:
        raise ValueError('Choisissez un nombre entier d’articles supérieur à zéro.')
    if len(selection) != nombre:
        raise ValueError(f'Sélectionnez exactement {nombre} articles ({len(selection)} sélectionnés).')
    if len({e['article'] for e in selection}) != len(selection):
        raise ValueError('Choisissez une seule variante par article.')


def choisir_automatiquement(entrees, nombre, graine=None):
    if isinstance(nombre, bool) or int(nombre) != nombre or nombre < 1:
        raise ValueError('Choisissez un nombre entier d’articles supérieur à zéro.')
    groupes = {}
    for e in entrees.values():
        groupes.setdefault(e['article'], []).append(e)
    if nombre > len(groupes):
        raise ValueError(f'Le catalogue ne contient que {len(groupes)} articles distincts ; ajoutez des XML Friperie.')
    rng = random.Random(graine)
    return [rng.choice(groupes[cle]) for cle in rng.sample(list(groupes), nombre)]


def composer(base, selection, nombre, dossier):
    verifier(selection, nombre)
    arbre = moteur.charger(base)
    r = arbre.getroot()
    devise = moteur._txt(r, 'Valuation/Gs_Invoice/Currency_code')
    if any(e['devise'] != devise for e in selection):
        raise ValueError('Les articles doivent utiliser la même devise que le dossier.')
    anciens = r.findall('Item')
    if not anciens:
        raise ValueError('Le dossier doit contenir au moins un article.')
    rang = list(r).index(anciens[0])
    for it in anciens:
        r.remove(it)
    for k, entree in enumerate(selection):
        r.insert(rang+k, ET.fromstring(entree['item']))
    compteur = r.find('Property/Nbers/Total_number_of_items')
    if compteur is not None:
        compteur.text = str(nombre)
    info = moteur.infos_dossier(r)
    moteur.recalculer(arbre, list(zip(info['fob_articles'], info['poids_articles'])), info['colis_articles'])
    contenu = ET.tostring(r, encoding='utf-8', xml_declaration=True)
    destination = Path(dossier)/f'Composition {hashlib.sha256(contenu).hexdigest()[:16]}.xml'
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        moteur.enregistrer(arbre, destination)
    return str(destination)
