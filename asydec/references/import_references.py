"""Import des XML dans la base de références : extraction complète, archivage, diagnostics.

Chaîne : empreinte → doublon ? → lecture → extraction exacte → contrôles → archive
→ une transaction SQLite par document (aucun document importé à moitié).
Un document importé n'est jamais marqué « accepté » : ce n'est qu'une observation.
"""
import hashlib
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from asydec.references import base_references as base
from asydec.references.base_references import decimal_canonique, maintenant

VERSION_PARSEUR = 1
# Tolérances des contrôles de cohérence (descriptives, sans valeur réglementaire).
TOLERANCES = {"fob": Decimal("0.005"), "poids": Decimal("0.0005"), "colis": Decimal("0"), "taxes": Decimal("0")}


@dataclass
class BilanImport:
    lot_id: int = None
    trouves: int = 0
    traites: int = 0
    importes: int = 0
    doublons: int = 0
    refuses: int = 0
    etat: str = "en_cours"
    refus: list = field(default_factory=list)       # (fichier, raison)
    documents: list = field(default_factory=list)   # identifiants des documents nouveaux
    documents_traites: list = field(default_factory=list)  # réussis et doublons, pour réactivation volontaire


# --------------------------------------------------------------------------
# Extraction (sans base de données)
# --------------------------------------------------------------------------
def _texte(e, chemin):
    noeud = e.find(chemin)
    if noeud is None or noeud.text is None:
        return None
    return noeud.text.strip() or None


def normaliser(designation):
    return " ".join((designation or "").casefold().split()) or None


