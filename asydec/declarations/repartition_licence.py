"""Division exacte du FOB et poids proposé par part (aléatoire entre 22 000 et 24 000 kg).

Par défaut : nombre de parts calculé automatiquement, parts égales de 120 000 USD maximum.
Options : nombre de parts choisi par l'utilisateur et/ou plafond de 120 000 USD retiré ;
la division reste la même (parts égales, total conservé au centime).
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

PLAFOND = Decimal('120000.00')
POIDS_PROPOSE = 23000
POIDS_MIN, POIDS_MAX = 22000, 24000
MAX_PARTS = 99


def nombre_parts(valeur):
    """None (automatique) ou nombre entier de parts entre 1 et MAX_PARTS."""
    if valeur is None or str(valeur).strip() == '':
        return None
    try:
        nombre = int(str(valeur).strip())
    except ValueError:
        raise ValueError(f'Nombre de parts invalide : indiquez un entier entre 1 et {MAX_PARTS}, ou laissez vide.') from None
    if not 1 <= nombre <= MAX_PARTS:
        raise ValueError(f'Nombre de parts invalide : indiquez un entier entre 1 et {MAX_PARTS}, ou laissez vide.')
    return nombre


def montant(valeur):
    try:
        nombre = Decimal(str(valeur).replace(' ', '').replace('\u00a0', '').replace('\u202f', '').replace(',', '.'))
    except InvalidOperation:
        raise ValueError('Montant FOB invalide.') from None
    if not nombre.is_finite() or nombre <= 0 or nombre != nombre.quantize(Decimal('.01')):
        raise ValueError('Le FOB doit être positif avec deux décimales au maximum.')
    return nombre


def minimum_parts(fob):
    """Nombre de parts automatique : le moins possible sous le plafond."""
    centimes, plafond = int(montant(fob) * 100), int(PLAFOND * 100)
    return (centimes + plafond - 1) // plafond


def repartir(fob, nombre=None, plafond=True):
    total = montant(fob)
    centimes = int(total * 100)
    nombre = nombre_parts(nombre)
    if nombre is None:
        nombre = minimum_parts(total) if plafond else 1
    elif plafond and nombre < minimum_parts(total):
        raise ValueError(f'Avec le plafond de 120 000 USD, il faut au moins {minimum_parts(total)} parts. '
                         'Augmentez le nombre de parts ou retirez le plafond.')
    if nombre > centimes:
        raise ValueError('Trop de parts pour ce FOB : chaque part doit valoir au moins 0,01 USD.')
    base, reste = divmod(centimes, nombre)
    return [Decimal(base + (1 if i < reste else 0)) / 100 for i in range(nombre)]


def _diviser(valeur, nombre, pas):
    """Parts identiques au pas près ; le reste va aux premières parts, total conservé."""
    unites = int((valeur / pas).to_integral_value())
    base, reste = divmod(unites, nombre)
    return [(base + (1 if i < reste else 0)) * pas for i in range(nombre)]


def _articles(produits):
    """[(produit, quantité, prix, pas)] ou None si un article n'a pas de quantité ou de prix exploitable."""
    resultat = []
    for produit in produits or []:
        try:
            quantite = Decimal(str(produit.get('quantite', '')).replace(' ', '').replace(',', '.'))
            prix = Decimal(str(produit.get('prix_unitaire', '')).replace(' ', '').replace(',', '.'))
        except InvalidOperation:
            return None
        if not quantite.is_finite() or not prix.is_finite() or quantite <= 0 or prix < 0:
            return None
        pas = Decimal(1) if quantite == quantite.to_integral_value() else Decimal('0.001')
        resultat.append((produit, quantite, prix, pas))
    return resultat or None


def _valeur(quantite, prix):
    return (quantite * prix).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def ecart_arrondi(produits, fob):
    """Écart (FOB − somme quantité × prix) s'il ne vient que de l'arrondi des quantités, sinon None.

    Les licences portent des quantités arrondies (ex. 39,865 pièces × 702 = 27 985,23 pour un FOB
    de 27 985,00) : l'écart toléré est d'un pas de quantité par article (1 ou 0,001) au prix unitaire."""
    articles = _articles(produits)
    if not articles:
        return None
    ecart = montant(fob) - sum((_valeur(q, p) for _, q, p, _ in articles), Decimal(0))
    tolerance = sum((pas * p for _, _, p, pas in articles), Decimal(0)) + Decimal('0.01') * len(articles)
    return ecart if abs(ecart) <= tolerance else None


