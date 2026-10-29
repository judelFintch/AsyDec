"""Service de références : statuts de validation et consultation des documents.

Règles des statuts (lot 4) :
- Un document importé ou généré est « non vérifié » tant que l'utilisateur ne dit rien.
- « Accepté » exige une preuve ou une référence (contrôle aussi imposé par la base).
- « Rejeté », « exclu » et le retour à « non vérifié » exigent un commentaire.
- Le statut porte sur une version précise (empreinte) : un XML modifié est un autre
  document et n'hérite de rien.
- L'historique est en ajout seul : une erreur se corrige par un événement de correction.
"""
import datetime
import getpass

from asydec.references.base_references import maintenant

STATUTS = {"non_verifie": "Non vérifié", "accepte": "Accepté", "rejete": "Rejeté", "exclu": "Exclu des références"}


def _auteur(auteur):
    if auteur:
        return auteur
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 - l'auteur est facultatif
        return None


def _texte(valeur):
    valeur = (valeur or "").strip()
    return valeur or None


def _date(valeur):
    """Date effective saisie : AAAA-MM-JJ, pas dans le futur. None si vide."""
    valeur = _texte(valeur)
    if valeur is None:
        return None
    try:
        jour = datetime.date.fromisoformat(valeur)
    except ValueError:
        raise ValueError(f"Date « {valeur} » invalide : utilisez le format AAAA-MM-JJ.") from None
    if jour > datetime.date.today():
        raise ValueError("La date effective ne peut pas être dans le futur.")
    return jour.isoformat()


def statut(conn, document_id):
    ligne = conn.execute("SELECT statut FROM document_statuts WHERE document_id = ?", (document_id,)).fetchone()
    if ligne is None:
        raise ValueError(f"Document {document_id} introuvable.")
    return ligne["statut"]


def enregistrer_statut(conn, document_id, nouveau, preuve=None, commentaire=None, auteur=None, date_effective=None):
    """Change le statut d'un document. Renvoie l'événement enregistré."""
    if nouveau not in STATUTS:
        raise ValueError(f"Statut inconnu : {nouveau}.")
    ancien = statut(conn, document_id)
    preuve, commentaire = _texte(preuve), _texte(commentaire)
    if nouveau == ancien:
        raise ValueError(f"Le document est déjà « {STATUTS[nouveau]} ».")
    if nouveau == "accepte" and not preuve:
        raise ValueError("Une acceptation exige une preuve ou une référence (numéro d'enregistrement, quittance…).")
    if nouveau != "accepte" and not commentaire:
        raise ValueError(f"Indiquez la raison du passage à « {STATUTS[nouveau]} ».")
    valeurs = (document_id, ancien, nouveau, _date(date_effective), preuve, commentaire, _auteur(auteur), maintenant())
    curseur = conn.execute("INSERT INTO status_events (document_id, type, ancien, nouveau, date_effective, preuve, "
                           "commentaire, auteur, saisi_le) VALUES (?, 'changement', ?, ?, ?, ?, ?, ?, ?)", valeurs)
    return evenement(conn, curseur.lastrowid)


def corriger_evenement(conn, evenement_id, commentaire, date_effective=None, preuve=None, auteur=None):
    """Corrige la date ou la preuve d'un événement passé, sans l'effacer ni changer le statut courant."""
    origine = evenement(conn, evenement_id)
    if not _texte(commentaire):
        raise ValueError("Une correction doit être motivée.")
    if _texte(date_effective) is None and _texte(preuve) is None:
        raise ValueError("Indiquez la date ou la preuve corrigée.")
    if origine["nouveau"] == "accepte" and _texte(preuve) is None:
        preuve = origine["preuve"]  # la preuve d'une acceptation n'est jamais retirée par une correction
    curseur = conn.execute(
        "INSERT INTO status_events (document_id, type, ancien, nouveau, corrige_id, date_effective, preuve, "
        "commentaire, auteur, saisi_le) VALUES (?, 'correction', ?, ?, ?, ?, ?, ?, ?, ?)",
        (origine["document_id"], origine["ancien"], origine["nouveau"], evenement_id, _date(date_effective),
         _texte(preuve), _texte(commentaire), _auteur(auteur), maintenant()))
    return evenement(conn, curseur.lastrowid)


def evenement(conn, evenement_id):
    ligne = conn.execute("SELECT * FROM status_events WHERE id = ?", (evenement_id,)).fetchone()
    if ligne is None:
        raise ValueError(f"Événement {evenement_id} introuvable.")
    return dict(ligne)


def historique_statuts(conn, document_id):
    return [dict(l) for l in conn.execute("SELECT * FROM status_events WHERE document_id = ? ORDER BY id",
                                          (document_id,))]


def preuve_suggeree(conn, document_id):
    """Proposition de preuve tirée du XML (enregistrement, liquidation, quittance).
    Ce n'est qu'une suggestion à confirmer : elle n'accepte jamais rien d'elle-même."""
    d = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if d is None:
        return None
    morceaux = []
    for cle, libelle in (("enregistrement", "Enregistrement"), ("liquidation", "Liquidation"), ("quittance", "Quittance")):
        if d[f"{cle}_numero"]:
            morceaux.append(f"{libelle} {d[f'{cle}_serie'] or ''} {d[f'{cle}_numero']}".replace("  ", " ")
                            + (f" du {d[f'{cle}_date_brute']}" if d[f"{cle}_date_brute"] else ""))
    return " · ".join(morceaux) or None


