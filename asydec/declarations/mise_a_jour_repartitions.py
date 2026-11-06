"""Validation explicite des informations de toutes les parts avant export."""
import copy
import hashlib
import json
from datetime import date
from decimal import Decimal
from asydec.declarations import informations_declaration, numeros_repartitions


def exiger_numeros(informations):
    manquants=[nom for cle,nom in (('numero_e','E'),('numero_liquidation','liquidation'),('numero_quittance','Q'))
               if not str(informations.get(cle,'')).strip()]
    if manquants:
        raise ValueError('Numéros obligatoires manquants : '+', '.join(manquants)+'.')


def empreinte(licence):
    donnees=copy.deepcopy(licence)
    donnees.pop('mise_a_jour_repartitions',None)
    # Les XML générés et récupérés ne font pas partie des données à valider.
    donnees.pop('xml_genere',None)
    donnees.pop('recuperation_simulation',None)
    donnees.pop('modele_structure',None)
    # Factures de l'étape 5 et leurs références : elles dépendent de ces données, pas l'inverse.
    for cle in ('factures_parts','cvi_parts','numero_facture','date_facture','declarations'):
        donnees.pop(cle,None)
    for cle in ('date_validation','date_bl'):
        if donnees.get(cle):
            donnees[cle]=informations_declaration.lire_date(donnees[cle]).isoformat()
    def encoder(valeur):
        return valeur.isoformat() if isinstance(valeur,date) else str(valeur)
    contenu=json.dumps(donnees,sort_keys=True,ensure_ascii=False,default=encoder)
    return hashlib.sha256(contenu.encode()).hexdigest()


def est_a_jour(licence):
    informations=licence.get('informations_declaration',{})
    try:
        exiger_numeros(informations)
    except ValueError:
        return False
    return licence.get('mise_a_jour_repartitions',{}).get('empreinte')==empreinte(licence)


def appliquer(licence):
    base=licence.get('informations_declaration',{})
    exiger_numeros(base)
    informations_declaration.verifier(base)
    if not licence.get('repartition',{}).get('parts'):
        raise ValueError('Validez la répartition avant sa mise à jour.')
    numeros_repartitions.completer(licence)
    contexte={cle:copy.deepcopy(licence.get(cle)) for cle in
              ('numero_dec','numero_validation','date_validation','date_bl','soussigne','fournisseur')}
    for part in licence['repartition']['parts']:
        exiger_numeros(part['informations_declaration'])
        part['contexte_licence']=copy.deepcopy(contexte)
    licence['mise_a_jour_repartitions']={'empreinte':empreinte(licence),'parts':len(licence['repartition']['parts'])}
    return licence
