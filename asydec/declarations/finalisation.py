"""Étape 10 : finalisation du dossier, qui passe « en attente d'archivage ».

Un dossier ne se finalise que si tous ses documents sont produits et à jour. La finalisation retient
une empreinte des documents : si l'un d'eux est régénéré ensuite, le dossier repasse « à finaliser ».
"""
from datetime import datetime, timezone
import hashlib
import json

from asydec.declarations import cvi, declaration_licence, facture_licence, mise_a_jour_repartitions

EN_COURS = 'en_cours'
EN_ATTENTE_ARCHIVAGE = 'en_attente_archivage'
A_REFAIRE = 'a_refaire'
LIBELLES = {EN_COURS: 'En cours', EN_ATTENTE_ARCHIVAGE: 'En attente d’archivage',
            A_REFAIRE: 'Finalisation à refaire'}


def _nombre_parts(licence):
    return len(((licence.get('repartition') or {}).get('parts')) or [])


def controles(licence):
    """[(libellé, réussi, bloquant)] : ce qui doit être vrai avant de finaliser."""
    parts = _nombre_parts(licence)
    recuperation = licence.get('recuperation_simulation') or {}
    declarations = (licence.get('declarations') or {}).get('fichiers') or []
    ecarts = (recuperation.get('resume') or {}).get('controles_differents')
    simules = [str(i.get('libelle') or '') for i in recuperation.get('imports') or [] if i.get('simule')]
    from asydec.declarations.numeros_logiques import parts_hors_regle
    hors_regle = parts_hors_regle(licence)
    return [
        ('Répartition enregistrée', parts > 0, True),
        ('Informations de déclaration saisies', bool(licence.get('informations_declaration')), True),
        ('Liquidation, Q et manifeste inférieurs au E sur toutes les parts' if not hors_regle else
         f'Liquidation, Q ou manifeste ≥ E sur {len(hors_regle)} part(s) : corrigez l’étape 3', not hors_regle, True),
        ('Répartitions mises à jour', mise_a_jour_repartitions.est_a_jour(licence), True),
        ('Factures et packing lists à jour', facture_licence.est_a_jour(licence), True),
        ('CVI et BL à jour', cvi.est_a_jour(licence), True),
        ('XML générés', bool(licence.get('xml_genere')), True),
        ('XML SYDONIA importés', bool(recuperation), True),
        ('Comparaison SYDONIA sans écart' if not ecarts else f'Comparaison SYDONIA : {ecarts} écart(s) à vérifier',
         bool(recuperation) and not ecarts, False),
        ('XML SYDONIA réels pour toutes les parts' if not simules else
         f'{len(simules)} XML de vérification AsyDec (sans SYDONIA) : ' + ', '.join(simules),
         not simules, False),
        (f'Déclarations à jour ({len(declarations)} / {parts} parts)',
         declaration_licence.est_a_jour(licence) and len(declarations) == parts, True),
    ]


def bloquants(licence):
    return [libelle for libelle, reussi, bloquant in controles(licence) if bloquant and not reussi]


def pret(licence):
    return not bloquants(licence)


def empreinte(licence):
    """Empreinte des documents produits : change dès qu'un document est régénéré."""
    def cle(nom, *champs):
        fiche = licence.get(nom) or {}
        return [fiche.get(c) for c in champs]
    sources = dict(
        repartitions=mise_a_jour_repartitions.empreinte(licence) if licence.get('repartition') else None,
        factures=cle('factures_parts', 'genere_le', 'empreinte'),
        cvi=cle('cvi_parts', 'empreinte', 'fichiers'),
        xml=cle('xml_genere', 'genere_le'),
        sydonia=cle('recuperation_simulation', 'importe_le'),
        declarations=cle('declarations', 'genere_le', 'fichiers'))
    texte = json.dumps(sources, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(texte.encode('utf-8')).hexdigest()


def statut(licence):
    fiche = licence.get('finalisation')
    if not fiche:
        return EN_COURS
    try:
        identique = fiche.get('empreinte') == empreinte(licence)
    except (ValueError, KeyError, TypeError):
        identique = False
    return EN_ATTENTE_ARCHIVAGE if identique else A_REFAIRE


def fiche(licence, observation=''):
    """Fiche de finalisation à enregistrer ; ValueError si le dossier n'est pas complet."""
    manquants = bloquants(licence)
    if manquants:
        raise ValueError('Dossier incomplet : ' + ' ; '.join(manquants) + '.')
    return dict(statut=EN_ATTENTE_ARCHIVAGE, finalise_le=datetime.now(timezone.utc).isoformat(),
                empreinte=empreinte(licence), observation=str(observation or '').strip())
