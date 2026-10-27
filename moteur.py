"""Moteur de calcul des déclarations ASYCUDA / SYDONIA (friperie).

Recalcule une déclaration XML à partir d'un fichier de base :
valeurs par article (facture, fret, assurance, CIF), coefficients de
répartition, toutes les lignes de taxes, totaux, et nombre de colis.

Les règles de calcul ont été vérifiées en régénérant des déclarations
SYDONIA réelles (KDMETA, SHABANI) : résultat identique au CDF près.
"""
import math
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP

# Taxes arrondies au plus proche ; les autres sont tronquées.
TAXES_ARRONDIES = {"TVA", "RCC", "RRC"}
# Taxes dont le taux est en pour mille.
TAXES_POUR_MILLE = {"RCC", "RRC"}
# Articles dont le FOB s'ajuste pour atteindre le FOB total (index 0 = article 1).
ARTICLES_VARIABLES = (3, 6, 7)


def arrondi(x):
    return math.floor(x + 0.5)


def _txt(e, chemin):
    return (e.findtext(chemin) or "").strip()


def _fl(texte):
    return float(texte) if texte else 0.0


def _ecrire(e, chemin, valeur):
    noeud = e.find(chemin)
    for enfant in list(noeud):
        noeud.remove(enfant)
    noeud.text = valeur


def _nombre(x):
    x = round(x, 2)
    return str(int(x)) if x == int(x) else f"{x:.2f}".rstrip("0")


def _kg(x):
    return f"{x:.3f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------
# Lecture
# --------------------------------------------------------------------------
def charger(chemin):
    return ET.parse(chemin)


def articles(racine):
    """Articles réellement remplis (prix non nul)."""
    return [it for it in racine.findall("Item") if _fl(_txt(it, "Tarification/Item_price"))]


CHEMINS_PLAQUE = ("Transport/Means_of_transport/Departure_arrival_information/Identity",
                  "Transport/Means_of_transport/Border_information/Identity")


def normaliser_plaque(valeur):
    """Plaque en majuscules ; lettres, chiffres, espaces, « - » et « / » seulement."""
    import re
    texte = " ".join(str(valeur or "").upper().split())
    if not texte:
        raise ValueError("Indiquez la plaque du camion.")
    if len(texte) > 40 or not re.fullmatch(r"[A-Z0-9][A-Z0-9 /-]*", texte):
        raise ValueError("Plaque invalide : lettres, chiffres, espaces, « - » ou « / » uniquement, 40 caractères au plus.")
    return texte


def ecrire_plaque(racine, plaque):
    """Inscrit la plaque aux champs Identity d'arrivée et de frontière du transport."""
    plaque = normaliser_plaque(plaque)
    champs = [e for e in (racine.find(c) for c in CHEMINS_PLAQUE) if e is not None]
    if not champs:
        raise ValueError("Le XML de base n'a pas de champ plaque (Transport/Means_of_transport) : plaque non inscrite.")
    for champ in champs:
        for enfant in list(champ):  # <null/> éventuel
            champ.remove(enfant)
        champ.text = plaque
    return plaque


def infos_dossier(racine):
    nom = _txt(racine, "Traders/Consignee/Consignee_name").splitlines()
    its = articles(racine)
    return {
        "importateur": nom[0].strip() if nom else "",
        "code": _txt(racine, "Traders/Consignee/Consignee_code"),
        "reference": _txt(racine, "Declarant/Reference/Number"),
        "manifeste": _txt(racine, "Identification/Manifest_reference_number"),
        "camion": _txt(racine, "Transport/Means_of_transport/Departure_arrival_information/Identity"),
        "taux": _fl(_txt(racine, "Valuation/Gs_Invoice/Currency_rate")),
        "fob": _fl(_txt(racine, "Valuation/Total/Total_invoice")),
        "poids": _fl(_txt(racine, "Valuation/Total/Total_weight")),
        "colis": int(_fl(_txt(racine, "Property/Nbers/Total_number_of_packages"))),
        "fob_articles": [_fl(_txt(i, "Tarification/Item_price")) for i in its],
        "poids_articles": [_fl(_txt(i, "Valuation_item/Weight_itm/Gross_weight_itm")) for i in its],
        "colis_articles": [int(_fl(_txt(i, "Packages/Number_of_packages"))) for i in its],
        "designations": [_txt(i, "Goods_description/Description_of_goods") for i in its],
    }