def extraire(contenu):
    """Lit un XML ASYCUDA (octets) et renvoie un dictionnaire exact, sans base de données.
    Lève ValueError si le fichier n'est pas un XML ASYCUDA lisible."""
    try:
        racine = ET.fromstring(contenu)
    except ET.ParseError as exc:
        raise ValueError(f"XML illisible ({exc})") from None
    if racine.tag != "ASYCUDA":
        raise ValueError(f"format non reconnu : racine <{racine.tag}> au lieu de <ASYCUDA>")
    diagnostics = []

    def nombre(e, chemin, position=None):
        texte = _texte(e, chemin)
        try:
            return decimal_canonique(texte)
        except ValueError as exc:
            diagnostics.append(("erreur", "valeur_invalide", f"{chemin} : {exc}", position, None, texte))
            return None

    t = lambda chemin: _texte(racine, chemin)
    nom = (t("Traders/Consignee/Consignee_name") or "").splitlines()
    document = {
        "importateur": nom[0].strip() if nom else None,
        "importateur_code": t("Traders/Consignee/Consignee_code"),
        "declarant_reference": t("Declarant/Reference/Number"),
        "manifeste": t("Identification/Manifest_reference_number"),
        "camion": t("Transport/Means_of_transport/Departure_arrival_information/Identity"),
        "bureau_code": t("Identification/Office_segment/Customs_clearance_office_code"),
        "type_declaration": t("Identification/Type/Type_of_declaration"),
        "devise": t("Valuation/Gs_Invoice/Currency_code"),
        "nb_articles_declares": nombre(racine, "Property/Nbers/Total_number_of_items"),
    }
    # Dates gardées telles quelles : le format SYDONIA (« 10/1/26 ») est ambigu.
    for cle, bloc in (("enregistrement", "Registration"), ("liquidation", "Assessment"), ("quittance", "receipt")):
        document[f"{cle}_serie"] = t(f"Identification/{bloc}/Serial_number")
        document[f"{cle}_numero"] = t(f"Identification/{bloc}/Number")
        document[f"{cle}_date_brute"] = t(f"Identification/{bloc}/Date")

    v = "Valuation/"
    valorisation = {
        "fob_total": nombre(racine, v + "Total/Total_invoice"),
        "poids_total": nombre(racine, v + "Total/Total_weight"),
        "colis_total": nombre(racine, "Property/Nbers/Total_number_of_packages"),
        "devise_facture": t(v + "Gs_Invoice/Currency_code"),
        "taux_change": nombre(racine, v + "Gs_Invoice/Currency_rate"),
        "facture_monnaie_nationale": nombre(racine, v + "Gs_Invoice/Amount_national_currency"),
        "fret_externe_devise": t(v + "Gs_external_freight/Currency_code"),
        "fret_externe_montant": nombre(racine, v + "Gs_external_freight/Amount_foreign_currency"),
        "fret_externe_monnaie_nationale": nombre(racine, v + "Gs_external_freight/Amount_national_currency"),
        "fret_interne_monnaie_nationale": nombre(racine, v + "Gs_internal_freight/Amount_national_currency"),
        "assurance_devise": t(v + "Gs_insurance/Currency_code"),
        "assurance_montant": nombre(racine, v + "Gs_insurance/Amount_foreign_currency"),
        "assurance_monnaie_nationale": nombre(racine, v + "Gs_insurance/Amount_national_currency"),
        "autres_couts_monnaie_nationale": nombre(racine, v + "Gs_other_cost/Amount_national_currency"),
        "deductions_monnaie_nationale": nombre(racine, v + "Gs_deduction/Amount_national_currency"),
        "cout_total": nombre(racine, v + "Total_cost"),
        "cif_total": nombre(racine, v + "Total_CIF"),
        "taxes_globales": nombre(racine, "Financial/Amounts/Global_taxes"),
        "taxes_manuelles": nombre(racine, "Financial/Amounts/Total_manual_taxes"),
        "taxes_totales": nombre(racine, "Financial/Amounts/Totals_taxes"),
    }
    if not document["devise"]:
        diagnostics.append(("alerte", "devise_absente", "Devise de la facture absente : comparaisons limitées.",
                            None, None, None))

    # Détail des taxes globales : conservé seulement s'il existe vraiment.
    taxes_globales = []
    for rang, ligne in enumerate(racine.findall("Global_taxes/Global_tax_item"), 1):
        if len(ligne) and any((c.text or "").strip() for c in ligne):
            taxes_globales.append({"rang": rang, "code": _texte(ligne, "Global_tax_code"),
                                   "base": nombre(ligne, "Global_tax_base"), "taux": nombre(ligne, "Global_tax_rate"),
                                   "montant": nombre(ligne, "Global_tax_amount")})

    articles = []
    for position, item in enumerate(racine.findall("Item"), 1):
        i = lambda chemin: _texte(item, chemin)
        n = lambda chemin: nombre(item, chemin, position)
        article = {
            "position": position,
            "code": i("Tarification/HScode/Commodity_code"),
            "precision_1": i("Tarification/HScode/Precision_1"),
            "precision_4": i("Tarification/HScode/Precision_4"),
            "designation": i("Goods_description/Description_of_goods"),
            "description_commerciale": i("Goods_description/Commercial_Description"),
            "procedure_etendue": i("Tarification/Extended_customs_procedure"),
            "procedure_nationale": i("Tarification/National_customs_procedure"),
            "pays_origine": i("Goods_description/Country_of_origin_code"),
            "poids_brut": n("Valuation_item/Weight_itm/Gross_weight_itm"),
            "poids_net": n("Valuation_item/Weight_itm/Net_weight_itm"),
            "fob": n("Tarification/Item_price"),
            "colis": n("Packages/Number_of_packages"),
            "facture_monnaie_nationale": n("Valuation_item/Item_Invoice/Amount_national_currency"),
            "fret_monnaie_nationale": n("Valuation_item/item_external_freight/Amount_national_currency"),
            "assurance_monnaie_nationale": n("Valuation_item/item_insurance/Amount_national_currency"),
            "cout_total": n("Valuation_item/Total_cost_itm"),
            "cif": n("Valuation_item/Total_CIF_itm"),
            "valeur_statistique": n("Valuation_item/Statistical_value"),
            "coefficient_repartition": n("Valuation_item/Alpha_coeficient_of_apportionment"),
            "taxes_article": n("Taxation/Item_taxes_amount"),
        }
        valeurs = [article[c] for c in ("fob", "poids_brut", "colis")]
        if not article["code"] and not article["designation"] and all(x in (None, "0") for x in valeurs):
            continue  # ligne entièrement vide du formulaire SYDONIA
        article["designation_normalisee"] = normaliser(article["designation"])
        fob, poids = article["fob"], article["poids_brut"]
        if fob is not None and poids is not None and Decimal(fob) > 0 and Decimal(poids) > 0:
            article["ratio"] = decimal_canonique((Decimal(fob) / Decimal(poids)).quantize(Decimal("1E-10")))
        else:
            article["ratio"] = None
            diagnostics.append(("alerte", "article_partiel",
                                f"Art. {position} : FOB ou poids absent/non positif ; ratio non calculable.",
                                position, None, None))
        if not article["code"] or not article["designation"]:
            diagnostics.append(("alerte", "identification_incomplete",
                                f"Art. {position} : code ou désignation manquant ; rapprochement incertain.",
                                position, None, None))
        article["taxes"] = []
        for rang, ligne in enumerate(item.findall("Taxation/Taxation_line"), 1):
            code = _texte(ligne, "Duty_tax_code")
            montant = nombre(ligne, "Duty_tax_amount", position)
            if not code:
                if montant not in (None, "0"):
                    diagnostics.append(("alerte", "taxe_sans_code",
                                        f"Art. {position}, ligne {rang} : montant sans code de taxe.",
                                        position, None, montant))
                continue
            article["taxes"].append({"rang": rang, "code": code, "base": nombre(ligne, "Duty_tax_Base", position),
                                     "taux": nombre(ligne, "Duty_tax_rate", position), "montant": montant,
                                     "mode_paiement": _texte(ligne, "Duty_tax_MP"),
                                     "type_calcul": _texte(ligne, "Duty_tax_Type_of_calculation")})
        articles.append(article)

    if not articles:
        raise ValueError("aucun article renseigné dans ce XML")
    document["nb_articles"] = len(articles)
    diagnostics += controles(valorisation, articles, document)
    return {"document": document, "valorisation": valorisation, "articles": articles,
            "taxes_globales": taxes_globales, "diagnostics": diagnostics}


