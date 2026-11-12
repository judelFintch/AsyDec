"""Articles comptés à l'unité (motos, pièces, paires, cartons…) : quantités toujours entières.

Une licence peut porter une quantité fractionnaire (ex. 1 425,212 motos, quand le PU a été déduit du FOB).
On ne vend pas 0,212 moto : la quantité est arrondie à l'entier et c'est le prix unitaire qui s'ajuste,
avec au besoin plus de deux décimales, pour que quantité × PU donne exactement la valeur de l'article
(et donc le FOB de la licence). Les marchandises au poids ou au volume (kg, litres, m³…) gardent leurs décimales.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

CENTIME = Decimal('0.01')
DECIMALES_MAX_PU = 6

_COMPTABLES = re.compile(r'pi[eè]ce|unit[eé]?|\bpcs?\b|\bu\b|paire|\bpairs?\b|nombre|\bnbre?\b|\bsets?\b|\bjeux?\b|'
                         r'carton|colis|\bsacs?\b|balles?|bottes?|rouleaux?|\bpaquets?\b|\btetes?\b|têtes?|'
                         r'\bnos?\b|\bea(ch)?\b', re.I)
_MESURES = re.compile(r'kilo|\bkgs?\b|gramme|\bg\b|tonne|\bt\b|litre|\bl\b|\bm[23²³]?\b|m[eè]tre|mètre', re.I)


def comptable(unite):
    """True pour une unité de comptage (pièce, unité, paire…), False pour une mesure (kg, litre, m…)."""
    texte = str(unite or '').strip()
    if not texte:
        return False
    if _MESURES.search(texte) and not _COMPTABLES.search(texte):
        return False
    return bool(_COMPTABLES.search(texte))


def _decimal(valeur):
    try:
        d = Decimal(str(valeur).replace(' ', '').replace(' ', '').replace(',', '.'))
    except (InvalidOperation, TypeError):
        return None
    return d if d.is_finite() else None


def valeur(quantite, prix):
    return (quantite * prix).quantize(CENTIME, rounding=ROUND_HALF_UP)


def entier(quantite):
    """Quantité entière la plus proche, au moins 1."""
    return max(Decimal(1), quantite.to_integral_value(rounding=ROUND_HALF_UP))


def pu_exact(quantite, montant, reference=None):
    """Prix unitaire avec le moins de décimales possible (2 à 6) tel que quantité × PU = montant au centime ;
    au plus près de montant / quantité. None si impossible."""
    if quantite <= 0 or montant <= 0:
        return None
    cible = montant / quantite
    for decimales in range(2, DECIMALES_MAX_PU + 1):
        pas = Decimal(1).scaleb(-decimales)
        base = cible.quantize(pas, rounding=ROUND_HALF_UP)
        candidats = [base + k * pas for k in range(-3, 4) if base + k * pas > 0]
        exacts = [p for p in candidats if valeur(quantite, p) == montant]
        if exacts:
            return min(exacts, key=lambda p: (abs(p - cible), p))
    return None


def format_quantite(q):
    return format(q.normalize(), 'f') if q == q.to_integral_value() else format(q, '.3f')


def format_pu(pu):
    """PU affiché avec 2 décimales au moins, plus seulement si nécessaires (ex. 701.754386)."""
    d = _decimal(pu)
    if d is None:
        return str(pu)
    texte = format(d.quantize(Decimal(1).scaleb(-DECIMALES_MAX_PU)), 'f').rstrip('0')
    entiere, _, decimales = texte.partition('.')
    return f'{entiere}.{decimales.ljust(2, "0")}'


def pu_texte(pu, separateur_milliers=','):
    """PU pour un document : « 1,234.56 » ou « 701.754386 », séparateur de milliers au choix."""
    texte = format_pu(pu)
    entiere, _, decimales = texte.partition('.')
    signe = '-' if entiere.startswith('-') else ''
    entiere = entiere.lstrip('-')
    groupes = []
    while len(entiere) > 3:
        groupes.insert(0, entiere[-3:])
        entiere = entiere[:-3]
    groupes.insert(0, entiere)
    return signe + separateur_milliers.join(groupes) + '.' + decimales


def fractionnaires(produits):
    """Articles comptés à l'unité dont la quantité a des décimales : [(indice, désignation, quantité)]."""
    resultat = []
    for i, p in enumerate(produits or []):
        q = _decimal(p.get('quantite'))
        if q is not None and comptable(p.get('unite')) and q != q.to_integral_value():
            resultat.append((i, ' '.join(str(p.get('designation', '')).split()), q))
    return resultat


def arrondir(produits, cibles=None):
    """Copie des articles avec quantités entières pour les articles comptés à l'unité.

    cibles : valeur à atteindre pour chaque article (par défaut quantité × prix d'origine) ; le prix
    unitaire est recalculé pour que quantité entière × PU = cette valeur exactement.
    Renvoie les articles d'origine (même objet) si rien n'est à changer."""
    a_corriger = {i for i, _, _ in fractionnaires(produits)}
    if cibles is not None:
        a_corriger |= {i for i, (p, c) in enumerate(zip(produits, cibles))
                       if c is not None and comptable(p.get('unite'))
                       and _decimal(p.get('quantite')) is not None and _decimal(p.get('prix_unitaire')) is not None
                       and valeur(_decimal(p.get('quantite')), _decimal(p.get('prix_unitaire'))) != c}
    if not a_corriger:
        return produits
    copies = [dict(p) for p in produits]
    for i in sorted(a_corriger):
        q, p = _decimal(copies[i].get('quantite')), _decimal(copies[i].get('prix_unitaire'))
        if q is None or p is None or q <= 0:
            continue
        cible = cibles[i] if cibles is not None and cibles[i] is not None else valeur(q, p)
        q_entiere = entier(q)
        pu = pu_exact(q_entiere, cible, p)
        if pu is None:
            continue
        copies[i]['quantite'] = format_quantite(q_entiere)
        copies[i]['prix_unitaire'] = format_pu(pu)
    return copies


def entiers_prix_conserves(produits):
    """Copie avec quantités entières pour les articles comptés, prix unitaires inchangés (la valeur bouge)."""
    indices = {i for i, _, _ in fractionnaires(produits)}
    if not indices:
        return produits
    copies = [dict(p) for p in produits]
    for i in indices:
        copies[i]['quantite'] = format_quantite(entier(_decimal(copies[i]['quantite'])))
    return copies