# --------------------------------------------------------------------------
# FOB par article selon les ratios
# --------------------------------------------------------------------------
def fob_par_ratios(poids, ratios, fob_total):
    """FOB = poids x ratio pour chaque article, puis l'écart avec le FOB total
    est réparti sur les articles 4, 7 et 8 au prorata de leur FOB."""
    D = Decimal
    fob = [(D(str(p)) * D(str(r))).quantize(D("0.01"), ROUND_HALF_UP) for p, r in zip(poids, ratios)]
    cible = D(str(fob_total))
    ecart = cible - sum(fob)
    var = [i for i in ARTICLES_VARIABLES if i < len(fob)]
    base = sum(fob[i] for i in var)
    if base:
        for i in var:
            fob[i] = (fob[i] * (base + ecart) / base).quantize(D("0.01"), ROUND_HALF_UP)
        fob[var[0]] += cible - sum(fob)
    negatifs = [i + 1 for i, x in enumerate(fob) if x <= 0]
    if negatifs:
        raise ValueError(f"FOB total {cible} USD trop bas : les articles {', '.join(map(str, negatifs))} "
                         f"tomberaient à zéro ou en négatif. Augmentez le FOB total ou passez en FOB saisis.")
    return [float(x) for x in fob], float(ecart)


def ajuster_poids(poids, total):
    """Ramène les poids au total voulu, tous au même pourcentage
    (kilos entiers, méthode du plus grand reste)."""
    somme = sum(poids)
    if somme <= 0:
        raise ValueError("Poids total nul.")
    total = int(round(total))
    brut = [p * total / somme for p in poids]
    res = [math.floor(x) for x in brut]
    for i in sorted(range(len(poids)), key=lambda i: brut[i] - res[i], reverse=True)[: total - sum(res)]:
        res[i] += 1
    return [float(x) for x in res]


# --------------------------------------------------------------------------
# Colis gradués
# --------------------------------------------------------------------------
def colis_gradues(poids, fob, total, minimum=10):
    """Répartit les colis au prorata du poids (le FOB départage les égalités).
    Les petits articles sont gradués à partir du minimum (10, 11, 12...),
    tous les nombres sont différents et la somme fait exactement le total."""
    n = len(poids)
    W, F = sum(poids), sum(fob) or 1
    s = [poids[i] / W + 1e-6 * fob[i] / F for i in range(n)]
    minimum_total = sum(range(minimum, minimum + n))
    if total == minimum_total:
        ordre = sorted(range(n), key=lambda i: (s[i], poids[i], i))
        a = [0] * n
        for k, i in enumerate(ordre):
            a[i] = minimum + k
        return a
    petits = set()
    while True:
        gros = [i for i in range(n) if i not in petits]
        reste = total - sum(minimum + k for k in range(len(petits)))
        S = sum(s[i] for i in gros)
        bas = [i for i in gros if reste * s[i] / S < minimum + len(petits) + 1]
        if not bas:
            break
        petits |= set(bas)
    a = [0] * n
    for k, i in enumerate(sorted(petits, key=lambda i: (s[i], poids[i]))):
        a[i] = minimum + k
    gros = [i for i in range(n) if i not in petits]
    reste = total - sum(a)
    S = sum(s[i] for i in gros)
    brut = {i: reste * s[i] / S for i in gros}
    for i in gros:
        a[i] = math.floor(brut[i])
    for i in sorted(gros, key=lambda i: brut[i] - a[i], reverse=True)[: total - sum(a)]:
        a[i] += 1
    plus_gros = max(range(n), key=lambda i: a[i])
    for _ in range(100):
        vus, doublon = set(), None
        for i in sorted(range(n), key=lambda i: (a[i], s[i])):
            if a[i] in vus:
                doublon = i
                break
            vus.add(a[i])
        if doublon is None:
            break
        a[doublon] += 1
        a[plus_gros] -= 1
    if sum(a) != total or min(a) < minimum:
        raise ValueError("Répartition des colis impossible avec ce total.")
    return a


