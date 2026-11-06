"""Déclinaison stable des informations E/L/Q sur les parts d'une licence."""
import random
import re


def incrementer(numero, tirage):
    if not numero:
        return ''
    correspondance = re.fullmatch(r'(.*?)(\d+)(\D*)', numero)
    if not correspondance:
        raise ValueError('Les numéros E, liquidation, Q et manifeste doivent contenir une partie numérique pour être incrémentés.')
    prefixe, chiffres, suffixe = correspondance.groups()
    return prefixe + str(int(chiffres) + tirage.randint(1,6)).zfill(len(chiffres)) + suffixe


def completer(licence, tirage=None):
    base = licence.get('informations_declaration')
    parts = licence.get('repartition', {}).get('parts', [])
    if not base or not parts:
        return False
    rng = tirage or random.SystemRandom()
    # Toute modification de la saisie initiale redéfinit la première part.
    premiere = parts[0].get('informations_declaration', {})
    conserver = all(premiere.get(c, '') == v for c,v in base.items() if c not in ('plaque','numero_dec'))
    precedent_e, precedent_l = base.get('numero_e',''), base.get('numero_liquidation','')
    precedent_m = base.get('manifeste','')
    premier_q = base.get('numero_quittance','')
    deuxieme_q = None
    change = False
    for i, part in enumerate(parts):
        ancien = part.get('informations_declaration', {}) if conserver else {}
        if i == 0:
            e,l,q,m = precedent_e,precedent_l,premier_q,precedent_m
        else:
            e = ancien.get('numero_e') if conserver else None
            l = ancien.get('numero_liquidation') if conserver else None
            m = ancien.get('manifeste') if conserver else None
            # Préserver les tirages déjà validés, compléter uniquement les nouvelles parts.
            e = e if e is not None else incrementer(precedent_e,rng)
            l = l if l is not None else incrementer(precedent_l,rng)
            # Les anciennes parts recopiaient le manifeste saisi : les décliner aussi.
            if m is None or (m and m == base.get('manifeste')):
                m = incrementer(precedent_m,rng)
            if i < 5:
                q = premier_q
            else:
                if deuxieme_q is None:
                    deuxieme_q = ancien.get('numero_quittance') if conserver else None
                    if deuxieme_q is None or deuxieme_q == premier_q:
                        deuxieme_q = incrementer(premier_q,rng)
                q = deuxieme_q
        informations = dict(base, numero_e=e, numero_liquidation=l, numero_quittance=q, manifeste=m,
                            numero_dec=licence.get('numero_dec',''), plaque=part.get('plaque',''))
        if part.get('informations_declaration') != informations:
            part['informations_declaration'] = informations
            change = True
        precedent_e,precedent_l,precedent_m=e,l,m
    return change
