"""Éléments déjà saisis sur les licences ouvertes, réutilisables sur une autre licence.

Importateurs (soussigné), fournisseurs et articles sont proposés sans doublon, les plus
récents d'abord, avec les licences où ils apparaissent. Les valeurs sont toujours copiées :
modifier la licence cible ne change pas la licence d'origine.
"""
from copy import deepcopy
import json


def _licences(fichier=None, exclure=None):
    """(numéro, contenu) des licences ouvertes, puis des licences supprimées (archivées).

    Les licences supprimées restent une source : leurs soussignés, fournisseurs et articles
    ne disparaissent jamais. `exclure` ne vise que la licence ouverte de ce numéro.
    """
    from asydec.declarations import licences_ouvertes
    with licences_ouvertes.connexion(fichier) as conn:
        ouvertes = conn.execute('SELECT numero, contenu FROM licences ORDER BY modifie_le DESC, numero').fetchall()
        supprimees = conn.execute('SELECT numero, contenu FROM licences_supprimees ORDER BY supprime_le DESC, id DESC').fetchall()
    return ([(l['numero'], json.loads(l['contenu'])) for l in ouvertes if not (exclure and l['numero'] == exclure)]
            + [(l['numero'], json.loads(l['contenu'])) for l in supprimees])


def parties_existantes(fichier=None, exclure=None):
    """(importateurs, fournisseurs) : listes de dict(libelle, coordonnees, licences)."""
    resultat = {'soussigne': [], 'fournisseur': []}
    for numero, licence in _licences(fichier, exclure):
        for partie, liste in resultat.items():
            coordonnees = {k: v for k, v in (licence.get(partie) or {}).items() if str(v or '').strip()}
            if not coordonnees.get('nom'):
                continue
            existant = next((s for s in liste if s['coordonnees'] == coordonnees), None)
            if existant:
                existant['licences'].append(numero)
            else:
                liste.append(dict(coordonnees=coordonnees, licences=[numero]))
    for liste in resultat.values():
        # Fiches les plus complètes d'abord (adresse, identifiants…), puis les plus récentes.
        liste.sort(key=lambda source: -len(source['coordonnees']))
        for source in liste:
            autres = len(source['licences']) - 1
            source['libelle'] = (f"{source['coordonnees']['nom']} · licence {source['licences'][0]}"
                                 + (f' (+{autres})' if autres else ''))
    return resultat['soussigne'], resultat['fournisseur']


def _cle_article(article):
    """Identité d'un article, quantité exclue : même article sur deux licences = une proposition."""
    return tuple(' '.join(str(article.get(c, '')).split()).casefold()
                 for c in ('tarif_douanier', 'designation', 'pays_origine', 'unite', 'prix_unitaire', 'devise'))


def articles_existants(fichier=None, exclure=None):
    """Articles des licences ouvertes : liste de dict(article, licences), sans doublon."""
    resultat, index = [], {}
    for numero, licence in _licences(fichier, exclure):
        for article in licence.get('produits') or []:
            if not str(article.get('designation', '')).strip():
                continue
            cle = _cle_article(article)
            if cle in index:
                if numero not in index[cle]['licences']:
                    index[cle]['licences'].append(numero)
                continue
            index[cle] = dict(article=deepcopy(article), licences=[numero])
            resultat.append(index[cle])
    return resultat


