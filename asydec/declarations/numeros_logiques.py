"""Proposition logique des numéros E, liquidation, Q et manifeste (étape 3).

Les numéros SYDONIA repartent chaque année et augmentent avec les jours (par bureau). À partir des numéros
déjà connus — autres dossiers (y compris supprimés), XML SYDONIA importés, déclarations réelles de
XML_LICENCES — on propose pour une date donnée un numéro cohérent :

- entre deux dossiers connus de la même année : interpolation selon la date ;
- après (ou avant) les seuls dossiers connus : prolongement au rythme observé cette année-là ;
- sans dossier connu cette année : rythme moyen des autres années × jour de l'année.

Le numéro reste strictement après les dossiers plus anciens (et après ceux du même jour) et laisse,
avant le dossier suivant, la place des incréments des parts (+1 à +6 par part).
"""
from datetime import date, datetime
import json
from pathlib import Path
import random
import re
from statistics import median
import xml.etree.ElementTree as ET

# Type -> (clé du numéro, clé de la date dans les informations de déclaration, libellé, chemins XML)
TYPES = {
    'E': ('numero_e', 'date_enregistrement', 'E',
          ('Identification/Registration/Number', 'Identification/Registration/Date')),
    'L': ('numero_liquidation', 'date_liquidation', 'Liquidation',
          ('Identification/Assessment/Number', 'Identification/Assessment/Date')),
    'Q': ('numero_quittance', 'date_quittance', 'Q',
          ('Identification/receipt/Number', 'Identification/receipt/Date')),
    'M': ('manifeste', 'date_enregistrement', 'Manifeste',
          ('Identification/Manifest_reference_number', 'Identification/Registration/Date')),
}
SOURCE_SAISIE = 'saisie '
INCREMENT_MOYEN = 3.5      # incrément moyen entre deux parts (+1 à +6)
RYTHMES_PAR_DEFAUT = {'E': 40, 'L': 40, 'Q': 20, 'M': 30}  # numéros par jour, sans aucune donnée


def numero(valeur):
    """Partie numérique finale : « E 4567 » -> 4567, « 2026 7628 » -> 7628 ; None sinon."""
    trouve = re.search(r'(\d+)\D*$', str(valeur or '').strip())
    return int(trouve.group(1)) if trouve else None


def lire_date(valeur):
    texte = str(valeur or '').strip()
    formats = ('%m/%d/%y',) if re.fullmatch(r'\d{1,2}/\d{1,2}/\d{2}', texte) else ('%d/%m/%Y', '%Y-%m-%d')
    for format_ in formats:
        try:
            return datetime.strptime(texte, format_).date()
        except ValueError:
            pass
    return None


def _ajouter(points, type_, valeur, jour, bureau, source):
    n, d = numero(valeur), jour if isinstance(jour, date) else lire_date(jour)
    if n is not None and d is not None:
        points.append(dict(type=type_, numero=n, date=d, bureau=str(bureau or '').strip(), source=source))


def points_dossier(licence, source):
    """Numéros connus d'un dossier : chaque part, et ses XML SYDONIA importés.
    Un dossier qui ne respecte pas la règle (liquidation, Q ou manifeste ≥ E) n'est jamais une référence."""
    points = []
    if parts_hors_regle(licence):
        return points
    for part in (licence.get('repartition') or {}).get('parts') or []:
        infos = part.get('informations_declaration') or {}
        e = numero(infos.get('numero_e'))
        for type_, (cle, cle_date, _, _) in TYPES.items():
            # Une liquidation, un Q ou un manifeste ≥ E est une erreur de saisie : jamais une référence.
            if type_ in SOUS_E and e is not None and (numero(infos.get(cle)) or 0) >= e:
                continue
            _ajouter(points, type_, infos.get(cle), infos.get(cle_date), infos.get('bureau_code'), source)
    for i in (licence.get('recuperation_simulation') or {}).get('imports') or []:
        if not i.get('simule'):  # un XML de vérification AsyDec n'apprend rien de réel
            points += points_xml(i.get('contenu') or '', source)
    return points


def points_xml(contenu, source):
    points = []
    try:
        racine = ET.fromstring(contenu) if isinstance(contenu, (str, bytes)) else ET.parse(contenu).getroot()
    except (ET.ParseError, OSError):
        return points
    bureau = racine.findtext('Identification/Office_segment/Customs_clearance_office_code')
    for type_, (_, _, _, (chemin_numero, chemin_date)) in TYPES.items():
        _ajouter(points, type_, racine.findtext(chemin_numero), racine.findtext(chemin_date), bureau, source)
    return points


def dedoublonner(points):
    vus, uniques = set(), []
    for p in points:
        cle = (p['type'], p['numero'], p['date'])
        if cle not in vus:
            vus.add(cle)
            uniques.append(p)
    return uniques