def controles(valorisation, articles, document):
    """Cohérence entre articles et totaux. Rien n'est corrigé : on signale seulement."""
    sortie = []

    def somme(valeurs):
        valeurs = list(valeurs)
        return None if any(x is None for x in valeurs) else sum((Decimal(x) for x in valeurs), Decimal(0))

    for libelle, cle_article, cle_total, tolerance in (
            ("FOB", "fob", "fob_total", TOLERANCES["fob"]),
            ("Poids", "poids_brut", "poids_total", TOLERANCES["poids"]),
            ("Colis", "colis", "colis_total", TOLERANCES["colis"])):
        calcule, declare = somme(a[cle_article] for a in articles), valorisation[cle_total]
        if calcule is not None and declare is not None and abs(calcule - Decimal(declare)) > tolerance:
            sortie.append(("alerte", f"total_{cle_article}",
                           f"{libelle} : somme des articles différente du total déclaré (tolérance {tolerance}).",
                           None, decimal_canonique(calcule), declare))
    for a in articles:
        lignes = somme(t["montant"] for t in a["taxes"])
        if a["taxes"] and lignes is not None and a["taxes_article"] is not None \
                and abs(lignes - Decimal(a["taxes_article"])) > TOLERANCES["taxes"]:
            sortie.append(("alerte", "taxes_article", f"Art. {a['position']} : somme des lignes de taxes différente "
                           "du total de l'article.", a["position"], decimal_canonique(lignes), a["taxes_article"]))
    taxes_articles = somme(a["taxes_article"] for a in articles)
    if None not in (taxes_articles, valorisation["taxes_globales"], valorisation["taxes_totales"]):
        calcule = taxes_articles + Decimal(valorisation["taxes_globales"])
        if abs(calcule - Decimal(valorisation["taxes_totales"])) > TOLERANCES["taxes"]:
            sortie.append(("alerte", "taxes_totales", "Taxes des articles + taxes globales différentes du total "
                           "des taxes déclaré.", None, decimal_canonique(calcule), valorisation["taxes_totales"]))
    declares = document["nb_articles_declares"]
    if declares is not None and Decimal(declares) != len(articles):
        sortie.append(("info", "nombre_articles", "Nombre d'articles renseignés différent du nombre déclaré.",
                       None, str(len(articles)), declares))
    vus = {}
    for a in articles:
        cle = (a["code"], a["designation_normalisee"])
        if cle in vus:
            sortie.append(("info", "article_repete", f"Art. {a['position']} : même code et désignation que "
                           f"l'art. {vus[cle]} ; les deux occurrences sont conservées.", a["position"], None, None))
        vus.setdefault(cle, a["position"])
    return sortie


# --------------------------------------------------------------------------
# Import dans la base
# --------------------------------------------------------------------------
def lister_xml(dossier):
    return sorted(p for p in Path(dossier).rglob("*") if p.is_file() and p.suffix.lower() == ".xml")


def _archiver(contenu, empreinte, sources):
    cible = sources / empreinte[:2] / f"{empreinte}.xml"
    if not cible.exists():
        cible.parent.mkdir(parents=True, exist_ok=True)
        temporaire = cible.with_suffix(".tmp")
        temporaire.write_bytes(contenu)
        os.replace(temporaire, cible)
    return cible


def _inserer(conn, table, valeurs):
    colonnes = list(valeurs)
    curseur = conn.execute(f"INSERT INTO {table} ({', '.join(colonnes)}) VALUES ({', '.join('?' * len(colonnes))})",
                           [valeurs[c] for c in colonnes])
    return curseur.lastrowid


