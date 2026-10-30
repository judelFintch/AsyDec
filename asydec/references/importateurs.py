"""Base des importateurs : un par code, tiré automatiquement des XML de la bibliothèque.

Le code et le bloc complet (nom et adresse) viennent du dernier XML lu pour ce code, sans saisie.
Les documents rejetés ou exclus ne servent pas de source, un XML sans code non plus.
"""
from asydec.calcul import moteur
from asydec.references.base_references import maintenant


def libelle(importateur):
    return f"{importateur['nom']}  ·  {importateur['code']}"


def synchroniser(conn):
    """Ajoute les nouveaux importateurs et rafraîchit ceux qui ont un XML plus récent."""
    a_lire = conn.execute(
        "SELECT d.importateur_code AS code, MAX(d.id) AS dernier, d.archive "
        "FROM documents d JOIN document_statuts s ON s.document_id = d.id "
        "LEFT JOIN importateurs i ON i.code = d.importateur_code "
        "WHERE d.importateur_code IS NOT NULL AND s.statut NOT IN ('rejete', 'exclu') "
        "GROUP BY d.importateur_code HAVING dernier > COALESCE(i.document_id, 0)").fetchall()
    for ligne in a_lire:
        try:
            racine = moteur.charger(ligne["archive"]).getroot()
        except (OSError, SyntaxError):  # archive absente : l'importateur sera relu au prochain passage
            continue
        bloc = moteur._txt(racine, "Traders/Consignee/Consignee_name")
        if bloc:
            conn.execute(
                "INSERT INTO importateurs (code, nom, bloc, document_id, mis_a_jour) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (code) DO UPDATE SET nom = excluded.nom, bloc = excluded.bloc, "
                "document_id = excluded.document_id, mis_a_jour = excluded.mis_a_jour",
                (ligne["code"], bloc.splitlines()[0].strip(), bloc, ligne["dernier"], maintenant()))


def lister(conn):
    """Importateurs connus, par ordre alphabétique ; la base est d'abord mise à jour."""
    synchroniser(conn)
    return [dict(l) for l in conn.execute("SELECT code, nom, bloc FROM importateurs ORDER BY nom COLLATE NOCASE")]