def lister_documents(conn, statut=None, importateur=None, recherche=None, origine=None):
    """Documents avec leur statut courant et leurs totaux, les plus récemment importés d'abord."""
    conditions, parametres = [], []
    if statut:
        conditions.append("s.statut = ?")
        parametres.append(statut)
    if importateur:
        conditions.append("d.importateur = ?")
        parametres.append(importateur)
    if origine:
        conditions.append("d.origine = ?")
        parametres.append(origine)
    if recherche:
        conditions.append("(d.nom_initial LIKE ? OR d.declarant_reference LIKE ? OR d.camion LIKE ?)")
        parametres += [f"%{recherche}%"] * 3
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return [dict(l) for l in conn.execute(
        f"SELECT d.*, s.statut, v.fob_total, v.poids_total, v.colis_total, v.taxes_totales "
        f"FROM documents d JOIN document_statuts s ON s.document_id = d.id "
        f"LEFT JOIN valuations v ON v.document_id = d.id {where} ORDER BY d.id DESC", parametres)]


def options_filtres(conn):
    """Valeurs proposées dans les listes de filtres."""
    valeurs = lambda sql: [l[0] for l in conn.execute(sql) if l[0]]
    return {"importateurs": valeurs("SELECT DISTINCT importateur FROM documents ORDER BY 1"),
            "devises": valeurs("SELECT DISTINCT devise FROM documents ORDER BY 1")}


def compteurs(conn):
    un = lambda sql: conn.execute(sql).fetchone()[0]
    statuts = dict(conn.execute("SELECT statut, COUNT(*) FROM document_statuts GROUP BY statut").fetchall())
    return {"documents": un("SELECT COUNT(*) FROM documents"),
            "articles": un("SELECT COUNT(*) FROM articles"),
            "observations": un("SELECT COUNT(*) FROM articles WHERE ratio IS NOT NULL"),
            "acceptes": statuts.get("accepte", 0), "non_verifies": statuts.get("non_verifie", 0),
            "rejetes": statuts.get("rejete", 0), "exclus": statuts.get("exclu", 0),
            "anomalies": un("SELECT COUNT(*) FROM diagnostics WHERE document_id IS NOT NULL "
                            "AND gravite IN ('alerte', 'erreur')")}


def detail_document(conn, document_id):
    """Tout ce que la base sait d'un document : valeurs source, taxes, diagnostics, statuts, provenance."""
    document = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if document is None:
        raise ValueError(f"Document {document_id} introuvable.")
    valorisation = conn.execute("SELECT * FROM valuations WHERE document_id = ?", (document_id,)).fetchone()
    articles = []
    for a in conn.execute("SELECT * FROM articles WHERE document_id = ? ORDER BY position", (document_id,)):
        article = dict(a)
        article["taxes"] = [dict(l) for l in conn.execute(
            "SELECT * FROM tax_lines WHERE article_id = ? ORDER BY rang", (a["id"],))]
        articles.append(article)
    requete = lambda sql: [dict(l) for l in conn.execute(sql, (document_id,))]
    return {"document": dict(document), "valorisation": dict(valorisation) if valorisation else {},
            "articles": articles, "statut": statut(conn, document_id),
            "taxes_globales": requete("SELECT * FROM global_tax_lines WHERE document_id = ? ORDER BY rang"),
            "diagnostics": requete("SELECT * FROM diagnostics WHERE document_id = ? ORDER BY id"),
            "historique": historique_statuts(conn, document_id),
            "sources": requete("SELECT * FROM document_sources WHERE document_id = ? ORDER BY id"),
            "preuve_suggeree": preuve_suggeree(conn, document_id)}


def observations(conn, statuts=("accepte",), importateur=None):
    """Ratios observés des documents ayant l'un des statuts demandés, au format de ratios.regrouper.
    Les documents rejetés ou exclus ne sont jamais renvoyés. Les valeurs flottantes ne servent
    qu'aux statistiques affichées ; la base garde les valeurs exactes."""
    autorises = [s for s in statuts if s in ("accepte", "non_verifie")]
    if not autorises:
        return []
    sql = ("SELECT d.id AS document_id, d.nom_initial, d.importateur, d.devise, s.statut, a.position, a.code, "
           "a.designation, a.designation_normalisee, a.poids_brut, a.fob, a.ratio "
           "FROM articles a JOIN documents d ON d.id = a.document_id "
           "JOIN document_statuts s ON s.document_id = d.id "
           f"WHERE a.ratio IS NOT NULL AND s.statut IN ({', '.join('?' * len(autorises))})")
    parametres = list(autorises)
    if importateur:
        sql += " AND d.importateur = ?"
        parametres.append(importateur)
    return [{"document_id": o["document_id"], "fichier": o["nom_initial"], "importateur": o["importateur"] or "",
             "devise": o["devise"] or "NON RENSEIGNEE", "statut": o["statut"], "position": o["position"],
             "code": o["code"] or "", "designation": o["designation"] or "", "poids": float(o["poids_brut"]),
             "fob": float(o["fob"]), "ratio": float(o["ratio"]),
             "groupe": (o["devise"] or "NON RENSEIGNEE", o["code"] or "", o["designation_normalisee"] or "")}
            for o in conn.execute(sql + " ORDER BY d.id, a.position", parametres)]