def collecter(licences, dossier_reel=None):
    """Points connus de plusieurs dossiers [(nom, contenu)] et des déclarations réelles ; doublons retirés."""
    points = []
    for nom, licence in licences:
        points += points_dossier(licence, f'dossier {nom}')
    if dossier_reel and Path(dossier_reel).is_dir():
        from asydec.declarations.verification_xml import SUFFIXE
        for fichier in sorted(Path(dossier_reel).glob('*.xml')):
            if SUFFIXE not in fichier.name:
                points += points_xml(fichier, f'déclaration réelle {fichier.name}')
    vus, uniques = set(), []
    for p in points:
        cle = (p['type'], p['numero'], p['date'])
        if cle not in vus:
            vus.add(cle)
            uniques.append(p)
    return uniques


def _jour_annee(jour):
    return jour.timetuple().tm_yday


def rythme(points, type_, annee):
    """Numéros par jour : pente observée cette année, sinon numéro / jour de l'année (médiane)."""
    annee_ = sorted((p for p in points if p['type'] == type_ and p['date'].year == annee), key=lambda p: p['date'])
    pentes = [(b['numero'] - a['numero']) / (b['date'] - a['date']).days
              for a, b in zip(annee_, annee_[1:]) if (b['date'] - a['date']).days >= 7 and b['numero'] > a['numero']]
    if pentes:
        return median(pentes)
    ratios = [p['numero'] / _jour_annee(p['date']) for p in points
              if p['type'] == type_ and p['numero'] > 0 and _jour_annee(p['date']) >= 5]
    if ratios:
        return median(r for r in ratios if r > 0)
    return RYTHMES_PAR_DEFAUT[type_]


def coherents(points):
    """Plus longue suite de points dont le numéro croît avec la date (numéros aberrants écartés)."""
    ordonnes = sorted(points, key=lambda p: (p['date'], p['numero']))
    longueur, precedent = [1] * len(ordonnes), [-1] * len(ordonnes)
    for i, p in enumerate(ordonnes):
        for j in range(i):
            if ordonnes[j]['numero'] <= p['numero'] and longueur[j] + 1 > longueur[i]:
                longueur[i], precedent[i] = longueur[j] + 1, j
    if not ordonnes:
        return []
    i, suite = max(range(len(ordonnes)), key=lambda k: longueur[k]), []
    while i >= 0:
        suite.append(ordonnes[i])
        i = precedent[i]
    return suite[::-1]


def proposer_numero(points, type_, jour, nombre_parts=1, bureau='', tirage=None):
    """(numéro, explication) pour une date ; None sans date."""
    if jour is None:
        return None
    tirage = tirage or random.SystemRandom()
    libelle = TYPES[type_][2]
    candidats = [p for p in points if p['type'] == type_ and p['date'].year == jour.year]
    bureau = str(bureau or '').strip()
    if bureau and any(p['bureau'] == bureau for p in candidats):
        candidats = [p for p in candidats if p['bureau'] in (bureau, '')]
    candidats = coherents(candidats)
    # Place des parts suivantes du dossier : un Q est partagé par 2 à 6 parts.
    etendue = round(INCREMENT_MOYEN * max(0, nombre_parts - 1) / (4 if type_ == 'Q' else 1))
    vitesse = rythme(points, type_, jour.year)
    avant = [p for p in candidats if p['date'] <= jour]
    apres = [p for p in candidats if p['date'] > jour]
    precedent = max(avant, key=lambda p: (p['numero'], p['date'])) if avant else None
    suivant = min(apres, key=lambda p: (p['numero'], p['date'])) if apres else None
    if suivant and not precedent:
        # La numérotation repart de zéro au 1er janvier.
        precedent = dict(numero=0, date=date(jour.year, 1, 1), source='début d’année')
    marge = tirage.randint(1, 6)
    if precedent and suivant:
        jours = (suivant['date'] - precedent['date']).days or 1
        valeur = precedent['numero'] + (suivant['numero'] - precedent['numero']) * (jour - precedent['date']).days / jours
        bas, haut = precedent['numero'] + marge, suivant['numero'] - etendue - 1
        valeur = min(max(round(valeur), bas), haut) if bas <= haut else precedent['numero'] + 1
        debut = (f"0 au 1er janvier" if precedent['numero'] == 0
                 else f"{precedent['numero']} ({precedent['date']:%d/%m/%Y}, {precedent['source']})")
        explication = (f"{libelle} : entre {debut} et {suivant['numero']} ({suivant['date']:%d/%m/%Y}, "
                       f"{suivant['source']})")
    elif precedent:
        valeur = precedent['numero'] + max(marge, round(vitesse * (jour - precedent['date']).days) + marge)
        explication = (f"{libelle} : après {precedent['numero']} ({precedent['date']:%d/%m/%Y}, {precedent['source']}), "
                       f"environ {vitesse:.0f} par jour")
    else:
        valeur = max(1, round(vitesse * _jour_annee(jour)) + marge)
        explication = (f"{libelle} : aucun numéro connu en {jour.year}, estimé à environ {vitesse:.0f} par jour "
                       f"depuis le 1er janvier")
    return int(valeur), explication


