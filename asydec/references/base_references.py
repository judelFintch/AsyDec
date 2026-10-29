"""Base de références SQLite : connexion, migrations versionnées, sauvegarde et restauration.

Les montants, poids et taux sont stockés en texte décimal exact, jamais en flottant :
la valeur lue dans le XML est mise sous forme canonique (« 2.83125E7 » devient
« 28312500 », « 30.0 » devient « 30 ») sans aucun arrondi. Une valeur absente reste NULL.
Les XML sources sont archivés sous leur empreinte SHA-256 dans DONNEES/sources/.
"""
import datetime
import shutil
import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path

from asydec import chemins

DOSSIER = chemins.DONNEES
BASE = DOSSIER / "asydec.db"

MIGRATIONS = [
    (1, "Documents, valorisation, articles, taxes, lots d'import et diagnostics", """
CREATE TABLE import_batches (
    id INTEGER PRIMARY KEY,
    origine TEXT,
    debut TEXT NOT NULL,
    fin TEXT,
    trouves INTEGER NOT NULL DEFAULT 0,
    traites INTEGER NOT NULL DEFAULT 0,
    importes INTEGER NOT NULL DEFAULT 0,
    doublons INTEGER NOT NULL DEFAULT 0,
    refuses INTEGER NOT NULL DEFAULT 0,
    etat TEXT NOT NULL CHECK (etat IN ('en_cours', 'termine', 'annule', 'interrompu'))
);
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    nom_initial TEXT NOT NULL,
    archive TEXT NOT NULL,
    origine TEXT NOT NULL CHECK (origine IN ('importe', 'genere')),
    lot_id INTEGER REFERENCES import_batches(id),
    importe_le TEXT NOT NULL,
    version_parseur INTEGER NOT NULL,
    importateur TEXT, importateur_code TEXT, declarant_reference TEXT,
    manifeste TEXT, camion TEXT, bureau_code TEXT, type_declaration TEXT,
    enregistrement_serie TEXT, enregistrement_numero TEXT, enregistrement_date_brute TEXT,
    liquidation_serie TEXT, liquidation_numero TEXT, liquidation_date_brute TEXT,
    quittance_serie TEXT, quittance_numero TEXT, quittance_date_brute TEXT,
    devise TEXT, nb_articles_declares INTEGER, nb_articles INTEGER NOT NULL
);
CREATE TABLE document_sources (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chemin TEXT NOT NULL,
    nom TEXT NOT NULL,
    lot_id INTEGER REFERENCES import_batches(id),
    vu_le TEXT NOT NULL,
    UNIQUE (document_id, chemin)
);
CREATE TABLE valuations (
    document_id INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    fob_total TEXT, poids_total TEXT, colis_total TEXT,
    devise_facture TEXT, taux_change TEXT, facture_monnaie_nationale TEXT,
    fret_externe_devise TEXT, fret_externe_montant TEXT, fret_externe_monnaie_nationale TEXT,
    fret_interne_monnaie_nationale TEXT,
    assurance_devise TEXT, assurance_montant TEXT, assurance_monnaie_nationale TEXT,
    autres_couts_monnaie_nationale TEXT, deductions_monnaie_nationale TEXT,
    cout_total TEXT, cif_total TEXT,
    taxes_globales TEXT, taxes_manuelles TEXT, taxes_totales TEXT
);
CREATE TABLE articles (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    code TEXT, precision_1 TEXT, precision_4 TEXT,
    designation TEXT, designation_normalisee TEXT, description_commerciale TEXT,
    procedure_etendue TEXT, procedure_nationale TEXT, pays_origine TEXT,
    poids_brut TEXT, poids_net TEXT, fob TEXT, colis TEXT,
    facture_monnaie_nationale TEXT, fret_monnaie_nationale TEXT, assurance_monnaie_nationale TEXT,
    cout_total TEXT, cif TEXT, valeur_statistique TEXT, coefficient_repartition TEXT,
    taxes_article TEXT,
    ratio TEXT,
    UNIQUE (document_id, position)
);
CREATE TABLE tax_lines (
    id INTEGER PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    rang INTEGER NOT NULL,
    code TEXT NOT NULL,
    base TEXT, taux TEXT, montant TEXT, mode_paiement TEXT, type_calcul TEXT,
    UNIQUE (article_id, rang)
);
CREATE TABLE global_tax_lines (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    rang INTEGER NOT NULL,
    code TEXT, base TEXT, taux TEXT, montant TEXT,
    UNIQUE (document_id, rang)
);
CREATE TABLE diagnostics (
    id INTEGER PRIMARY KEY,
    lot_id INTEGER REFERENCES import_batches(id),
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    article_position INTEGER,
    fichier TEXT,
    gravite TEXT NOT NULL CHECK (gravite IN ('info', 'alerte', 'erreur')),
    code TEXT NOT NULL,
    explication TEXT NOT NULL,
    valeur_calculee TEXT,
    valeur_declaree TEXT
);
CREATE INDEX articles_code ON articles(code);
CREATE INDEX articles_designation ON articles(designation_normalisee);
CREATE INDEX documents_importateur ON documents(importateur);
CREATE INDEX documents_devise ON documents(devise);
CREATE INDEX tax_lines_code ON tax_lines(code);
CREATE INDEX diagnostics_document ON diagnostics(document_id);
CREATE INDEX document_sources_document ON document_sources(document_id)
"""),
    (2, "Statuts de validation des documents, historique en ajout seul", """
CREATE TABLE status_events (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    type TEXT NOT NULL CHECK (type IN ('changement', 'correction')),
    ancien TEXT,
    nouveau TEXT NOT NULL CHECK (nouveau IN ('non_verifie', 'accepte', 'rejete', 'exclu')),
    corrige_id INTEGER REFERENCES status_events(id),
    date_effective TEXT,
    preuve TEXT,
    commentaire TEXT,
    auteur TEXT,
    saisi_le TEXT NOT NULL,
    CHECK (nouveau <> 'accepte' OR length(trim(coalesce(preuve, ''))) > 0),
    CHECK (type = 'changement' OR (corrige_id IS NOT NULL AND length(trim(coalesce(commentaire, ''))) > 0))
);
CREATE INDEX status_events_document ON status_events(document_id);
CREATE TRIGGER status_events_sans_modification BEFORE UPDATE ON status_events
BEGIN
    SELECT RAISE(ABORT, 'Historique des statuts : une modification est interdite, ajoutez une correction.');
END;
CREATE TRIGGER status_events_sans_suppression BEFORE DELETE ON status_events
BEGIN
    SELECT RAISE(ABORT, 'Historique des statuts : une suppression est interdite.');
END;
CREATE VIEW document_statuts AS
SELECT d.id AS document_id,
       COALESCE((SELECT e.nouveau FROM status_events e
                 WHERE e.document_id = d.id AND e.type = 'changement'
                 ORDER BY e.id DESC LIMIT 1), 'non_verifie') AS statut
FROM documents d
"""),
    (3, "Classement des XML par module métier", """
CREATE TABLE xml_modules (
    sha256 TEXT PRIMARY KEY,
    module TEXT NOT NULL CHECK (module IN ('friperie', 'divers'))
);
"""),
]