def articles_declarations(dossier=None, connus=()):
    """Articles des vraies déclarations SYDONIA du dossier XML_LICENCES : liste de dict(article, licences).

    Code SH (10 chiffres), désignation, origine, unité, quantité et prix unitaire (valeur ÷ quantité) quand
    la déclaration les donne. connus : articles déjà proposés (articles_existants), pour éviter les doublons."""
    import xml.etree.ElementTree as ET
    from decimal import Decimal, ROUND_HALF_UP
    from pathlib import Path
    from asydec import chemins
    dossier = Path(dossier or chemins.XML_LICENCES)
    if not dossier.is_dir():
        return []
    vus = {_cle_article(c['article'])[:3] for c in connus}
    resultat, index = [], {}
    for chemin in sorted(dossier.glob('*.xml'), key=lambda c: c.stat().st_mtime, reverse=True):
        try:
            racine = ET.parse(chemin).getroot()
        except (ET.ParseError, OSError):
            continue
        for item in racine.findall('Item'):
            texte = lambda c: ' '.join((item.findtext(c) or '').split())
            code = texte('Tarification/HScode/Commodity_code') + (texte('Tarification/HScode/Precision_1') or '00')
            designation = texte('Goods_description/Description_of_goods') or texte('Goods_description/Commercial_Description')
            if not designation or len(code) != 10 or not code.isdigit():
                continue
            quantite = _decimal(texte('Tarification/Supplementary_unit/Suppplementary_unit_quantity'))
            valeur = _decimal(texte('Valuation_item/Item_Invoice/Amount_foreign_currency') or texte('Tarification/Item_price'))
            prix = (valeur / quantite).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) if quantite and valeur and quantite > 0 else None
            article = dict(tarif_douanier=code, designation=designation,
                           pays_origine=texte('Goods_description/Country_of_origin_code'),
                           unite=texte('Tarification/Supplementary_unit/Suppplementary_unit_name'),
                           quantite=format(quantite.normalize(), 'f') if quantite else '',
                           prix_unitaire=format(prix, 'f') if prix is not None else '',
                           devise=texte('Valuation_item/Item_Invoice/Currency_code') or 'USD')
            cle = _cle_article(article)
            source = f'XML {chemin.stem}'
            if cle[:3] in vus:
                continue
            if cle in index:
                if source not in index[cle]['licences']:
                    index[cle]['licences'].append(source)
                continue
            index[cle] = dict(article=article, licences=[source])
            resultat.append(index[cle])
    return resultat


def copier_article(article, garder_quantite=False):
    """Copie d'un article pour une autre licence ; quantité vidée sauf demande contraire."""
    copie = deepcopy(article)
    if not garder_quantite:
        copie['quantite'] = ''
    return copie


# ---------------------------------------------------------------------------
# Reprise automatique du client et du fournisseur
# ---------------------------------------------------------------------------

FORMES_SOCIALES = {'ste', 'ets', 'sarl', 'sa', 'sas', 'sprl', 'sarlu', 'societe', 'etablissement', 'etablissements',
                   'ltd', 'limited', 'llc', 'fze', 'fzc', 'fzco', 'co', 'company', 'cie', 'et', 'the', 'de', 'des', 'du',
                   'la', 'le'}


def cle_nom(nom):
    """Nom réduit pour rapprocher les écritures d'une même société.

    « STE KATANGA T.V.S. SARL » et « ETS KATANGA TVS (CLT1064118) » donnent tous deux « katanga tvs ».
    """
    import re
    import unicodedata
    texte = ''.join(c for c in unicodedata.normalize('NFD', str(nom or '')) if not unicodedata.combining(c)).lower()
    texte = re.sub(r'\([^)]*\)', ' ', texte)                   # codes client entre parenthèses
    texte = re.sub(r'\b([a-z])\.(?=[a-z]\.?)', r'\1', texte)  # T.V.S. → TVS
    texte = re.sub(r'[^a-z0-9]+', ' ', texte)
    return ' '.join(m for m in texte.split() if m not in FORMES_SOCIALES)


def _remplies(coordonnees):
    return {k: v for k, v in (coordonnees or {}).items() if str(v or '').strip()}


def completer_parties(soussigne, fournisseur, fichier=None, exclure=None):
    """Complète automatiquement le client et le fournisseur d'une licence.

    - Client : si une licence ouverte a le même client (nom rapproché) avec une fiche plus complète
      (adresse, identifiants…), cette fiche est reprise entièrement.
    - Fournisseur : s'il est vide, celui de la licence la plus récente de ce client est repris.
    Renvoie dict(soussigne, fournisseur, source_soussigne, source_fournisseur) ; source_* = numéro
    de la licence d'origine, ou None si rien n'a été repris.
    """
    soussigne, fournisseur = deepcopy(soussigne or {}), deepcopy(fournisseur or {})
    resultat = dict(soussigne=soussigne, fournisseur=fournisseur, source_soussigne=None, source_fournisseur=None)
    cle = cle_nom(soussigne.get('nom'))
    if not cle:
        return resultat
    meilleure, fournisseur_trouve = None, None
    for numero, licence in _licences(fichier, exclure):   # les plus récentes d'abord
        client = _remplies(licence.get('soussigne'))
        if cle_nom(client.get('nom')) != cle:
            continue
        if meilleure is None or len(client) > len(meilleure[1]):
            meilleure = (numero, client)
        autre = _remplies(licence.get('fournisseur'))
        if fournisseur_trouve is None and autre.get('nom'):
            fournisseur_trouve = (numero, autre)
    if meilleure and len(meilleure[1]) > len(_remplies(soussigne)):
        resultat['soussigne'], resultat['source_soussigne'] = deepcopy(meilleure[1]), meilleure[0]
    if fournisseur_trouve and not _remplies(fournisseur).get('nom'):
        resultat['fournisseur'], resultat['source_fournisseur'] = deepcopy(fournisseur_trouve[1]), fournisseur_trouve[0]
    return resultat


