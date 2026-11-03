"""Rangement des fichiers existants (ancienne organisation DEC FRIPERIE) dans le dossier de travail.

Copie seulement : les originaux restent à leur place. planifier() calcule ce qui sera fait, sans rien
écrire ; executer() réalise les copies et laisse un compte rendu dans 2 - RAPPORTS.

Classement d'un XML, du signe le plus sûr au moins sûr :
1. déclaration réelle (connue, ou numéro d'enregistrement propre au fichier) -> 4 - DECLARATIONS REELLES ;
2. dossier d'origine reconnu (1 - HISTORIQUE, 4 - XML VALIDES, 2 - VOS FICHIERS…) -> type correspondant ;
3. autre XML lisible -> 1 - BASES SYDONIA de son importateur.
L'importateur se lit dans le XML. Un fichier illisible, ou un PDF/Word hors d'un dossier d'importateur,
va dans 3 - A TRIER en gardant son chemin d'origine.
"""
from datetime import datetime
from pathlib import Path
import shutil

from asydec import chemins
from asydec.declarations import detection_reelles
from asydec.declarations import generer
from asydec.declarations import modeles_generes as service
from asydec.systeme import espace_travail

EXTENSIONS = {'.xml', '.pdf', '.docx', '.xlsx'}
# Ancien nom de sous-dossier -> type de fichier (clé de espace_travail.RANGEMENT).
DOSSIERS_CONNUS = {**{nom: cle for cle, nom in espace_travail.ANCIEN_RANGEMENT.items()},
                   'COPARAISON': 'reelles', '1 - A UTILISER': 'sources',
                   '2 - ARCHIVES (fichiers utilises)': 'sources', '3 - A ESSAYER': 'sources'}
PAR_EXTENSION = {'.pdf': 'pdf', '.docx': 'factures'}
LIBELLES = {'reelles': 'Déclaration réelle', 'historique': 'Déclaration générée', 'valides': 'XML validé',
            'sources': 'Base SYDONIA', 'pdf': 'PDF', 'factures': 'Facture', 'rapports': 'Rapport Excel',
            'a_trier': 'À trier'}


def _sources(sources):
    """Fichiers à ranger : hors du logiciel et hors du dossier de travail lui-même."""
    racine = espace_travail.racine()
    for dossier in sources:
        for chemin in sorted(Path(dossier).rglob('*')):
            if not chemin.is_file() or chemin.suffix.lower() not in EXTENSIONS or chemin.name.startswith('.'):
                continue
            resolu = chemin.resolve()
            if chemins.RACINE in resolu.parents or (racine is not None and racine in resolu.parents):
                continue
            yield Path(dossier), chemin


def _importateur_du_chemin(dossier, chemin, connus):
    """Dossier d'importateur de l'ancienne organisation qui contient ce fichier, s'il y en a un."""
    relatif = chemin.relative_to(dossier).parts
    return relatif[0] if len(relatif) > 1 and relatif[0] in connus else None


def planifier(sources=None, table_imp=None, base=None):
    """Liste des copies prévues : dicts source, destination, categorie, importateur, deja, raison.
    deja = True : un fichier identique est déjà rangé à cet endroit (rien ne sera copié)."""
    racine = espace_travail.racine()
    if racine is None:
        raise ValueError('Choisissez d’abord le dossier de travail.')
    sources = [Path(s) for s in (sources or [generer.DEC])]
    table = generer.IMPORTATEURS_DEFAUT if table_imp is None else table_imp
    fichiers = {p: None for _, p in _sources(sources)}
    xml = detection_reelles._fichiers(sources)
    par_chemin = {chemin: (sha, donnees) for sha, (chemin, donnees, _) in xml.items()}
    _, bases, _ = detection_reelles._modeles_exportes(base)
    reelles = (detection_reelles.empreintes_reelles(xml, set(bases.values()), service.empreintes_exports(base=base))
               | {d['sha256'] for d in service.declarations_reelles(base=base)})
    # Dossiers d'importateurs de l'ancienne organisation : ceux qui contiennent un sous-dossier connu.
    importateurs_anciens = {p.name for s in sources if s.is_dir() for p in s.iterdir()
                            if p.is_dir() and any((p / n).is_dir() for n in DOSSIERS_CONNUS)}
    plan, deja_vus = [], set()
    for dossier, chemin in _sources(sources):
        sha, donnees = par_chemin.get(chemin, (None, None))
        cle_doublon = sha or espace_travail._empreinte(chemin)
        if cle_doublon in deja_vus:
            continue  # même contenu déjà prévu depuis un autre dossier
        deja_vus.add(cle_doublon)
        parent = chemin.parent.name
        importateur, raison = None, ''
        if chemin.suffix.lower() == '.xml':
            if donnees is None:
                categorie, raison = 'a_trier', 'XML illisible ou non ASYCUDA'
            else:
                nom_importateur = donnees['document'].get('importateur')
                importateur = generer.nom_dossier(nom_importateur, table) if nom_importateur else None
                if sha in reelles:
                    categorie, raison = 'reelles', 'Numéro d’enregistrement SYDONIA propre au fichier'
                elif parent in DOSSIERS_CONNUS:
                    categorie, raison = DOSSIERS_CONNUS[parent], f'Dossier d’origine « {parent} »'
                else:
                    categorie, raison = 'sources', 'XML de dossier non classé : rangé comme base'
                if importateur is None:
                    categorie, raison = 'a_trier', 'Importateur absent du XML'
        elif chemin.suffix.lower() == '.xlsx':
            categorie, raison = 'rapports', 'Classeur Excel'
        else:
            importateur = _importateur_du_chemin(dossier, chemin, importateurs_anciens)
            categorie = PAR_EXTENSION[chemin.suffix.lower()] if importateur else 'a_trier'
            raison = f'Dossier d’importateur « {importateur} »' if importateur else 'Importateur inconnu'
        if categorie == 'a_trier':
            cible = racine / espace_travail.A_TRIER / chemin.relative_to(dossier).parent
        elif categorie == 'rapports':
            cible = racine / espace_travail.RAPPORTS / 'Anciens'
        else:
            cible = racine / espace_travail.IMPORTATEURS / importateur / espace_travail.RANGEMENT[categorie]
        destination, deja = espace_travail.destination_libre(cible, chemin.name, chemin)
        plan.append(dict(source=chemin, destination=destination, categorie=categorie,
                         importateur=importateur or '', deja=deja, raison=raison))
    return plan


def executer(plan):
    """Copie les fichiers du plan (jamais d'écrasement, originaux intacts). Renvoie (copiés, compte rendu)."""
    copies, lignes = 0, []
    for p in plan:
        if p['deja']:
            lignes.append(f"déjà rangé   {p['source']}  ->  {p['destination']}")
            continue
        destination, deja = espace_travail.destination_libre(p['destination'].parent, p['source'].name, p['source'])
        if not deja:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p['source'], destination)
            copies += 1
        lignes.append(f"{LIBELLES[p['categorie']]:<20} {p['source']}  ->  {destination}")
    compte_rendu = None
    dossier = espace_travail.dossier_rapports()
    if dossier is not None:
        compte_rendu = dossier / f'Rangement des fichiers existants {datetime.now():%Y-%m-%d %H%M%S}.txt'
        compte_rendu.write_text(f'{copies} fichier(s) copié(s). Les originaux sont restés en place.\n\n'
                                + '\n'.join(lignes) + '\n', encoding='utf-8')
    return copies, compte_rendu