def maintenant():
    """Horodatage technique en UTC ; l'affichage se fait dans le fuseau de Lubumbashi."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def decimal_canonique(texte):
    """Texte décimal exact et canonique, ou None si absent. Lève ValueError si non numérique."""
    if texte is None or not str(texte).strip():
        return None
    try:
        valeur = Decimal(str(texte).strip())
    except InvalidOperation:
        raise ValueError(f"valeur non numérique : {texte!r}") from None
    if not valeur.is_finite():
        raise ValueError(f"valeur non finie : {texte!r}")
    resultat = format(valeur, "f")
    if "." in resultat:
        resultat = resultat.rstrip("0").rstrip(".")
    return "0" if resultat in ("-0", "") else resultat


def ouvrir(chemin=None):
    """Ouvre la base (créée si besoin) et applique les migrations manquantes."""
    chemin = Path(chemin or BASE)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(chemin, isolation_level=None)  # transactions explicites
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrer(conn)
    return conn


def version(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS schema_versions ("
                 "version INTEGER PRIMARY KEY, description TEXT NOT NULL, applique_le TEXT NOT NULL)")
    return conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_versions").fetchone()[0]


def instructions(sql):
    """Découpe un script en instructions complètes (les déclencheurs contiennent des « ; »)."""
    tampon = ""
    for morceau in sql.split(";"):
        tampon += morceau + ";"
        if sqlite3.complete_statement(tampon):
            if tampon.strip(" \n;"):
                yield tampon.strip()
            tampon = ""
    if tampon.strip(" \n;"):
        yield tampon.strip()


def migrer(conn, migrations=None):
    """Applique chaque migration manquante dans sa propre transaction."""
    actuelle = version(conn)
    for numero, description, sql in migrations or MIGRATIONS:
        if numero <= actuelle:
            continue
        conn.execute("BEGIN")
        try:
            for instruction in instructions(sql):
                conn.execute(instruction)
            conn.execute("INSERT INTO schema_versions VALUES (?, ?, ?)", (numero, description, maintenant()))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise


def dossier_sources(conn):
    """Dossier des XML archivés, à côté du fichier de la base."""
    fichier = conn.execute("PRAGMA database_list").fetchone()["file"]
    return Path(fichier).parent / "sources"


def sauvegarder(conn, destination=None):
    """Copie cohérente de la base (API de sauvegarde SQLite) et des XML archivés."""
    if destination is None:
        racine = Path(conn.execute("PRAGMA database_list").fetchone()["file"]).parent
        destination = racine / "sauvegardes" / datetime.datetime.now().strftime("%Y-%m-%d %H%M%S")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    copie = sqlite3.connect(destination / "asydec.db")
    with copie:
        conn.backup(copie)
    copie.close()
    sources = dossier_sources(conn)
    if sources.exists():
        shutil.copytree(sources, destination / "sources")
    return destination


def restaurer(sauvegarde, chemin=None):
    """Remplace la base par une sauvegarde vérifiée. L'état actuel est d'abord sauvegardé."""
    sauvegarde, chemin = Path(sauvegarde), Path(chemin or BASE)
    source = sqlite3.connect(f"file:{sauvegarde / 'asydec.db'}?mode=ro", uri=True)
    try:
        if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("La sauvegarde est endommagée : restauration annulée.")
        precedente = None
        if chemin.exists():
            actuelle = ouvrir(chemin)
            precedente = sauvegarder(actuelle, chemin.parent / "sauvegardes" /
                                     ("avant restauration " + datetime.datetime.now().strftime("%Y-%m-%d %H%M%S")))
            actuelle.close()
        cible = sqlite3.connect(chemin)
        with cible:
            source.backup(cible)
        cible.close()
    finally:
        source.close()
    # Archives nommées par empreinte : un fichier recopié a forcément le même contenu.
    if (sauvegarde / "sources").exists():
        shutil.copytree(sauvegarde / "sources", chemin.parent / "sources", dirs_exist_ok=True)
    return precedente
