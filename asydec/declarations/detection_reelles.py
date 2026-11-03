"""Détection des déclarations SYDONIA réelles dans les dossiers des importateurs, et rattachement
à leur modèle généré. Rien n'est enregistré sans confirmation : voir enregistrer().

Une déclaration réelle se reconnaît à son numéro d'enregistrement SYDONIA, à condition qu'il soit
propre à ce fichier. AsyDec recopie celui du XML de base dans ses sorties : un numéro porté par
plusieurs contenus différents, ou par la base d'un modèle, désigne donc un gabarit, pas une déclaration.
"""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

from asydec import chemins
from asydec.calcul import variantes
from asydec.declarations import comparaison_prediction
from asydec.declarations import modeles_generes as service
from asydec.references.import_references import extraire
from asydec.systeme import espace_travail


def _cle(document):
    """Identité SYDONIA d'une déclaration : bureau, série, numéro et date d'enregistrement."""
    if not document.get('enregistrement_numero'):
        return None
    return (document.get('bureau_code'), document.get('enregistrement_serie'),
            document['enregistrement_numero'], document.get('enregistrement_date_brute'))


def _tracteur(plaque):
    """Plaque du tracteur (avant le « / » de la remorque), normalisée."""
    return ' '.join(str(plaque or '').upper().split('/')[0].split())


def _date_enregistrement(brute):
    """« 11/3/26 » (mois/jour/année SYDONIA) -> date, ou None."""
    try:
        return datetime.strptime(str(brute), '%m/%d/%y').date()
    except ValueError:
        return None


def _fichiers(racines):
    """{sha: (chemin, données extraites, octets)} des XML ASYCUDA lisibles, hors dossier OUTILS.
    Un même contenu présent à plusieurs endroits (copie rangée et original) ne compte qu'une fois."""
    sortie = {}
    for chemin in (c for racine in racines for c in sorted(Path(racine).rglob('*.xml'))):
        if chemins.RACINE == chemin or chemins.RACINE in chemin.parents:
            continue
        try:
            octets = chemin.read_bytes()
            donnees = extraire(octets)
        except (OSError, ValueError):
            continue
        sortie.setdefault(hashlib.sha256(octets).hexdigest(), (chemin, donnees, octets))
    return sortie


def _modeles_exportes(base=None, module=None):
    """(modèles exportés, {id: clé SYDONIA de leur XML de base}, {id: signature des articles})."""
    modeles = [m for m in service.lister(base=base, module=module) if m['exporte']]
    bases, signatures = {}, {}
    for m in modeles:
        source = bytes(service.detail(m['id'], base=base)['base_xml'])
        bases[m['id']] = _cle(extraire(source)['document'])
        signatures[m['id']] = variantes.signature_racine(ET.fromstring(source))
    return modeles, bases, signatures


def empreintes_reelles(fichiers, gabarits, exports=frozenset()):
    """Empreintes des fichiers qui sont des déclarations réelles : numéro d'enregistrement porté par
    ce seul contenu, qui n'est ni la base d'un modèle (gabarits) ni un export AsyDec."""
    contenus_par_cle = defaultdict(set)
    for sha, (_, donnees, _) in fichiers.items():
        cle = _cle(donnees['document'])
        if cle:
            contenus_par_cle[cle].add(sha)
    return {sha for sha, (_, donnees, _) in fichiers.items()
            if (cle := _cle(donnees['document'])) and len(contenus_par_cle[cle]) == 1
            and cle not in gabarits and sha not in exports}