def ajuster_articles(produits, fob):
    """Articles corrigés pour que quantité × prix unitaire donne exactement le FOB de la licence.

    1. Articles comptés à l'unité (motos, pièces, paires…) : quantité entière, jamais de décimales ; le prix
       unitaire est recalculé pour garder la valeur de l'article (voir quantites_entieres).
    2. Écart d'arrondi avec le FOB (voir ecart_arrondi) : porté par un article mesuré (kg, litres…) dont la
       quantité est retouchée au millième, le moins cher d'abord ; sans article mesuré, par le prix unitaire
       de l'article compté le plus cher. Ex. 39,865 motos × 702 = 27 985,23 pour un FOB de 27 985,00
       devient 40 motos × 699,625 = 27 985,00.
    Écart réel (non dû à l'arrondi) : seules les quantités sont rendues entières, valeurs inchangées."""
    from asydec.declarations import quantites_entieres as QE
    try:
        ecart = ecart_arrondi(produits, fob)
    except ValueError:
        ecart = None
    articles = _articles(produits)
    if not articles:
        return produits
    mesures = [i for i, (produit, *_) in enumerate(articles) if not QE.comptable(produit.get('unite'))]
    if ecart and not mesures:
        cibles = [_valeur(q, p) for _, q, p, _ in articles]
        plus_cher = max(range(len(cibles)), key=lambda i: cibles[i])
        if cibles[plus_cher] + ecart > 0:
            cibles[plus_cher] += ecart
            return QE.arrondir(produits, cibles)
        return QE.arrondir(produits)
    if ecart is not None and mesures:
        # Pièces arrondies à prix inchangé ; l'article mesuré absorbe l'écart au millième.
        entiers = QE.entiers_prix_conserves(produits)
        valeurs = [_valeur(q, p) for _, q, p, _ in _articles(entiers)]
        if sum(valeurs) == montant(fob):
            return entiers
        corriges = _ajuster_quantite(entiers, fob, mesures)
        if corriges is not entiers:
            return corriges
    resultat = QE.arrondir(produits)
    if ecart:
        resultat = _ajuster_quantite(resultat, fob, mesures)
    return resultat


def _ajuster_quantite(produits, fob, indices):
    """Écart d'arrondi porté par un des articles « indices » : quantité au millième puis, si besoin,
    prix de quelques centimes au plus près de l'original. Articles inchangés si impossible."""
    articles = _articles(produits)
    total = montant(fob)
    millieme, centime = Decimal('0.001'), Decimal('0.01')
    valeurs = [_valeur(q, p) for _, q, p, _ in articles]
    for i in sorted(indices, key=lambda i: articles[i][2]):
        _, q0, p0, _ = articles[i]
        reste = total - sum(valeurs) + valeurs[i]
        if reste <= 0:
            continue
        for k in range(0, 1001):
            for p in dict.fromkeys((p0 - k * centime, p0 + k * centime)):
                if p <= 0:
                    continue
                base = (reste / p).quantize(millieme)
                for q in (base, base - millieme, base + millieme):
                    if q > 0 and _valeur(q, p) == reste:
                        copies = [dict(a) for a in produits]
                        copies[i]['quantite'] = format(q.normalize(), 'f') if q == q.to_integral_value() else format(q, '.3f')
                        if p != p0:
                            copies[i]['prix_unitaire'] = format(p, '.2f')
                        return copies
    return produits


def valeurs_articles(produits, fob):
    """Valeur de chaque article telle qu'elle sera répartie : quantité × prix, l'écart d'arrondi avec le FOB
    étant porté par l'article le plus cher. None si les articles ne sont pas exploitables ;
    sans correspondance au FOB (écart réel), les valeurs brutes."""
    articles = _articles(produits)
    if not articles:
        return None
    valeurs = [_valeur(q, p) for _, q, p, _ in articles]
    try:
        ecart = ecart_arrondi(produits, fob)
    except ValueError:
        ecart = None
    if ecart:
        valeurs[valeurs.index(max(valeurs))] += ecart
    return valeurs


def repartir_articles(produits, nombre, ecart=Decimal(0)):
    """Quantité et valeur de chaque article divisées à l'identique entre les parts.

    ecart : différence d'arrondi avec le FOB, ajoutée à la valeur de l'article le plus cher
    pour que le total des articles soit exactement le FOB de la licence.
    Retourne une liste (une entrée par part) de lignes d'articles, ou None si les
    articles ne correspondent pas à des quantités et prix exploitables.
    """
    articles = _articles(produits)
    if not articles:
        return None
    ajuste = max(range(len(articles)), key=lambda i: _valeur(articles[i][1], articles[i][2]))
    if ecart and _valeur(articles[ajuste][1], articles[ajuste][2]) + ecart <= 0:
        return None
    parts = [[] for _ in range(nombre)]
    for indice, (produit, quantite, prix, pas) in enumerate(articles, 1):
        quantites = _diviser(quantite, nombre, pas)
        valeur_totale = _valeur(quantite, prix) + (ecart if indice - 1 == ajuste else 0)
        valeurs = [(q * prix).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) for q in quantites[:-1]]
        valeurs.append(valeur_totale - sum(valeurs, Decimal(0)))
        for part, q, v in zip(parts, quantites, valeurs):
            part.append(dict(article=indice, designation=' '.join(str(produit.get('designation', '')).split()),
                             unite=produit.get('unite', ''), prix_unitaire=format(prix, 'f'),
                             quantite=format(q.normalize(), 'f') if pas == 1 else format(q, '.3f'),
                             valeur=format(v, '.2f')))
    return parts