# ---------------------------------------------------------------------------
# Quantités calculées pour atteindre le FOB de la licence
# ---------------------------------------------------------------------------

def _decimal(valeur):
    from decimal import Decimal, InvalidOperation
    try:
        d = Decimal(str(valeur).replace(' ', '').replace(' ', '').replace(' ', '').replace(',', '.'))
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def poids_origine(articles):
    """Valeurs d'origine (quantité × prix) servant de proportions, ou None si incomplètes."""
    valeurs = []
    for a in articles:
        q, p = _decimal(a.get('quantite')), _decimal(a.get('prix_unitaire'))
        if q is None or p is None or q <= 0 or p <= 0:
            return None
        valeurs.append(q * p)
    return valeurs


def repartir_quantites(articles, total, poids=None):
    """Quantités des articles pour que la somme des valeurs (quantité × prix, arrondie au centime)
    soit exactement le FOB `total`.

    poids : part de chaque article dans le total (ex. valeurs sur la licence d'origine) ;
    à défaut, parts égales. Les quantités sont entières quand c'est possible ; l'article le
    moins cher sert d'appoint avec 3 décimales pour tomber juste au centime.
    Renvoie (articles avec quantités, écart) ; écart = FOB − total obtenu (0 si exact).
    """
    from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
    if not articles:
        raise ValueError('Ajoutez au moins un article avant de calculer les quantités.')
    cible = _decimal(total)
    if cible is None or cible <= 0:
        raise ValueError('Renseignez d’abord le montant FOB de la licence (onglet Licence).')
    cible = cible.quantize(Decimal('.01'))
    prix = [_decimal(a.get('prix_unitaire')) for a in articles]
    sans_prix = [str(a.get('designation', '')).split('\n')[0] for a, p in zip(articles, prix) if not p or p <= 0]
    if sans_prix:
        raise ValueError('Prix unitaire manquant ou nul pour : ' + ', '.join(sans_prix[:5]))
    poids = [(_decimal(p) or Decimal(0)) for p in poids] if poids else []
    if len(poids) != len(articles) or sum(poids) <= 0 or any(p < 0 for p in poids):
        poids = [Decimal(1)] * len(articles)
    somme_poids = sum(poids)
    centime, millieme = Decimal('.01'), Decimal('.001')

    def valeur(q, p):
        return (q * p).quantize(centime, rounding=ROUND_HALF_UP)

    def quantite(montant, p):
        brut = montant / p
        q = brut.to_integral_value(rounding=ROUND_FLOOR)
        return q if q >= 1 else brut.quantize(millieme, rounding=ROUND_FLOOR)

    quantites = [quantite(cible * w / somme_poids, p) for w, p in zip(poids, prix)]
    appoint = min(range(len(articles)), key=lambda i: prix[i])  # le plus petit prix ajuste le plus finement

    def ajuster(qs):
        """Quantité d'appoint qui complète au plus près ; renvoie (quantités, écart) ou None."""
        reste = cible - sum(valeur(q, p) for i, (q, p) in enumerate(zip(qs, prix)) if i != appoint)
        if reste <= 0:
            return None
        base = (reste / prix[appoint]).quantize(millieme)
        meilleur = None
        for k in range(-3, 4):
            q = base + k * millieme
            if q <= 0:
                continue
            ecart = reste - valeur(q, prix[appoint])
            if meilleur is None or abs(ecart) < abs(meilleur[1]):
                meilleur = (q, ecart)
        if meilleur is None:
            return None
        nouvelles = list(qs)
        nouvelles[appoint] = meilleur[0]
        return nouvelles, meilleur[1]

    resultat = ajuster(quantites)
    if resultat is None:
        raise ValueError('Montant FOB trop faible pour ces articles : retirez des articles ou vérifiez les prix.')
    # Appoint inexact (prix élevés) : déplacer quelques unités d'un autre article jusqu'à tomber juste.
    if resultat[1] != 0:
        for i in (i for i in range(len(articles)) if i != appoint):
            entier = resultat[0][i] == resultat[0][i].to_integral_value() and resultat[0][i] >= 1
            unite = Decimal(1) if entier else millieme
            for pas in range(1, 400):
                for signe in (1, -1):
                    essai = list(resultat[0])
                    essai[i] += signe * pas * unite
                    if essai[i] <= 0:
                        continue
                    tentative = ajuster(essai)
                    if tentative and abs(tentative[1]) < abs(resultat[1]):
                        resultat = tentative
                    if resultat[1] == 0:
                        break
                if resultat[1] == 0:
                    break
            if resultat[1] == 0:
                break
    quantites, ecart = resultat
    prix_appoint = None
    if ecart != 0:
        # Prix trop élevé pour tomber juste en jouant sur la quantité seule (ex. 702 USD : pas de 0,702 USD) :
        # prix unitaire de l'appoint ajusté de quelques centimes, au plus près du prix d'origine.
        reste = cible - sum(valeur(q, p) for i, (q, p) in enumerate(zip(quantites, prix)) if i != appoint)
        for k in range(1, 1001):
            for signe in (-1, 1):
                p = prix[appoint] + signe * k * centime
                if p <= 0:
                    continue
                base = (reste / p).quantize(millieme)
                q = next((base + d * millieme for d in (0, -1, 1) if base + d * millieme > 0
                          and valeur(base + d * millieme, p) == reste), None)
                if q is not None:
                    prix_appoint, quantites[appoint], ecart = p, q, Decimal(0)
                    break
            if prix_appoint is not None:
                break
    copies = []
    for i, (article, q) in enumerate(zip(articles, quantites)):
        copie = deepcopy(article)
        copie['quantite'] = format(q, '.3f')
        if i == appoint and prix_appoint is not None:
            copie['prix_unitaire'] = format(prix_appoint, '.2f')
        copies.append(copie)
    return copies, ecart