def detecter(racine=None, base=None, module=None):
    """Déclarations réelles pas encore connues, avec le modèle proposé pour chacune.

    Renvoie une liste de dicts : chemin, nom, sha256, camion, importateur, poids, fob, enregistrement,
    liquidee, date, modeles (identifiants possibles, le plus probable d'abord), modele (proposé ou None),
    avertissements (raisons de vérifier avant de confirmer)."""
    fichiers = _fichiers([racine] if racine else espace_travail.emplacements_lecture())
    modeles, bases, signatures = _modeles_exportes(base, module)
    connus = {d['sha256'] for d in service.declarations_reelles(base=base, module=module)}
    reelles = empreintes_reelles(fichiers, set(bases.values()), service.empreintes_exports(base=base)) - connus
    candidats = []
    for sha, (chemin, donnees, octets) in fichiers.items():
        if sha not in reelles:
            continue
        document, valeurs = donnees['document'], donnees['valorisation']
        cle = _cle(document)
        signature = variantes.signature_racine(ET.fromstring(octets))
        date = _date_enregistrement(document.get('enregistrement_date_brute'))
        tracteur = _tracteur(document.get('camion'))
        possibles = [m for m in modeles if tracteur and _tracteur(m['plaque']) == tracteur]
        # Le plus probable : mêmes articles, encore jamais comparé, puis le plus récent (tris stables).
        possibles.sort(key=lambda m: m['cree_utc'], reverse=True)
        possibles.sort(key=lambda m: (signatures[m['id']] != signature, m['comparaisons'] > 0))
        avertissements = []
        modele = possibles[0] if possibles else None
        if modele is not None:
            if signatures[modele['id']] != signature:
                avertissements.append('Articles différents du modèle : à vérifier.')
            cree = datetime.fromisoformat(modele['cree_utc']).astimezone(timezone.utc).date()
            if date and date < cree:
                avertissements.append(f"Enregistrée le {date:%d/%m/%Y}, avant la création du modèle ({cree:%d/%m/%Y}).")
            if len(possibles) > 1:
                avertissements.append(f"{len(possibles)} modèles ont cette plaque : n° "
                                      + ', '.join(str(m['id']) for m in possibles) + '.')
            if modele['comparaisons']:
                avertissements.append(f"Le modèle n° {modele['id']} a déjà {modele['comparaisons']} comparaison(s).")
        candidats.append(dict(
            chemin=str(chemin), nom=chemin.name, sha256=sha, camion=document.get('camion') or '',
            importateur=document.get('importateur') or '', poids=valeurs.get('poids_total'), fob=valeurs.get('fob_total'),
            enregistrement=' '.join(str(x) for x in cle[1:3] if x), liquidee=bool(document.get('liquidation_numero')),
            date=date, modeles=[m['id'] for m in possibles], modele=modele['id'] if modele else None,
            avertissements=avertissements))
    candidats.sort(key=lambda c: (c['modele'] is None, c['nom']))
    return candidats


def enregistrer(candidats, auteur, module='friperie', base=None, table_imp=None):
    """Confirme les candidats choisis : comparaison enregistrée avec leur modèle (candidat['modele']),
    ou déclaration réelle retenue sans modèle. Chaque fichier est d'abord copié dans
    4 - DECLARATIONS REELLES de son importateur (dossier de travail). Renvoie (comparées, retenues, erreurs)."""
    from asydec.declarations import generer
    comparees, retenues, erreurs = 0, 0, []
    for c in candidats:
        try:
            c = dict(c, chemin=generer.ranger_fichier(c['chemin'], c.get('importateur'), 'reelles', table_imp))
            if c.get('modele') is not None:
                export = service.lire_export(c['modele'], base=base)
                rapport = comparaison_prediction.comparer_octets(export, Path(c['chemin']).read_bytes(),
                                                                 f"export du modèle n° {c['modele']}", c['chemin'])
                service.noter_comparaison(c['modele'], c['chemin'], rapport, auteur, base=base)
                comparees += 1
            else:
                service.ajouter_declaration_reelle(c['chemin'], auteur, module=module, base=base)
                retenues += 1
        except (ValueError, OSError) as exc:
            erreurs.append(f"{c['nom']} : {exc}")
    return comparees, retenues, erreurs