def proposer(points, dates, nombre_parts=1, bureau='', tirage=None):
    """{clé du champ: (numéro texte, explication)} pour E, L, Q et manifeste.

    dates : {'date_enregistrement', 'date_liquidation', 'date_quittance'} au format JJ/MM/AAAA."""
    tirage = tirage or random.SystemRandom()
    resultat = {}
    for type_, (cle, cle_date, _, _) in TYPES.items():
        proposition = proposer_numero(points, type_, lire_date(dates.get(cle_date)), nombre_parts, bureau, tirage)
        if proposition:
            resultat[cle] = (str(proposition[0]), proposition[1])
    if 'numero_e' in resultat:
        e = int(resultat['numero_e'][0])
        for type_ in SOUS_E:
            cle = TYPES[type_][0]
            if cle in resultat and int(resultat[cle][0]) >= e:
                valeur = sous_e(points, type_, e, tirage)
                resultat[cle] = (str(valeur), resultat[cle][1] + f' · ramené sous le E {e} (règle : '
                                 f'{TYPES[type_][2].lower()} toujours inférieur au E)')
    return resultat


# Liquidation, Q et manifeste sont toujours inférieurs au numéro E (même part).
SOUS_E = ('L', 'Q', 'M')


def rapport_au_e(points, type_):
    """Rapport habituel numéro / E (médiane des dossiers qui ont les deux la même année), ou None."""
    maxima = {}
    for p in points:
        if p['type'] in ('E', type_):
            cle = (p['source'], p['date'].year, p['type'])
            maxima[cle] = max(maxima.get(cle, 0), p['numero'])
    rapports = [maxima[(s, a, type_)] / n for (s, a, t), n in maxima.items()
                if t == 'E' and n > 0 and (s, a, type_) in maxima and maxima[(s, a, type_)] < n]
    return median(rapports) if rapports else None


def sous_e(points, type_, e, tirage=None):
    """Numéro inférieur au E : au rapport habituel avec le E, sinon juste en dessous."""
    tirage = tirage or random.SystemRandom()
    rapport = rapport_au_e(points, type_)
    valeur = round(e * rapport) if rapport else e - tirage.randint(5, 40)
    return max(1, min(valeur, e - tirage.randint(1, 6)))


def depuis_base(conn, exclure=None):
    """[(nom, contenu)] des dossiers ouverts et supprimés, sauf le dossier « exclure »."""
    licences = []
    for table in ('licences', 'licences_supprimees'):
        for ligne in conn.execute(f'SELECT numero, contenu FROM {table}').fetchall():
            if ligne['numero'] != exclure:
                try:
                    licences.append((ligne['numero'], json.loads(ligne['contenu'])))
                except ValueError:
                    continue
    return licences


# ---------------------------------------------------------------- listes de numéros connus (collées)
_DATE = re.compile(r'\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b')
_NUMERO_E = re.compile(r'^\s*[Ee]\s?(\d{2,7})\s*$')


def _date_liste(texte):
    trouve = _DATE.search(str(texte or ''))
    if not trouve:
        return None
    try:
        return date(int(trouve.group(3)), int(trouve.group(2)), int(trouve.group(1)))
    except ValueError:
        return None


def lire_liste(texte, type_='E'):
    """Numéros connus dans un tableau collé (Excel, Word…) : (points, ignorées).

    En-tête attendu : colonnes « E », « PAIEMENT ORANGE » et « DECLARATION » (séparées par tabulations).
    La date retenue est celle de la DÉCLARATION (les E croissent avec elle, pas avec le paiement).
    Une ligne sans E ou sans date de déclaration est ignorée ; une date de déclaration d'une autre année
    que le paiement est prise pour une faute de frappe et ignorée."""
    colonnes, points, ignorees = None, [], 0
    for ligne in str(texte or '').splitlines():
        cellules = [c.strip() for c in ligne.split('\t')]
        entetes = [c.upper().replace('É', 'E') for c in cellules]
        if 'E' in entetes and any(c.startswith('DECLAR') for c in entetes):
            colonnes = dict(e=entetes.index('E'),
                            declaration=next(i for i, c in enumerate(entetes) if c.startswith('DECLAR')),
                            paiement=next((i for i, c in enumerate(entetes) if 'ORANGE' in c or c.startswith('DATE')), None))
            continue
        if not any(cellules):
            continue
        if colonnes:
            valeur = cellules[colonnes['e']] if len(cellules) > colonnes['e'] else ''
            jour = _date_liste(cellules[colonnes['declaration']]) if len(cellules) > colonnes['declaration'] else None
            paiement = (_date_liste(cellules[colonnes['paiement']])
                        if colonnes['paiement'] is not None and len(cellules) > colonnes['paiement'] else None)
        else:  # sans en-tête : « E1234 » et la dernière date de la ligne
            valeur = next((c for c in cellules if _NUMERO_E.match(c)), '')
            dates = [d for d in (_date_liste(m.group()) for m in _DATE.finditer(ligne)) if d]
            jour, paiement = (dates[-1] if dates else None), (dates[0] if len(dates) > 1 else None)
        trouve = _NUMERO_E.match(valeur)
        if not trouve or jour is None or (paiement and paiement.year != jour.year):
            if trouve or jour:
                ignorees += 1
            continue
        plaque = next((c for c in cellules if '/' in c and re.search(r'[A-Za-z]', c) and not _DATE.search(c)), '')
        points.append(dict(type=type_, numero=int(trouve.group(1)), date=jour, bureau='',
                           source='liste ' + (plaque.upper().replace(' ', '') or 'collée')))
    return points, ignorees