# ---------------------------------------------------------------------------
# Articles proposés automatiquement pour une licence qui n'a qu'un FOB
# ---------------------------------------------------------------------------

def modeles_articles(fichier=None, exclure=None):
    """Licences dont les articles servent de modèle : liste de dict(numero, client, fob, articles, valeurs).

    Seuls les articles complets (désignation, prix et quantité positifs) comptent ; un même article
    répété sur une licence est fusionné (valeurs additionnées).
    """
    modeles, vus = [], set()
    for numero, licence in _licences(fichier, exclure):
        index, articles, valeurs = {}, [], []
        for article in licence.get('produits') or []:
            if not str(article.get('designation', '')).strip():
                continue
            valeur = poids_origine([article])
            if not valeur:
                continue
            cle = _cle_article(article)
            if cle in index:
                valeurs[index[cle]] += valeur[0]
                continue
            index[cle] = len(articles)
            articles.append(deepcopy(article))
            valeurs.append(valeur[0])
        signature = (numero, tuple(sorted(index)))   # licence recommencée : déjà vue ouverte ou archivée
        if articles and signature not in vus:
            vus.add(signature)
            modeles.append(dict(numero=numero, client=cle_nom((licence.get('soussigne') or {}).get('nom')),
                                fob=sum(valeurs), articles=articles, valeurs=valeurs))
    return modeles


def _tirer_sans_remise(hasard, elements, poids, nombre):
    """`nombre` éléments distincts, chacun tiré avec une probabilité proportionnelle à son poids."""
    restants = list(zip(elements, poids))
    choisis = []
    while restants and len(choisis) < nombre:
        total = sum(p for _, p in restants)
        seuil, cumul = hasard.uniform(0, total), 0.0
        for i, (element, p) in enumerate(restants):
            cumul += p
            if cumul >= seuil:
                break
        choisis.append(element)
        del restants[i]
    return choisis