def poids_part(poids):
    """Poids entier entre 22 000 et 24 000 kg."""
    try:
        valeur = Decimal(str(poids).replace(' ', '').replace('\u00a0', '').replace('\u202f', '').replace(',', '.'))
    except InvalidOperation:
        raise ValueError('Indiquez un poids entier entre 22 000 et 24 000 kg.') from None
    if not valeur.is_finite() or valeur != valeur.to_integral_value() or not POIDS_MIN <= valeur <= POIDS_MAX:
        raise ValueError('Indiquez un poids entier entre 22 000 et 24 000 kg.')
    return int(valeur)


def proposer_poids(nombre, existants=()):
    """Un poids aléatoire (22 000 à 24 000 kg) par part ; les poids valides déjà proposés sont conservés."""
    import secrets
    resultat = []
    for poids in list(existants)[:nombre]:
        try:
            resultat.append(poids_part(poids))
        except ValueError:
            resultat.append(None)
    resultat += [None] * (nombre - len(resultat))
    return [p if p is not None else POIDS_MIN + secrets.randbelow(POIDS_MAX - POIDS_MIN + 1) for p in resultat]


def preparer(fob, poids=POIDS_PROPOSE, produits=None, nombre=None, plafond=True):
    """poids : un poids commun à toutes les parts, ou une liste (un poids par part ; les parts
    manquantes reçoivent un poids aléatoire). nombre : parts choisies (None = automatique) ;
    plafond=False retire la limite de 120 000 USD."""
    if isinstance(poids, (list, tuple)):
        poids_liste = [poids_part(p) for p in poids]
        commun = None
    else:
        commun = poids_part(poids)
        poids_liste = None
    total = montant(fob)
    nombre_choisi = nombre_parts(nombre)
    plafond = bool(plafond)
    montants = repartir(fob, nombre_choisi, plafond)
    articles = None
    # Division des articles seulement si leurs valeurs correspondent au FOB de la licence,
    # à l'arrondi des quantités près (l'écart est absorbé pour retomber exactement sur le FOB).
    ecart = ecart_arrondi(produits, total)
    if ecart is not None and repartir_articles(produits, 1, ecart):
        nombre = len(montants)
        while True:
            articles = repartir_articles(produits, nombre, ecart)
            # Le FOB de chaque part est la somme de ses articles, pour rester cohérent.
            montants = [sum((Decimal(a['valeur']) for a in part), Decimal(0)) for part in articles]
            if not plafond or max(montants) <= PLAFOND:
                break
            if nombre_choisi is not None:
                raise ValueError(f'Avec {nombre_choisi} parts, une part dépasse 120 000 USD une fois les articles divisés. '
                                 'Augmentez le nombre de parts ou retirez le plafond.')
            nombre += 1
    poids_parts = [commun] * len(montants) if commun is not None else proposer_poids(len(montants), poids_liste)
    identiques = len(set(poids_parts)) == 1
    resultat = dict(fob_total=format(total, '.2f'), plafond_usd=str(PLAFOND) if plafond else None,
                    plafond_actif=plafond, nombre_parts_choisi=nombre_choisi,
                    poids_par_part_kg=poids_parts[0] if identiques else None, poids_total_kg=sum(poids_parts),
                    parts=[dict(numero=i + 1, fob=format(part, '.2f'), poids_kg=poids_parts[i])
                           for i, part in enumerate(montants)])
    if articles:
        for part, lignes in zip(resultat['parts'], articles):
            part['articles'] = lignes
    return resultat


FORMAT_PLAQUE = r'T[1-9][0-9]{2}[A-Z]{3}/T[1-9][0-9]{2}[A-Z]{3}'


def verifier_plaques(plaques, nombre):
    import re
    if len(plaques) != nombre:
        raise ValueError('Une paire de plaques est requise pour chaque part.')
    utilisees = set()
    for paire in plaques:
        if not isinstance(paire, str) or not re.fullmatch(FORMAT_PLAQUE, paire):
            raise ValueError('Format de plaques attendu : T171EAK/T196EAK.')
        camion, remorque = paire.split('/')
        if camion == remorque or camion in utilisees or remorque in utilisees:
            raise ValueError('Chaque plaque doit être unique dans cette licence.')
        utilisees.update((camion, remorque))
    return list(plaques)


def proposer_plaques(nombre, existantes=()):
    """Conserve les propositions valides ; complète sans doublon de camion/remorque."""
    import re
    import secrets
    import string
    resultat = [None] * nombre
    utilisees = set()
    for i, paire in enumerate(list(existantes)[:nombre]):
        if not isinstance(paire, str) or not re.fullmatch(FORMAT_PLAQUE, paire):
            continue
        camion, remorque = paire.split('/')
        if camion != remorque and camion not in utilisees and remorque not in utilisees:
            resultat[i] = paire
            utilisees.update((camion, remorque))

    def nouvelle():
        while True:
            plaque = 'T' + str(secrets.randbelow(900) + 100) + ''.join(secrets.choice(string.ascii_uppercase) for _ in range(3))
            if plaque not in utilisees:
                utilisees.add(plaque)
                return plaque

    for i, paire in enumerate(resultat):
        if paire is None:
            resultat[i] = nouvelle() + '/' + nouvelle()
    return resultat
