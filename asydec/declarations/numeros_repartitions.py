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


TAILLE_GROUPE_Q = (2, 6)  # parts consécutives partageant un même numéro Q


def _valeur(numero):
    correspondance = re.fullmatch(r'(.*?)(\d+)(\D*)', numero or '')
    return (correspondance.group(1), int(correspondance.group(2)), correspondance.group(3)) if correspondance else None


def tailles_groupes(nombre, tirage):
    """Tailles aléatoires de 2 à 6 dont la somme vaut « nombre », sans groupe isolé d'une seule part
    (sauf s'il n'y a qu'une part)."""
    mini, maxi = TAILLE_GROUPE_Q
    tailles, reste = [], nombre
    while reste > 0:
        if reste < mini:
            tailles.append(reste)
            break
        possibles = [t for t in range(mini, min(maxi, reste) + 1) if reste - t == 0 or reste - t >= mini]
        taille = tirage.choice(possibles)
        tailles.append(taille)
        reste -= taille
    return tailles


def _segments(dates):
    """Indices de début et de fin des suites de parts consécutives à la même date de quittance."""
    segments, debut = [], 0
    for i in range(1, len(dates) + 1):
        if i == len(dates) or dates[i] != dates[debut]:
            segments.append((debut, i))
            debut = i
    return segments


def quittances_valides(quittances, premier_q, dates):
    """True si les Q forment des groupes consécutifs de 2 à 6 parts (même date), croissants de +1 à +6."""
    if not quittances or quittances[0] != premier_q or any(not q for q in quittances):
        return False
    groupes, debut = [], 0
    for i in range(1, len(quittances) + 1):
        if i == len(quittances) or quittances[i] != quittances[debut]:
            groupes.append((debut, i))
            debut = i
    mini, maxi = TAILLE_GROUPE_Q
    for numero, (a, b) in enumerate(groupes):
        if any(dates[k] != dates[a] for k in range(a, b)):
            return False
        segment = next(s for s in _segments(dates) if s[0] <= a < s[1])
        if not (mini <= b - a <= maxi or (b - a == segment[1] - segment[0] < mini)):
            return False
        if numero:
            avant, apres = _valeur(quittances[groupes[numero - 1][0]]), _valeur(quittances[a])
            if not avant or not apres or avant[0] != apres[0] or avant[2] != apres[2] or not 1 <= apres[1] - avant[1] <= 6:
                return False
    return True


def tirer_quittances(premier_q, dates, tirage):
    """Un Q par groupe aléatoire de 2 à 6 parts consécutives ; un changement de date ouvre un groupe."""
    quittances, courant = [], None
    for debut, fin in _segments(dates):
        for taille in tailles_groupes(fin - debut, tirage):
            courant = premier_q if courant is None else incrementer(courant, tirage)
            quittances += [courant] * taille
    return quittances


def _sous(numero, e, precedent, tirage):
    """Liquidation ou manifeste d'une part ramené sous le E de la part (toujours inférieur),
    en restant après celui de la part précédente quand c'est possible."""
    a, b = _valeur(numero), _valeur(e)
    if not a or not b or a[1] < b[1]:
        return numero
    plancher = (_valeur(precedent)[1] + 1) if precedent and _valeur(precedent) else 1
    if plancher > b[1] - 1:
        return numero  # impossible sans casser l'ordre : la saisie de la part 1 est à revoir
    cible = max(plancher, b[1] - tirage.randint(1, 3))
    return a[0] + str(cible).zfill(len(str(a[1]))) + a[2]


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
    change = False
    # Q : groupes aléatoires de parts consécutives à la même date ; tirage conservé s'il reste conforme.
    dates_q = [base.get('date_quittance', '')] * len(parts)
    anciennes_q = [(p.get('informations_declaration') or {}).get('numero_quittance', '') for p in parts] if conserver else []
    if not premier_q:
        quittances = [''] * len(parts)
    elif conserver and quittances_valides(anciennes_q, premier_q, dates_q):
        quittances = anciennes_q
    else:
        quittances = tirer_quittances(premier_q, dates_q, rng)
    for i, part in enumerate(parts):
        ancien = part.get('informations_declaration', {}) if conserver else {}
        if i == 0:
            e,l,m = precedent_e,precedent_l,precedent_m
        else:
            e = ancien.get('numero_e') if conserver else None
            l = ancien.get('numero_liquidation') if conserver else None
            m = ancien.get('manifeste') if conserver else None
            # Préserver les tirages déjà validés, compléter uniquement les nouvelles parts.
            e = e if e is not None else incrementer(precedent_e,rng)
            # Nouveaux tirages seulement (les numéros déjà validés ne bougent pas) : sous le E de la part.
            l = l if l is not None else _sous(incrementer(precedent_l,rng), e, precedent_l, rng)
            # Les anciennes parts recopiaient le manifeste saisi : les décliner aussi.
            if m is None or (m and m == base.get('manifeste')):
                m = _sous(incrementer(precedent_m,rng), e, precedent_m, rng)
        informations = dict(base, numero_e=e, numero_liquidation=l, numero_quittance=quittances[i], manifeste=m,
                            numero_dec=licence.get('numero_dec',''), plaque=part.get('plaque',''))
        if part.get('informations_declaration') != informations:
            part['informations_declaration'] = informations
            change = True
        precedent_e,precedent_l,precedent_m=e,l,m
    return change