# ---------------------------------------------------------------- contrôle d'une saisie et tendance
def attendu(points, type_, jour):
    """(bas, haut) : numéros des dossiers connus juste avant et juste après la date (cohérents), ou None."""
    candidats = coherents([p for p in points if p['type'] == type_ and p['date'].year == jour.year])
    avant = [p for p in candidats if p['date'] < jour]
    apres = [p for p in candidats if p['date'] > jour]
    return (max(avant, key=lambda p: p['numero']) if avant else None,
            min(apres, key=lambda p: p['numero']) if apres else None)


def controler_sous_e(e, valeurs):
    """Messages pour une liquidation, un Q ou un manifeste saisi supérieur ou égal au E."""
    n_e = numero(e)
    if n_e is None:
        return []
    return [f"{TYPES[t][2]} {numero(valeurs.get(TYPES[t][0]))} ≥ E {n_e} : il doit toujours être inférieur au E."
            for t in SOUS_E if numero(valeurs.get(TYPES[t][0])) is not None and numero(valeurs.get(TYPES[t][0])) >= n_e]


def controler(points, type_, valeur, jour):
    """Message si un numéro saisi contredit la progression connue (sinon None)."""
    n = numero(valeur)
    if n is None or jour is None:
        return None
    libelle = TYPES[type_][2]
    avant, apres = attendu(points, type_, jour)
    if avant and n < avant['numero']:
        return (f"{libelle} {n} au {jour:%d/%m/%Y} : plus petit que {avant['numero']} déjà connu au "
                f"{avant['date']:%d/%m/%Y} ({avant['source']}).")
    if apres and n > apres['numero']:
        return (f"{libelle} {n} au {jour:%d/%m/%Y} : plus grand que {apres['numero']} déjà connu au "
                f"{apres['date']:%d/%m/%Y} ({apres['source']}).")
    estime = proposer_numero(points, type_, jour, 1, tirage=random.Random(0)) if type_ == 'E' else None
    if estime:
        vitesse = rythme(points, type_, jour.year)
        tolerance = max(60, round(vitesse * 4))
        if abs(n - estime[0]) > tolerance:
            return (f"{libelle} {n} au {jour:%d/%m/%Y} : loin de la progression attendue (vers {estime[0]}, "
                    f"± {tolerance}). Vérifiez le numéro ou la date.")
    return None


def tendance(points, type_, annee):
    """Points cohérents et écartés de l'année, rythme et projection : pour le graphique de suivi."""
    annee_ = [p for p in points if p['type'] == type_ and p['date'].year == annee]
    retenus = coherents(annee_)
    ids = {id(p) for p in retenus}
    return dict(retenus=retenus, ecartes=[p for p in annee_ if id(p) not in ids],
                rythme=rythme(points, type_, annee))


def parts_hors_regle(licence):
    """[(n° de part, [messages])] des parts dont la liquidation, le Q ou le manifeste n'est pas inférieur au E."""
    resultat = []
    for part in (licence.get('repartition') or {}).get('parts') or []:
        infos = part.get('informations_declaration') or {}
        messages = controler_sous_e(infos.get('numero_e'), infos)
        if messages:
            resultat.append((part.get('numero'), messages))
    return resultat


def resume_hors_regle(licence):
    """Texte court pour la liste des licences, ou ''."""
    parts = parts_hors_regle(licence)
    if not parts:
        return ''
    types = sorted({m.split(' ')[0] for _, messages in parts for m in messages})
    numeros = [str(n) for n, _ in parts]
    return (f"{' / '.join(types)} ≥ E sur {len(parts)} part(s) "
            f"({', '.join(numeros[:6])}{'…' if len(numeros) > 6 else ''}) : corrigez l’étape 3")
