"""Correction versionnée du dossier d'un modèle : aperçu sans écriture, puis nouvelle validation."""
import copy
from dataclasses import dataclass
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from asydec.calcul import moteur, variantes
from asydec.declarations import modeles_generes as modeles

MODES = {'importateur': 'Importateur uniquement', 'base': 'Remplacer la base du dossier'}


@dataclass(frozen=True)
class Apercu:
    modele_id: int
    mode: str
    donneur: bytes
    source: bytes
    resultat: dict
    changements: tuple
    dernier_evenement: int


def _informations(racine, resume=None):
    info = moteur.infos_dossier(racine)
    valeurs = [('Importateur', info['importateur']), ('Code importateur', info['code']),
               ('Nom / adresse importateur', moteur._txt(racine, 'Traders/Consignee/Consignee_name')),
               ('Référence', info['reference']), ('Camion', info['camion']),
               ('Manifeste', info['manifeste']),
               ('Devise', moteur._txt(racine, 'Valuation/Gs_Invoice/Currency_code')),
               ('Taux de change', info['taux']),
               ('Fret en devise', moteur._txt(racine, 'Valuation/Gs_external_freight/Amount_foreign_currency')),
               ('Assurance en devise', moteur._txt(racine, 'Valuation/Gs_insurance/Amount_foreign_currency'))]
    if resume:
        valeurs += [('Taxes articles CDF', resume['taxes_articles']), ('Taxes globales CDF', resume['taxes_globales']),
                    ('Total taxes CDF', resume['taxes_totales'])]
    return dict(valeurs)


def preparer(identifiant, donneur, mode='importateur', base=None):
    """donneur : contenu XML ou chemin. Conserve exactement la répartition du modèle initial."""
    if mode not in MODES:
        raise ValueError('Type de correction inconnu.')
    d = modeles.detail(identifiant, base)
    if d['supprime']:
        raise ValueError('Restaurez le modèle avant de corriger son dossier.')
    contenu = donneur if isinstance(donneur, bytes) else Path(donneur).read_bytes()
    bon = ET.fromstring(contenu)
    importateur = bon.find('Traders/Consignee')
    if importateur is None or not moteur._txt(importateur, 'Consignee_name') or not moteur._txt(importateur, 'Consignee_code'):
        raise ValueError('Le bon XML doit renseigner le nom et le code de l’importateur.')
    ancien = ET.fromstring(d['base_xml'])
    if mode == 'importateur':
        nouveau = copy.deepcopy(ancien)
        traders = nouveau.find('Traders')
        mauvais = nouveau.find('Traders/Consignee')
        if traders is None or mauvais is None:
            raise ValueError('Le modèle ne contient pas de champ importateur remplaçable.')
        position = list(traders).index(mauvais)
        traders.remove(mauvais)
        traders.insert(position, copy.deepcopy(importateur))
        if d['plaque'] and d['plaque'] != moteur.infos_dossier(nouveau)['camion']:
            moteur.ecrire_plaque(nouveau, d['plaque'])
    else:
        if variantes.signature_racine(ancien) != variantes.signature_racine(bon):
            raise ValueError('Base incompatible : mêmes positions tarifaires, marchandises, ordre des articles et devise requis.')
        nouveau = copy.deepcopy(bon)
    source = ET.tostring(nouveau, encoding='utf-8', xml_declaration=True)
    r = d['resultat']
    lignes = [(a['fob'], a['poids']) for a in r['resume']['articles']]
    arbre = ET.ElementTree(nouveau)
    resume = moteur.recalculer(arbre, lignes, r['colis'])
    info = moteur.infos_dossier(nouveau)
    if not info['taux'] > 0:
        raise ValueError('Le taux de change du dossier doit être positif.')
    nom = f'Correction modele {identifiant}.xml'
    resultat = {'nom':nom, 'chemin':nom, 'resume':resume,
                'fob':[f for f, _ in lignes], 'colis':list(r['colis']), 'info':info,
                'mode':'SAISI', 'alertes':['Dossier corrigé : nouvelle version à valider.']}
    resultat['reference'] = copy.deepcopy(r.get('reference') or {'nom':d['nom'], 'sha256':modeles._sha(d['base_xml'])})
    if mode == 'importateur':
        if d['plaque']:
            resultat['plaque'] = d['plaque']
    # L'identité de l'ancienne plaque saisie doit aussi apparaître dans l'aperçu.
    avant = _informations(ancien, r['resume'])
    avant['Camion'] = d['plaque'] or avant['Camion']
    apres = _informations(nouveau, resume)
    changements = tuple((cle, avant[cle], apres[cle]) for cle in avant)
    if mode == 'importateur' and all(avant[k] == apres[k] for k in ('Importateur', 'Code importateur')) and \
            ET.tostring(ancien.find('Traders/Consignee')) == ET.tostring(importateur):
        raise ValueError('Cet importateur est déjà celui du modèle.')
    return Apercu(identifiant, mode, contenu, source, resultat, changements, d['evenements'][-1]['id'])


def enregistrer(apercu, auteur, motif, base=None):
    """Recalcule depuis les XML de l'aperçu et lie les deux versions dans une transaction unique."""
    auteur = modeles._auteur(auteur)
    motif = (motif or '').strip()
    if not motif:
        raise ValueError('Indiquez le motif de la correction.')
    verifie = preparer(apercu.modele_id, apercu.donneur, apercu.mode, base)
    if verifie.source != apercu.source or verifie.resultat != apercu.resultat:
        raise ValueError('Le modèle a changé : actualisez l’aperçu avant d’enregistrer.')
    resultat = copy.deepcopy(verifie.resultat)
    resultat['correction'] = {'modele_initial':apercu.modele_id, 'mode':apercu.mode,
                              'motif':motif, 'donneur_sha256':modeles._sha(apercu.donneur)}
    lignes = [(a['fob'], a['poids']) for a in resultat['resume']['articles']]
    xml = modeles._snapshot(verifie.source, resultat, lignes)
    with modeles._connexion(base) as conn:
        conn.execute('BEGIN IMMEDIATE')
        dernier = conn.execute('SELECT MAX(id) FROM evenements WHERE modele_id=?', (apercu.modele_id,)).fetchone()[0]
        if dernier != apercu.dernier_evenement:
            raise ValueError('Le modèle a changé : actualisez l’aperçu avant d’enregistrer.')
        horodatage = modeles._maintenant()
        empreinte = modeles._sha((str(apercu.modele_id)+horodatage+modeles._sha(xml)).encode())
        curseur = conn.execute('INSERT INTO modeles(empreinte,cree_utc,auteur,importateur,nom,resultat_json,base_xml,modele_xml) '
            'VALUES(?,?,?,?,?,?,?,?)', (empreinte,horodatage,auteur,resultat['info']['importateur'],resultat['nom'],
            json.dumps(resultat, ensure_ascii=False, sort_keys=True, allow_nan=False),verifie.source,xml))
        nouveau = curseur.lastrowid
        modeles._evenement(conn, nouveau, auteur, modeles.CREATION, 'en_attente')
        detail = json.dumps({'modele_initial':apercu.modele_id, 'modele_corrige':nouveau,
                             'mode':apercu.mode, 'motif':motif}, ensure_ascii=False)
        modeles._evenement(conn, nouveau, auteur, 'correction_dossier', detail=detail)
        modeles._evenement(conn, apercu.modele_id, auteur, 'version_corrigee', detail=detail)
    return nouveau