def importer_fichier(conn, chemin, lot_id=None, origine="importe"):
    """Importe un XML. Renvoie (« importe » | « doublon », id du document). Lève ValueError si refusé."""
    chemin = Path(chemin)
    contenu = chemin.read_bytes()
    empreinte = hashlib.sha256(contenu).hexdigest()
    existant = conn.execute("SELECT id FROM documents WHERE sha256 = ?", (empreinte,)).fetchone()
    if existant:
        conn.execute("INSERT OR IGNORE INTO document_sources (document_id, chemin, nom, lot_id, vu_le) "
                     "VALUES (?, ?, ?, ?, ?)", (existant["id"], str(chemin.resolve()), chemin.name, lot_id, maintenant()))
        return "doublon", existant["id"]
    donnees = extraire(contenu)
    archive = _archiver(contenu, empreinte, base.dossier_sources(conn))
    conn.execute("BEGIN")
    try:
        document_id = _inserer(conn, "documents", {
            "sha256": empreinte, "nom_initial": chemin.name, "archive": str(archive), "origine": origine,
            "lot_id": lot_id, "importe_le": maintenant(), "version_parseur": VERSION_PARSEUR, **donnees["document"]})
        _inserer(conn, "document_sources", {"document_id": document_id, "chemin": str(chemin.resolve()),
                                            "nom": chemin.name, "lot_id": lot_id, "vu_le": maintenant()})
        _inserer(conn, "valuations", {"document_id": document_id, **donnees["valorisation"]})
        for a in donnees["articles"]:
            article_id = _inserer(conn, "articles", {"document_id": document_id,
                                                     **{k: x for k, x in a.items() if k != "taxes"}})
            for t in a["taxes"]:
                _inserer(conn, "tax_lines", {"article_id": article_id, **t})
        for t in donnees["taxes_globales"]:
            _inserer(conn, "global_tax_lines", {"document_id": document_id, **t})
        for gravite, code, explication, position, calcule, declare in donnees["diagnostics"]:
            _inserer(conn, "diagnostics", {"lot_id": lot_id, "document_id": document_id, "article_position": position,
                                           "fichier": chemin.name, "gravite": gravite, "code": code,
                                           "explication": explication, "valeur_calculee": calcule,
                                           "valeur_declaree": declare})
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return "importe", document_id


def importer_lot(chemins, conn=None, origine="importe", nom_lot=None, progression=None, annulation=None):
    """Importe une liste de XML. progression(bilan, chemin) est appelée après chaque fichier ;
    annulation() renvoie True pour s'arrêter entre deux documents (les précédents restent importés)."""
    propre = conn is None
    conn = conn or base.ouvrir()
    chemins = list(chemins)
    bilan = BilanImport(trouves=len(chemins))
    bilan.lot_id = _inserer(conn, "import_batches", {"origine": nom_lot, "debut": maintenant(),
                                                     "trouves": len(chemins), "etat": "en_cours"})
    try:
        for chemin in chemins:
            if annulation and annulation():
                bilan.etat = "annule"
                break
            try:
                resultat, document_id = importer_fichier(conn, chemin, bilan.lot_id, origine)
                bilan.documents_traites.append(document_id)
                if resultat == "importe":
                    bilan.importes += 1
                    bilan.documents.append(document_id)
                else:
                    bilan.doublons += 1
            except Exception as exc:  # noqa: BLE001 - un fichier refusé n'arrête pas le lot
                bilan.refuses += 1
                bilan.refus.append((Path(chemin).name, str(exc)))
                _inserer(conn, "diagnostics", {"lot_id": bilan.lot_id, "fichier": Path(chemin).name,
                                               "gravite": "erreur", "code": "fichier_refuse", "explication": str(exc)})
            bilan.traites += 1
            if progression:
                progression(bilan, chemin)
        else:
            bilan.etat = "termine"
    except BaseException:
        bilan.etat = "interrompu"
        raise
    finally:
        conn.execute("UPDATE import_batches SET fin = ?, traites = ?, importes = ?, doublons = ?, refuses = ?, "
                     "etat = ? WHERE id = ?", (maintenant(), bilan.traites, bilan.importes, bilan.doublons,
                                               bilan.refuses, bilan.etat, bilan.lot_id))
        if propre:
            conn.close()
    return bilan


def main(arguments):
    """Ligne de commande : .venv/bin/python import_references.py <dossier ou fichiers XML>..."""
    chemins = []
    for argument in arguments:
        chemins += lister_xml(argument) if Path(argument).is_dir() else [Path(argument)]
    if not chemins:
        print("Usage : .venv/bin/python import_references.py <dossier ou fichiers XML>...")
        return 1
    afficher = lambda b, chemin: print(f"\r{b.traites}/{b.trouves}  {Path(chemin).name[:60]:60}", end="", flush=True)
    bilan = importer_lot(chemins, nom_lot=" ".join(arguments), progression=afficher)
    print(f"\nLot {bilan.lot_id} ({bilan.etat}) : {bilan.importes} importé(s), {bilan.doublons} doublon(s), "
          f"{bilan.refuses} refusé(s). Base : {base.BASE}")
    for fichier, raison in bilan.refus:
        print(f"  ✘ {fichier} : {raison}")
    return 1 if bilan.refuses else 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
