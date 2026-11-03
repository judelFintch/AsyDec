"""Compteur affiché sur les pages de génération : modèles possibles pour les totaux, et modèles déjà générés."""
import math

from asydec.calcul import variantes
from asydec.formats import nombre

EXPOSANTS = str.maketrans('0123456789-', '⁰¹²³⁴⁵⁶⁷⁸⁹⁻')
_CACHE = {}


def grand_nombre(x):
    """12345 -> « 12 345 » ; 1,86e18 -> « 1,9 × 10¹⁸ »."""
    if x < 1e6:
        return nombre(round(x))
    exposant = math.floor(math.log10(x))
    return f"{nombre(x / 10 ** exposant, 1)} × 10{str(exposant).translate(EXPOSANTS)}"


def pourcentage(part):
    """Part de 0 à 1 en pourcentage lisible, y compris pour les toutes petites valeurs."""
    pct = 100 * part
    if pct == 0:
        return "0 %"
    if pct < 0.0001:
        return "< 0,0001 %"
    return f"{nombre(pct, 4 if pct < 1 else 1)} %"


def estimation(base, poids, fob, colis, profil):
    """Estimation mise en cache par dossier, totaux et fourchettes de contrôle."""
    cle = (str(base), int(poids), round(fob, 2), int(colis), tuple(map(tuple, profil['bornes'])),
           bool(profil.get('variables_libres')))
    if cle not in _CACHE:
        _CACHE[cle] = variantes.estimer_possibles(poids, fob, colis, profil)
    return _CACHE[cle]


def enregistres(app, profil, poids, fob, colis):
    """Modèles enregistrés aux mêmes articles et totaux ; 0 si la liste est illisible."""
    try:
        from asydec.declarations import modeles_generes
        return modeles_generes.nombre_generes(profil['signature'], poids, fob, colis,
                                              module=getattr(app, 'module_travail', 'friperie'))
    except Exception:  # noqa: BLE001 - le compteur est une aide
        return 0


def texte(possibles, session, enregistres_):
    """Ligne affichée : possibles, générés, et probabilité de retomber sur un modèle déjà généré."""
    generes = f"Générés : {session} cette session · {enregistres_} enregistré(s) pour ces totaux"
    if possibles['estimation'] <= 0:
        return (f"Modèles possibles pour ces totaux : très peu (moins de {grand_nombre(max(1, possibles['plafond']))}, "
                f"aucun sur {possibles['essais']} essais) · {generes}")
    deja = (session + enregistres_) / possibles['estimation']
    return (f"Modèles possibles pour ces totaux : ≈ {grand_nombre(possibles['estimation'])} (estimation) · "
            f"{generes} · Probabilité de retomber sur un modèle déjà généré : {pourcentage(min(1, deja))}")


def calculer(app, base, profil, poids, fob, colis, session):
    """Texte du compteur, ou chaîne vide si les totaux ne permettent pas de l'estimer."""
    try:
        if not (poids and fob and colis) or int(poids) != poids or int(colis) != colis:
            return ""
        possibles = estimation(base, poids, fob, colis, profil)
    except Exception:  # noqa: BLE001 - le compteur est une aide
        return ""
    return texte(possibles, session, enregistres(app, profil, poids, fob, colis))