# --------------------------------------------------------------------------
# Recalcul complet
# --------------------------------------------------------------------------
def recalculer(arbre, lignes, colis=None):
    """lignes = [(fob_usd, poids_kg), ...] dans l'ordre des articles du fichier.
    colis = liste de colis par article (ou None pour garder ceux du fichier).
    Modifie l'arbre et renvoie un résumé."""
    r = arbre.getroot()
    V0 = r.find("Valuation")
    TAUX = _fl(_txt(V0, "Gs_Invoice/Currency_rate"))
    FRET = _fl(_txt(V0, "Gs_external_freight/Amount_foreign_currency"))
    ASSU = _fl(_txt(V0, "Gs_insurance/Amount_foreign_currency"))
    its = articles(r)
    if len(its) != len(lignes):
        raise ValueError(f"Le fichier de base contient {len(its)} articles valorisés, mais {len(lignes)} lignes ont été fournies.")
    if len(its) < len(lignes):
        raise ValueError(f"Le fichier de base n'a que {len(its)} articles.")
    TOTAL = round(sum(p for p, _ in lignes), 2)
    TOTAL_KG = round(sum(w for _, w in lignes), 3)
    if TOTAL <= 0:
        raise ValueError("FOB total nul.")

    resume = {"articles": [], "taux": TAUX, "fret": FRET, "assurance": ASSU}
    taxes_articles = 0
    for it, (prix, kg) in zip(its, lignes):
        a = prix / TOTAL
        fact = round(prix * TAUX, 2)
        fret_usd = round(FRET * a, 2)
        fret = round(fret_usd * TAUX, 2)
        assu_usd = round(ASSU * a, 2)
        assu = round(assu_usd * TAUX, 2)
        cout = arrondi(fret) + arrondi(assu)
        cif = arrondi(fact) + cout

        _ecrire(it, "Tarification/Item_price", _nombre(prix))
        _ecrire(it, "Tarification/Value_item", f"{arrondi(fret):,}+0+{arrondi(assu):,}+0-0")
        v = it.find("Valuation_item")
        _ecrire(v, "Weight_itm/Gross_weight_itm", _kg(kg))
        _ecrire(v, "Weight_itm/Net_weight_itm", _kg(kg))
        _ecrire(v, "Total_cost_itm", str(cout))
        _ecrire(v, "Total_CIF_itm", str(cif))
        _ecrire(v, "Statistical_value", str(cif))
        _ecrire(v, "Alpha_coeficient_of_apportionment", f"{a:.14g}")
        _ecrire(v, "Item_Invoice/Amount_national_currency", _nombre(fact))
        _ecrire(v, "Item_Invoice/Amount_foreign_currency", _nombre(prix))
        _ecrire(v, "item_external_freight/Amount_national_currency", _nombre(fret))
        _ecrire(v, "item_external_freight/Amount_foreign_currency", _nombre(fret_usd))
        _ecrire(v, "item_insurance/Amount_national_currency", _nombre(assu))
        _ecrire(v, "item_insurance/Amount_foreign_currency", _nombre(assu_usd))

        lignes_tax = [t for t in it.findall("Taxation/Taxation_line") if _txt(t, "Duty_tax_code")]
        taux_tax = {_txt(t, "Duty_tax_code"): _fl(_txt(t, "Duty_tax_rate")) for t in lignes_tax}
        montants, total_art = {}, 0
        for t in lignes_tax:
            code = _txt(t, "Duty_tax_code")
            tx = _fl(_txt(t, "Duty_tax_rate"))
            f = arrondi if code in TAXES_ARRONDIES else math.floor
            if code == "DDI":
                base = cif
            elif code in ("TVA", "TPI"):
                base = cif + montants["DDI"]
            elif code == "TVF":
                base = math.floor(cif * sum(taux_tax.get(k, 0) for k in ("COG", "RCO", "CSO")) / 100 + 1e-9)
            elif code == "QFR":
                base = kg
            elif code == "RLS":
                base = math.floor(round(_fl(_txt(t, "Duty_tax_Base")) / TAUX) * TAUX + 1e-9)
            else:
                base = cif
            if code == "QFR":
                montant = f(base * tx * TAUX + 1e-9)
            elif code == "RLS":
                montant = math.floor(base * tx + 1e-9)
            elif code == "COG" and abs(tx - 0.457) < 1e-9:
                montant = arrondi(base * 0.001 / 100 + 1e-9) + math.floor(base * 0.456 / 100 + 1e-9)
            else:
                montant = f(base * tx / (1000 if code in TAXES_POUR_MILLE else 100) + 1e-9)
            montants[code] = montant
            total_art += montant
            _ecrire(t, "Duty_tax_Base", _kg(base) if code == "QFR" else _nombre(base))
            _ecrire(t, "Duty_tax_amount", str(montant))
        _ecrire(it, "Taxation/Item_taxes_amount", str(total_art))
        taxes_articles += total_art
        resume["articles"].append({"fob": prix, "poids": kg, "cif": cif, "taxes": total_art})

    V = r.find("Valuation")
    fact_tot = round(TOTAL * TAUX, 2)
    _ecrire(V, "Gs_Invoice/Amount_national_currency", _nombre(fact_tot))
    _ecrire(V, "Gs_Invoice/Amount_foreign_currency", _nombre(TOTAL))
    _ecrire(V, "Total/Total_invoice", _nombre(TOTAL))
    _ecrire(V, "Total/Total_weight", _kg(TOTAL_KG))
    fret_n, assu_n = round(FRET * TAUX, 2), round(ASSU * TAUX, 2)
    _ecrire(V, "Gs_external_freight/Amount_national_currency", _nombre(fret_n))
    _ecrire(V, "Gs_insurance/Amount_national_currency", _nombre(assu_n))
    cout_tot = arrondi(fret_n) + arrondi(assu_n)
    _ecrire(V, "Total_cost", str(cout_tot))
    _ecrire(r, "General_information/Value_details", str(cout_tot))
    _ecrire(V, "Total_CIF", str(arrondi(fact_tot) + cout_tot))
    globales = int(_fl(_txt(r, "Financial/Amounts/Global_taxes")))
    _ecrire(r, "Financial/Amounts/Global_taxes", str(globales))
    _ecrire(r, "Financial/Amounts/Totals_taxes", str(taxes_articles + globales))

    if colis is not None:
        for it, c in zip(its, colis):
            it.find("Packages/Number_of_packages").text = str(int(c))
        r.find("Property/Nbers/Total_number_of_packages").text = str(int(sum(colis)))

    resume.update({
        "fob": TOTAL, "poids": TOTAL_KG, "cif": arrondi(fact_tot) + cout_tot,
        "taxes_articles": taxes_articles, "taxes_globales": globales,
        "taxes_totales": taxes_articles + globales,
        "colis": colis if colis is not None else [int(_fl(_txt(i, "Packages/Number_of_packages"))) for i in its],
    })
    return resume


def enregistrer(arbre, chemin):
    texte = ET.tostring(arbre.getroot(), encoding="unicode").replace(" />", "/>")
    with open(chemin, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n' + texte + "\n")