QUANTITE_MINIMALE = 10   # un article proposé doit pouvoir compter au moins 10 unités / kg


def _proposition(modele, cible, hasard):
    """Articles et proportions tirés d'un modèle, ou None si le modèle ne convient pas au FOB."""
    n = len(modele['articles'])
    indices = list(range(n))
    if n == 1:
        retenus = indices
    else:
        rapport = float(cible / modele['fob'])
        # Nombre d'articles : au hasard entre la moitié et la totalité du modèle,
        # moins d'articles quand le FOB est nettement plus petit que celui du modèle.
        haut = n if rapport >= 1 else max(2, round(n * rapport ** 0.5))
        bas = min(haut, max(2, (n + 1) // 2))
        nombre = hasard.randint(bas, haut)
        while True:
            # Les articles qui pèsent le plus sur la licence modèle ont plus de chances d'être repris.
            retenus = sorted(_tirer_sans_remise(hasard, indices, [float(v) for v in modele['valeurs']], nombre))
            # Chaque article doit pouvoir compter au moins QUANTITE_MINIMALE unités avec une part moyenne.
            part = cible / nombre
            if all(part >= _decimal(modele['articles'][i]['prix_unitaire']) * QUANTITE_MINIMALE for i in retenus) or nombre <= 2:
                break
            nombre -= 1
    from decimal import Decimal
    # Proportions d'origine, variées de ±30 % pour que deux propositions ne se ressemblent pas.
    poids = [modele['valeurs'][i] * Decimal(str(round(hasard.uniform(0.7, 1.3), 3))) for i in retenus]
    articles = [copier_article(modele['articles'][i]) for i in retenus]
    if any(cible * p / sum(poids) < _decimal(a['prix_unitaire']) for a, p in zip(articles, poids)):
        return None   # un article tomberait sous une unité
    return articles, poids


def proposer_articles(fob, client='', fichier=None, exclure=None, hasard=None, essais=30):
    """Articles et quantités proposés au hasard pour une licence qui n'a qu'un FOB.

    Une licence modèle (avec articles) est tirée au sort, de préférence du même client et
    d'un FOB proche. Si le modèle n'a qu'un article, cet article seul est repris ; sinon
    une partie de ses articles est choisie (nombre et proportions variés). Les quantités sont
    calculées pour que le total soit exactement le FOB.
    Renvoie dict(produits, source, nombre_modele) ; ValueError si aucune licence modèle.
    """
    import math
    import random
    hasard = hasard or random.SystemRandom()
    cible = _decimal(fob)
    if cible is None or cible <= 0:
        raise ValueError('Renseignez d’abord le montant FOB de la licence (onglet Licence).')
    modeles = modeles_articles(fichier, exclure)
    if not modeles:
        raise ValueError('Aucune licence avec des articles complets (prix et quantité) : '
                         'saisissez les articles d’au moins une licence pour servir de modèle.')
    client = cle_nom(client)

    def affinite(modele):
        # FOB proche du modèle : poids plus fort (1 pour un FOB identique, 1/3 pour un facteur e²).
        proche = 1 / (1 + abs(math.log(float(cible / modele['fob']))) / 2)
        return proche * (4 if client and modele['client'] == client else 1)

    meilleure = None
    for _ in range(essais):
        modele = _tirer_sans_remise(hasard, modeles, [affinite(m) for m in modeles], 1)[0]
        proposition = _proposition(modele, cible, hasard)
        if proposition is None:
            continue
        produits, ecart = repartir_quantites(proposition[0], cible, proposition[1])
        if meilleure is None or abs(ecart) < abs(meilleure[1]):
            meilleure = (dict(produits=produits, source=modele['numero'], nombre_modele=len(modele['articles'])), ecart)
        if ecart == 0:
            break
    if meilleure is None:
        raise ValueError('Le FOB est trop faible pour les articles des licences modèles.')
    meilleure[0]['ecart'] = meilleure[1]
    return meilleure[0]
