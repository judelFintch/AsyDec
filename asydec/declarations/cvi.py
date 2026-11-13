"""Remplissage du CVI et du BL de la première répartition, sans reconstruire le modèle Word.

Les balises {{CHAMP}} sont remplacées dans les textes du modèle, y compris
les zones de texte et en-têtes. Les styles, dessins et positions sont conservés.
Les numéros E/L/Q/manifeste sont ceux des parts validées, jamais retirés au hasard.
"""
from io import BytesIO
from pathlib import Path
import re
from xml.dom import minidom
from zipfile import ZipFile, BadZipFile

from asydec.declarations import facture_licence, mise_a_jour_repartitions
from asydec.declarations.preparer_facture import texte, remplacer

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
BALISE = re.compile(r'\{\{([A-Z_0-9]+)\}\}')
CHAMPS = ('NUMERO_E', 'NUMERO_LIQUIDATION', 'NUMERO_QUITTANCE', 'MANIFESTE',
          'DATE_CVI', 'PLAQUE', 'CONTENEUR', 'SCELLE', 'NUMERO_DEC', 'NUMERO_LICENCE',
          'NUMERO_FACTURE', 'DATE_FACTURE', 'FOB', 'POIDS_KG', 'ARTICLES',
          'IMPORTATEUR', 'FOURNISSEUR', 'BUREAU', 'REFERENCE', 'NUMERO_BL', 'PART',
          'NUMERO_CVI', 'DOSSIER_OCC', 'RAPPORT_INSPECTION', 'BORDEREAU',
          'ADRESSE_IMPORTATEUR', 'CONSTAT', 'ORIGINE', 'PROVENANCE', 'MODE_TRANSPORT',
          'REGIME', 'POSTE_ENTREE', 'ENTITE', 'FRET', 'ASSURANCE', 'DEVISE', 'CIF',
          'QUANTITE', 'QUANTITE_ARTICLE', 'DESIGNATION', 'DESTINATION', 'POIDS_GLOBAL_CVI')


# Seuls les champs absents des étapes précédentes peuvent être complétés ici.
# E/L/Q, plaque, FOB, poids et facture ne peuvent pas être écrasés.
CHAMPS_COMPLEMENTAIRES = {
    'NUMERO_CVI': 'N° CVI', 'DOSSIER_OCC': 'N° dossier OCC',
    'RAPPORT_INSPECTION': 'N° rapport d’inspection', 'BORDEREAU': 'N° bordereau',
    'ORIGINE': 'Pays d’origine', 'PROVENANCE': 'Pays de provenance',
    'MODE_TRANSPORT': 'Mode de transport', 'REGIME': 'Régime',
    'ENTITE': 'Entité OCC', 'DESTINATION': 'Destination finale',
    'CONSTAT': 'Constat sous palan', 'FRET': 'Fret total du dossier (USD)',
    'ASSURANCE': 'Assurance totale du dossier (USD)',
    'NUMERO_BL': 'N° BL (repris du dossier ou réservé automatiquement)',
    'DESIGNATION': 'Une seule désignation sur le CVI (ajustée à la case)',
}


CHAMPS_BL = {
    'NAVIRE_BL': 'Navire', 'VOYAGE_BL': 'N° voyage',
    'PORT_CHARGEMENT_BL': 'Port de chargement', 'PORT_DECHARGEMENT_BL': 'Port de déchargement',
    'FRET_PAYABLE_BL': 'Lieu de paiement du fret', 'LIEU_EMISSION_BL': 'Lieu d’émission du BL',
    'TYPE_CONTENEUR_BL': 'Type du conteneur (ex. 40HC)',
    'TARE_BL': 'Tare du conteneur (kg)', 'EMBALLAGE_BL': 'Conditionnement / emballage',
    'CONDITIONS_FOB_BL': 'Conditions FOB',
    'AGENT_BL': 'Notify party : nom et adresse (séparer les lignes par |)',
}
# Valeurs présentes sur la page CVI fournie, utilisées uniquement en l'absence
# de données du dossier ou d'une saisie dans le formulaire.
DEFAUTS_CVI = {
    'ORIGINE': 'CHINE', 'PROVENANCE': 'INDIA', 'MODE_TRANSPORT': 'Mer',
    'REGIME': 'IM4', 'ENTITE': 'LUBUMBASHI', 'DESTINATION': 'LUBUMBASHI',
    'POSTE_ENTREE': 'KASUMBALESA FRONTIERE', 'CONSTAT': 'TVS',
    'FRET': '0,00', 'ASSURANCE': '0,00', 'DEVISE': 'USD',
    'DESIGNATION': 'MOTOCYCLES A MOTEUR A PISTON',
    'IMPORTATEUR': 'KATANGA TVS SARL',
    'ADRESSE_IMPORTATEUR': 'AVENUE INDUSTRIELLE 2580, LUBUMBASHI, KATANGA RDC',
    'FOURNISSEUR': 'KINSHOP GENERAL TRADING', 'DATE_CVI': '07/11/2025',
    'FOB': '1263600,00', 'POIDS_KG': '240000,00',
    'QUANTITE': '1800,00', 'QUANTITE_ARTICLE': '1 800,000',
}
REFERENCES_CVI = dict(NUMERO_CVI='2025-725B-CAE-1230', DOSSIER_OCC='LSHI 2025 587821 CAE',
                      RAPPORT_INSPECTION='09899670', BORDEREAU='20',
                      # Le n° de voyage du modèle sert de base : chaque dossier reçoit le suivant.
                      VOYAGE_BL='994334')

# Valeurs de la deuxième page du modèle fourni, modifiables dans Infos BL.
DEFAUTS_BL = {
    'NAVIRE_BL': 'OEL SHRAVAN', 'VOYAGE_BL': '994334',
    'PORT_CHARGEMENT_BL': 'JEBEL ALI', 'PORT_DECHARGEMENT_BL': 'DAR ES SALAAM',
    'FRET_PAYABLE_BL': 'JEBEL ALI', 'LIEU_EMISSION_BL': 'JEBEL ALI',
    'TYPE_CONTENEUR_BL': '40HC', 'TARE_BL': '3900',
    'EMBALLAGE_BL': 'NOS SEAWORTHY CARTON BOXES',
    'CONDITIONS_FOB_BL': 'FOB CHENNAI PORT, CHINA',
    'AGENT_BL': 'FREIGHT AFRICA NV | 1ST FLOOR PEGASUS BUILDING | NYERERE ROAD PO BOX 63217 | '
                'DAR ES SALAAM / TANZANIA | PH +255 22 2181420 | PH +255 784 278652',
}
CHAMPS_COMPLEMENTAIRES.update(CHAMPS_BL)
# Calculés, jamais saisis : l'origine vient de la licence, les conditions FOB du port de chargement.
CHAMPS_DERIVES = ('ORIGINE', 'CONDITIONS_FOB_BL')
NUMEROS_BL_SUIVANTS = ('NUMERO_BL_2', 'NUMERO_BL_3')


def port_chargement(licence, complements=None):
    """Port de chargement du dossier : saisi dans Infos BL, sinon port habituel du pays d'origine."""
    from asydec.declarations import coherence_transport
    if complements is None:
        complements = (licence.get('cvi_parts') or {}).get('complements') or {}
    return (str(complements.get('PORT_CHARGEMENT_BL') or '').strip()
            or coherence_transport.port_par_defaut(licence) or DEFAUTS_BL['PORT_CHARGEMENT_BL'])


def appliquer_derives(licence, valeurs):
    """Origine (licence) et conditions FOB (port) imposées, pour que CVI, BL et facture concordent."""
    from asydec.declarations import coherence_transport
    origine = coherence_transport.origine_cvi(licence)
    if origine:
        valeurs['ORIGINE'] = origine
    port = valeurs.get('PORT_CHARGEMENT_BL') or port_chargement(licence)
    valeurs['PORT_CHARGEMENT_BL'] = coherence_transport.normaliser_port(port)
    valeurs['CONDITIONS_FOB_BL'] = coherence_transport.conditions_fob(port)
    return valeurs
CHAMPS += tuple(CHAMPS_BL) + ('DATE_BL', 'DATE_FACTURE_BL', 'POIDS_BL', 'QUANTITE_BL')
CHAMPS_LIGNES = tuple(f'{prefixe}_LIGNE_{i}' for prefixe, maximum in
                     (('IMPORTATEUR', 5), ('FOURNISSEUR', 8), ('AGENT_BL', 7))
                     for i in range(1, maximum+1))
CHAMPS_LISTE_BL = tuple(f'CONTENEUR_SCELLE_BL_{i}' for i in range(1, 20))
CHAMPS += CHAMPS_LIGNES + CHAMPS_LISTE_BL + ('NOMBRE_CONTENEURS_BL', 'QUANTITE_BL_LETTRES', 'NUMERO_FACTURE_BL')


def modele_defaut():
    from asydec.systeme import modeles_documents
    return modeles_documents.chemin('cvi_bl')


def incrementer_reference(reference):
    correspondance = re.fullmatch(r'(.*?)([0-9]+)([^0-9]*)', reference)
    if not correspondance:
        raise ValueError('Référence CVI sans partie numérique : ' + reference)
    prefixe, chiffres, suffixe = correspondance.groups()
    return prefixe + str(int(chiffres) + 1).zfill(len(chiffres)) + suffixe


REFERENCE_BL_MODELE = 'E 008948899'
# Une page BL du modèle affiche 10 conteneurs ; au-delà, un BL de plus par tranche de 10 (3 au plus).
CONTENEURS_PAR_BL = 10
BL_MAXIMUM = 3
# Champs propres à chaque page BL ; le reste (navire, ports, notify…) est commun.
CHAMPS_PAGE_BL = ('NUMERO_BL', 'CONTENEUR', 'NOMBRE_CONTENEURS_BL', 'QUANTITE_BL', 'QUANTITE_BL_LETTRES',
                  'POIDS_BL') + tuple(f'CONTENEUR_SCELLE_BL_{i}' for i in range(1, 20))


def parts_triees(licence, part=None):
    parts = (licence.get('repartition') or {}).get('parts') or ([part] if part else [])
    return sorted(parts, key=lambda p: int(p['numero']))


def nombre_bl(licence):
    """1 BL jusqu'à 10 répartitions, 2 jusqu'à 20, 3 jusqu'à 30."""
    n = max(1, -(-len(parts_triees(licence)) // CONTENEURS_PAR_BL))
    if n > BL_MAXIMUM:
        raise ValueError(f'{len(parts_triees(licence))} répartitions : {BL_MAXIMUM} BL de {CONTENEURS_PAR_BL} conteneurs '
                         f'au plus ({BL_MAXIMUM * CONTENEURS_PAR_BL} répartitions).')
    return n


def cles_numeros_bl(licence):
    """['NUMERO_BL', 'NUMERO_BL_2', …] selon le nombre de BL du dossier."""
    return ['NUMERO_BL'] + [f'NUMERO_BL_{k}' for k in range(2, nombre_bl(licence) + 1)]


def numero_bl_connu(licence, part=None):
    if part is None:
        part = premiere_part(licence)
    for valeur in ((part.get('informations_declaration') or {}).get('numero_bl'),
                   (licence.get('informations_declaration') or {}).get('numero_bl'),
                   licence.get('numero_bl')):
        if valeur is not None and str(valeur).strip():
            return str(valeur).strip()
    return ''


def reserver_references(licence, fichier=None):
    """Réserve les séquences sous verrou SQLite ; un dossier conserve ses références.

    Une réservation annulée laisse un trou, sans réutiliser son numéro.
    Les CVI déjà enregistrés servent également de base à la séquence.
    """
    from asydec.declarations import licences_ouvertes
    import json
    identifiant = str(licence.get('numero_validation') or licence.get('numero_dec') or '').strip()
    connu = numero_bl_connu(licence)
    references = dict(REFERENCES_CVI)
    if not connu:
        references['NUMERO_BL'] = REFERENCE_BL_MODELE
    try:
        for cle in cles_numeros_bl(licence)[1:]:
            references[cle] = REFERENCE_BL_MODELE
    except ValueError:
        pass
    # Les appels sans dossier identifié servent seulement aux aperçus / analyses.
    if not identifiant:
        return dict({cle: incrementer_reference(valeur) for cle, valeur in references.items()}, **({'NUMERO_BL':connu} if connu else {}))
    existants = (licence.get('cvi_parts') or {}).get('complements') or {}
    infos = premiere_part(licence).get('informations_declaration') or {}
    annee = str(infos.get('date_cvi') or DEFAUTS_CVI['DATE_CVI'])[-4:]
    extraire = lambda v: int(re.search(r'([0-9]+)[^0-9]*$', v).group(1))
    resultat = {'NUMERO_BL':connu} if connu else {}
    with licences_ouvertes.connexion(fichier) as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute("""CREATE TABLE IF NOT EXISTS cvi_references (
            licence TEXT NOT NULL, champ TEXT NOT NULL, reference TEXT NOT NULL, sequence INTEGER NOT NULL,
            PRIMARY KEY (licence, champ), UNIQUE (champ, reference), UNIQUE (champ, sequence))""")
        anciens = [json.loads(r['contenu']) for r in conn.execute('SELECT contenu FROM licences').fetchall()]
        for cle, base in references.items():
            reserve = conn.execute('SELECT reference FROM cvi_references WHERE licence=? AND champ=?', (identifiant,cle)).fetchone()
            if reserve:
                resultat[cle] = reserve['reference']
                continue
            maximum = extraire(base)
            # Tous les BL (1er, 2e, 3e d'un dossier) partagent une seule séquence.
            famille = ['NUMERO_BL'] + [f'NUMERO_BL_{k}' for k in range(2, BL_MAXIMUM + 1)] if cle.startswith('NUMERO_BL') else [cle]
            marques = ','.join('?' * len(famille))
            autre = conn.execute(f'SELECT MAX(sequence) FROM cvi_references WHERE champ IN ({marques})', famille).fetchone()[0]
            maximum = max(maximum, autre or 0)
            utilisees = set()
            for dossier in anciens:
                for membre in famille:
                    valeur = ((dossier.get('cvi_parts') or {}).get('complements') or {}).get(membre)
                    if membre == 'NUMERO_BL':
                        try:
                            valeur = numero_bl_connu(dossier) or valeur
                        except ValueError:
                            pass
                    if valeur and re.search(r'[0-9]+[^0-9]*$', valeur):
                        maximum = max(maximum, extraire(valeur))
                        if str(dossier.get('numero_validation') or dossier.get('numero_dec')) != identifiant or membre != cle:
                            utilisees.add(extraire(valeur))
            if cle != 'NUMERO_BL' and cle.startswith('NUMERO_BL') and connu and re.search(r'[0-9]+[^0-9]*$', connu):
                utilisees.add(extraire(connu))
            reference = str(existants.get(cle) or '')
            sequence = extraire(reference) if reference and re.search(r'[0-9]+[^0-9]*$', reference) else None
            # Le numéro du modèle lui-même n'est jamais attribué à un dossier (ex. ancien voyage 994334).
            collision = sequence is not None and (sequence == extraire(base) or sequence in utilisees or conn.execute(
                f'SELECT 1 FROM cvi_references WHERE champ IN ({marques}) AND sequence=? AND NOT (licence=? AND champ=?)',
                (*famille, sequence, identifiant, cle)).fetchone())
            if sequence is None or collision:
                reference = base
                if re.fullmatch(r'[0-9]{4}', annee):
                    if cle == 'NUMERO_CVI':
                        reference = re.sub(r'^[0-9]{4}', annee, reference)
                    elif cle == 'DOSSIER_OCC':
                        reference = re.sub(r'\b[0-9]{4}\b', annee, reference, count=1)
                m = re.fullmatch(r'(.*?)([0-9]+)([^0-9]*)', reference)
                sequence = maximum + 1
                reference = m[1] + str(sequence).zfill(len(m[2])) + m[3]
            conn.execute('INSERT INTO cvi_references VALUES (?, ?, ?, ?)', (identifiant,cle,reference,sequence))
            resultat[cle] = reference
    return resultat


def premiere_designation(part):
    for article in part.get('articles') or []:
        if str(article.get('designation') or '').strip():
            return str(article['designation'])
    return DEFAUTS_CVI['DESIGNATION']


def adapter_designation(designation):
    """Une désignation, sur une ligne en Arial 9, entre les deux tabulations.

    Les colonnes commencent à 36 et 216 pt ; garder 6 pt de marge avant la quantité.
    Les anciennes listes assemblées avec « ; » sont ramenées à leur premier article.
    """
    import pymupdf
    texte = ' '.join(str(designation or '').split(' ; ', 1)[0].split())
    largeur = lambda t: pymupdf.get_text_length(t, fontname='helv', fontsize=9)
    if largeur(texte) <= 174:
        return texte
    mots = texte.split()
    while len(mots) > 1:
        mots.pop()
        candidat = ' '.join(mots).rstrip(' ,;.-') + '…'
        if largeur(candidat) <= 174:
            return candidat
    mot = mots[0] if mots else ''
    while mot and largeur(mot + '…') > 174:
        mot = mot[:-1]
    return mot + '…'


def proposer_complements(licence, fichier=None):
    existants = (licence.get('cvi_parts') or {}).get('complements') or {}
    part = premiere_part(licence)
    infos = part.get('informations_declaration') or {}
    valeurs = dict(DEFAUTS_CVI, **DEFAUTS_BL)
    # Les informations connues et les choix enregistrés priment sur le modèle.
    for cle in CHAMPS_COMPLEMENTAIRES:
        connue = infos.get(cle.lower())
        if connue is not None and str(connue).strip():
            valeurs[cle] = str(connue)
    designation = premiere_designation(part)
    if designation:
        valeurs['DESIGNATION'] = designation
    for cle, valeur in existants.items():
        if valeur is not None and str(valeur).strip():
            valeurs[cle] = valeur
    # Sans choix enregistré : port habituel du pays d'origine, et les lieux et la provenance qui en découlent.
    from asydec.declarations import coherence_transport
    if not str(existants.get('PORT_CHARGEMENT_BL') or '').strip():
        port = port_chargement(licence, existants)
        valeurs['PORT_CHARGEMENT_BL'] = port
        for cle in ('FRET_PAYABLE_BL', 'LIEU_EMISSION_BL'):
            if not str(existants.get(cle) or '').strip():
                valeurs[cle] = port
        if not str(existants.get('PROVENANCE') or '').strip() and coherence_transport.port_par_defaut(licence):
            valeurs['PROVENANCE'] = coherence_transport.pays_du_port(port) or valeurs.get('PROVENANCE', '')
    appliquer_derives(licence, valeurs)
    valeurs['DESIGNATION'] = adapter_designation(valeurs['DESIGNATION'])
    valeurs.update(reserver_references(licence, fichier))
    return {cle: valeurs.get(cle, '') for cle in tuple(CHAMPS_COMPLEMENTAIRES) + tuple(cles_numeros_bl(licence)[1:])}


def colis_dossier(licence, parts):
    """Nombre total de colis du dossier (entier), selon la règle du XML appliquée à chaque article de chaque part."""
    from decimal import Decimal
    from asydec.declarations.xml_licence import colis
    total = 0
    for part in parts:
        articles = part.get('articles') or []
        if not articles:
            continue
        try:
            lignes = facture_licence.donnees_part(licence, part)['lignes']
        except (ValueError, KeyError, ArithmeticError):
            lignes = [dict(quantite=Decimal(str(a['quantite'])), unite=a.get('unite'),
                           poids=Decimal(str(part.get('poids_kg') or 0)) / len(articles)) for a in articles]
        total += sum(colis(l['quantite'], l.get('unite'), l['poids']) for l in lignes)
    return Decimal(total)


def poids_global_cvi(licence, part):
    """Somme des poids des parts ; ne pas utiliser le total éventuellement périmé."""
    from decimal import Decimal, InvalidOperation
    from asydec.formats import nombre
    parts = (licence.get('repartition') or {}).get('parts') or [part]
    if parts == [part] and not part.get('poids_kg') and not licence.get('repartition'):
        return nombre(Decimal(DEFAUTS_CVI['POIDS_KG'].replace(',', '.')), 2)
    try:
        poids = [Decimal(str(p['poids_kg']).replace(' ', '').replace('\u00a0', '').replace(',', '.')) for p in parts]
        if any(not p.is_finite() or p <= 0 for p in poids):
            raise ValueError()
    except (KeyError, InvalidOperation, ValueError):
        raise ValueError('Le poids de chaque répartition doit être renseigné et positif pour calculer le poids global CVI.') from None
    return nombre(sum(poids, Decimal(0)), 2)


def page_bl(licence, parts, numero_bl):
    """Champs propres à une page BL : ses conteneurs (10 au plus), scellés, poids et colis."""
    from decimal import Decimal, InvalidOperation
    from asydec.formats import nombre
    from asydec.declarations.nombres_lettres import nombre as en_lettres
    page = {'NUMERO_BL': str(numero_bl or ''), 'NOMBRE_CONTENEURS_BL': str(len(parts)), 'CONTENEUR': ''}
    lignes_bl = []
    if any(p.get('conteneur') or p.get('scelle') for p in parts):
        for i, p in enumerate(parts):
            conteneur = str(p.get('conteneur') or '').strip()
            scelle = str(p.get('scelle') or '').strip()
            if not conteneur or not scelle:
                raise ValueError(f"Conteneur ou scellé manquant sur la répartition {p.get('numero')}.")
            if i == 0:
                page['CONTENEUR'] = conteneur
            else:
                lignes_bl.append(conteneur)
            lignes_bl.append('SEAL ' + scelle)
    for i, cle in enumerate(CHAMPS_LISTE_BL):
        page[cle] = lignes_bl[i] if i < len(lignes_bl) else ''
    try:
        poids = sum((Decimal(str(p.get('poids_kg') or 0).replace(' ', '').replace(',', '.')) for p in parts), Decimal(0))
        # Packages : nombre entier de colis, calculé comme dans le XML (un colis par pièce,
        # sinon un colis par 50 kg) et additionné sur les répartitions du BL.
        colis = colis_dossier(licence, parts)
        if not colis:
            colis = Decimal(DEFAUTS_CVI['QUANTITE'].replace(',', '.'))
    except (InvalidOperation, ValueError):
        raise ValueError('Quantités ou poids BL invalides sur les répartitions.') from None
    if poids:
        page['POIDS_BL'] = nombre(poids, 2).replace(',', '.')
    page['QUANTITE_BL'] = nombre(colis, 0)
    page['QUANTITE_BL_LETTRES'] = en_lettres(colis)
    return page


def numeros_bl_cvi(numeros):
    """N° BL pour la case du CVI : tous les BL s'ils tiennent, sinon le premier suivi de la fin des autres."""
    import pymupdf
    numeros = [str(n) for n in numeros if str(n or '').strip()]
    if len(numeros) <= 1:
        return numeros[0] if numeros else ''
    largeur = lambda t: pymupdf.get_text_length(t, fontname='helv', fontsize=9)
    complet = ' / '.join(numeros)
    if largeur(complet) <= 128:
        return complet
    courts = [numeros[0]]
    for n in numeros[1:]:
        commun = 0
        while commun < min(len(n), len(numeros[0])) and n[commun] == numeros[0][commun]:
            commun += 1
        courts.append(n[min(commun, len(n) - 3):] if n[:commun].strip() else n)
    return ' / '.join(courts)


def donnees(licence, part, complements=None):
    infos = part.get('informations_declaration') or {}
    numero, date = facture_licence.references_facture(licence)
    valeurs = {c: str(infos.get(c.lower()) or '') for c in CHAMPS}
    valeurs.update(PART=str(part['numero']), NUMERO_DEC=str(licence.get('numero_dec') or ''),
                   NUMERO_LICENCE=str(licence.get('numero_validation') or ''),
                   NUMERO_FACTURE=facture_licence.numero_part(numero, part), DATE_FACTURE=date,
                   FOB=str(part.get('fob') or ''), POIDS_KG=str(part.get('poids_kg') or ''),
                   PLAQUE=str(part.get('plaque') or infos.get('plaque') or ''),
                   CONTENEUR=str(part.get('conteneur') or ''), SCELLE=str(part.get('scelle') or ''),
                   IMPORTATEUR=str((licence.get('soussigne') or {}).get('nom') or ''),
                   FOURNISSEUR=str((licence.get('fournisseur') or {}).get('nom') or ''),
                   NUMERO_BL=numero_bl_connu(licence, part),
                   BUREAU=str(infos.get('bureau_nom') or ''),
                   ARTICLES=' ; '.join(f"{a['designation']} : {a['quantite']}" for a in part.get('articles') or []))
    from decimal import Decimal, InvalidOperation
    from asydec.formats import nombre
    valeurs['ADRESSE_IMPORTATEUR'] = str((licence.get('soussigne') or {}).get('adresse') or '')
    valeurs['POSTE_ENTREE'] = str(infos.get('bureau_nom') or '')
    valeurs['POIDS_GLOBAL_CVI'] = poids_global_cvi(licence, part)
    valeurs['DEVISE'] = 'USD'
    valeurs['DESIGNATION'] = premiere_designation(part)
    if complements is None:
        complements = (licence.get('cvi_parts') or {}).get('complements') or {}
    valeurs.update({k: str(v).strip() for k, v in complements.items()
                    if (k in CHAMPS_COMPLEMENTAIRES or k in NUMEROS_BL_SUIVANTS)
                    and (k != 'NUMERO_BL' or not numero_bl_connu(licence, part))})
    if not str(valeurs.get('PORT_CHARGEMENT_BL') or '').strip():
        valeurs['PORT_CHARGEMENT_BL'] = port_chargement(licence, complements)
    for cle in ('FRET_PAYABLE_BL', 'LIEU_EMISSION_BL'):
        if not str(valeurs.get(cle) or '').strip():
            valeurs[cle] = valeurs['PORT_CHARGEMENT_BL']
    for cle, valeur in {**DEFAUTS_CVI, **DEFAUTS_BL}.items():
        if not str(valeurs.get(cle) or '').strip():
            valeurs[cle] = valeur
    appliquer_derives(licence, valeurs)
    valeurs['DESIGNATION'] = adapter_designation(valeurs['DESIGNATION'])
    for cle, prefixe in (('NUMERO_E', 'E'), ('NUMERO_LIQUIDATION', 'L'), ('NUMERO_QUITTANCE', 'Q')):
        if valeurs[cle] and not re.match(r'^'+prefixe+r'\b', valeurs[cle], re.I):
            valeurs[cle] = prefixe + ' ' + valeurs[cle]
    # Le CVI couvre toute la licence (comme le BL) : FOB, CIF, quantité, poids et facture globaux,
    # jamais ceux de la seule première part.
    toutes = (licence.get('repartition') or {}).get('parts') or [part]
    valeurs['NUMERO_FACTURE'] = numero
    try:
        fob_global = sum((Decimal(str(p.get('fob') or 0)) for p in toutes), Decimal(0))
        if not fob_global and licence.get('montant_fob'):
            fob_global = Decimal(str(licence['montant_fob']))
        if fob_global:
            valeurs['FOB'] = str(fob_global)
        valeurs['POIDS_KG'] = valeurs['POIDS_GLOBAL_CVI']
    except (InvalidOperation, ValueError):
        raise ValueError('FOB des répartitions invalide.') from None
    try:
        quantite = sum((Decimal(str(a['quantite'])) for p in toutes for a in p.get('articles') or []), Decimal(0))
        if not quantite:
            quantite = sum((Decimal(str(a.get('quantite')).replace(',', '.')) for a in licence.get('produits') or []
                            if str(a.get('quantite') or '').strip()), Decimal(0))
        valeurs['QUANTITE'] = nombre(quantite, 2) if quantite else DEFAUTS_CVI['QUANTITE']
        valeurs['QUANTITE_ARTICLE'] = nombre(quantite, 3) if quantite else DEFAUTS_CVI['QUANTITE_ARTICLE']
        for cle in ('FOB', 'POIDS_KG', 'FRET', 'ASSURANCE'):
            if valeurs.get(cle):
                montant = Decimal(valeurs[cle].replace(' ', '').replace('\u00a0', '').replace(',', '.'))
                if not montant.is_finite() or montant < 0:
                    raise ValueError('Montant négatif ou non fini.')
                valeurs[cle] = nombre(montant, 2)
        if all(valeurs.get(c) for c in ('FOB', 'FRET', 'ASSURANCE')):
            valeurs['CIF'] = nombre(sum((Decimal(valeurs[c].replace(' ', '').replace('\u00a0', '').replace(',', '.'))
                                         for c in ('FOB', 'FRET', 'ASSURANCE')), Decimal(0)), 2)
    except (InvalidOperation, ValueError):
        raise ValueError('Les montants CVI doivent être numériques.') from None
    from asydec.declarations.informations_declaration import lire_date
    mois = ('JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC')
    if licence.get('date_bl'):
        jour = lire_date(licence['date_bl'])
        valeurs['DATE_BL'] = f'{jour.day:02d} {mois[jour.month-1]} {jour.year}'
    valeurs['DATE_FACTURE_BL'] = date.replace('/', '.')
    valeurs['POIDS_BL'] = valeurs['POIDS_GLOBAL_CVI'].replace(',', '.')
    valeurs['QUANTITE_BL'] = valeurs.get('QUANTITE', '').replace(',', '.')
    # Un BL par tranche de 10 répartitions (conteneurs) : chacun a son numéro, ses conteneurs et scellés,
    # son poids et ses colis. Le CVI garde les totaux de tout le dossier.
    parts_bl = parts_triees(licence, part)
    tranches = [parts_bl[k:k + CONTENEURS_PAR_BL] for k in range(0, len(parts_bl), CONTENEURS_PAR_BL)]
    if len(tranches) > BL_MAXIMUM:
        nombre_bl(licence)
    vus = set()
    for p in parts_bl:
        conteneur = str(p.get('conteneur') or '').strip()
        if conteneur and conteneur in vus:
            raise ValueError('Un conteneur apparaît sur plusieurs répartitions : ' + conteneur)
        vus.add(conteneur)
    numeros_bl = [valeurs.get('NUMERO_BL', '')] + [valeurs.get(f'NUMERO_BL_{k}', '') for k in range(2, len(tranches) + 1)]
    if len(tranches) > 1:
        manquants = [str(k + 1) for k, n in enumerate(numeros_bl) if not str(n).strip()]
        if manquants:
            raise ValueError('Numéro manquant pour le BL ' + ', '.join(manquants) + ' : rouvrez le formulaire CVI et BL.')
        if len(set(numeros_bl)) != len(numeros_bl):
            raise ValueError('Chaque BL doit avoir un numéro différent.')
    valeurs['_PAGES_BL'] = [page_bl(licence, tranche, numero_bl) for tranche, numero_bl in zip(tranches, numeros_bl)]
    valeurs.update(valeurs['_PAGES_BL'][0])
    valeurs['NUMERO_BL'] = numeros_bl_cvi(numeros_bl)
    valeurs['NUMERO_FACTURE_BL'] = numero
    if valeurs.get('TARE_BL'):
        try:
            tare = Decimal(valeurs['TARE_BL'].replace(' ', '').replace(',', '.'))
            if not tare.is_finite() or tare < 0:
                raise ValueError()
            valeurs['TARE_BL'] = nombre(tare, 0)
        except (InvalidOperation, ValueError):
            raise ValueError('La tare du BL doit être un nombre positif ou nul.') from None
    # Éviter le texte coupé dans les deux cases étroites du BL, sans réduire la police.
    import pymupdf
    for cle, largeur, sources in (('VOYAGE_BL', 45.6, [valeurs]), ('NUMERO_BL', 75.6, valeurs['_PAGES_BL'])):
        for source in sources:
            if source.get(cle) and pymupdf.get_text_length(source[cle], fontname='helv', fontsize=7.5) > largeur:
                raise ValueError(f'{cle} : référence trop longue pour la case du modèle BL à police constante.')
    for prefixe, coordonnees, maximum in (
            ('IMPORTATEUR', licence.get('soussigne') or {}, 5),
            ('FOURNISSEUR', licence.get('fournisseur') or {}, 8),
            ('AGENT_BL', None, 7)):
        if coordonnees is None:
            contenu = valeurs.get('AGENT_BL', '').replace('|', '\n')
        else:
            contenu = '\n'.join(str(coordonnees.get(c) or '') for c in ('nom','adresse','telephone','email'))
        lignes = [l.strip() for l in contenu.splitlines() if l.strip()]
        if len(lignes) > maximum:
            raise ValueError(f'{prefixe} : le modèle BL accepte {maximum} lignes au maximum.')
        for i in range(maximum):
            valeurs[f'{prefixe}_LIGNE_{i+1}'] = lignes[i] if i < len(lignes) else ''
    return valeurs


_VML = 'urn:schemas-microsoft-com:vml'
_W14 = 'http://schemas.microsoft.com/office/word/2010/wordml'


def _saut_de_page(element):
    return any(b.getAttributeNS(W, 'type') == 'page' and b.parentNode is element
               for b in element.getElementsByTagNameNS(W, 'br'))


def _pages_bl(doc, nombre):
    """Duplique la page BL du modèle (zones de texte après le saut de page) pour avoir `nombre` pages BL.

    Renvoie {élément de premier niveau: indice de page BL} pour savoir quelle page remplit chaque zone."""
    corps = doc.getElementsByTagNameNS(W, 'body')[0]
    for paragraphe in [c for c in corps.childNodes if c.nodeType == 1 and c.localName == 'p']:
        runs = [c for c in paragraphe.childNodes if c.nodeType == 1]
        saut = next((i for i, r in enumerate(runs) if r.localName == 'r' and _saut_de_page(r)), None)
        if saut is not None:
            break
    else:
        return {}
    page_bl = [r for r in runs[saut + 1:] if r.localName == 'r']
    appartenance = {id(r): 0 for r in page_bl}
    precedent = paragraphe
    for k in range(1, nombre):
        nouveau = doc.createElementNS(W, 'w:p')
        for proprietes in [c for c in paragraphe.childNodes if c.nodeType == 1 and c.localName == 'pPr']:
            nouveau.appendChild(proprietes.cloneNode(True))
        nouveau.appendChild(runs[saut].cloneNode(True))
        for run in page_bl:
            copie = run.cloneNode(True)
            for forme in copie.getElementsByTagNameNS(_VML, 'shape'):
                if forme.getAttribute('id'):
                    forme.setAttribute('id', f"{forme.getAttribute('id')} BL{k + 1}")
                if forme.getAttribute('o:spid'):
                    forme.setAttribute('o:spid', f"{forme.getAttribute('o:spid')}_{k + 1}")
            for element in [copie] + list(copie.getElementsByTagName('*')):
                for attribut in ('w14:paraId', 'w14:textId'):
                    if element.hasAttribute(attribut):
                        element.removeAttribute(attribut)
            nouveau.appendChild(copie)
            appartenance[id(copie)] = k
        corps.insertBefore(nouveau, precedent.nextSibling)
        precedent = nouveau
    return appartenance


def _page_de(p, appartenance):
    noeud = p
    while noeud is not None:
        if id(noeud) in appartenance:
            return appartenance[id(noeud)]
        noeud = noeud.parentNode
    return None


def remplir(modele, valeurs, avec_bl=False):
    pages = valeurs.get('_PAGES_BL') or []
    try:
        archive = ZipFile(BytesIO(modele))
    except BadZipFile:
        raise ValueError('Le CVI doit être un .docx enregistré par Word, avec les balises de remplissage. Le .doc original reste intact.') from None
    with archive:
        modifications, trouvees = {}, set()
        for nom in archive.namelist():
            if not re.fullmatch(r'word/(document|header[0-9]*|footer[0-9]*|footnotes|endnotes)\.xml', nom):
                continue
            try:
                doc = minidom.parseString(archive.read(nom))
            except Exception as exc:
                raise ValueError('Le modèle CVI contient un XML illisible : ' + nom) from exc
            change = False
            appartenance = _pages_bl(doc, len(pages)) if nom == 'word/document.xml' and pages else {}
            change = len(pages) > 1 and bool(appartenance)
            for p in doc.getElementsByTagNameNS(W, 'p'):
                # Un paragraphe de zone de texte peut être inclus dans un autre :
                # ne traiter que les paragraphes contenant directement leurs textes.
                if p.getElementsByTagNameNS(W, 'p'):
                    continue
                contenu = texte(p)
                indice = _page_de(p, appartenance) if appartenance else None
                source = dict(valeurs, **pages[indice]) if indice is not None else valeurs
                for m in reversed(list(BALISE.finditer(contenu))):
                    cle = m.group(1)
                    if cle not in CHAMPS:
                        raise ValueError(f'Champ CVI inconnu : {cle}.')
                    if cle not in CHAMPS_LIGNES + CHAMPS_LISTE_BL and not str(source.get(cle) or '').strip():
                        raise ValueError(f'Donnée CVI manquante : {cle}. Complétez la licence ou la déclaration.')
                    trouvees.add(cle)
                    valeur = str(source.get(cle, ''))
                    if cle == 'DESIGNATION':
                        valeur = adapter_designation(valeur)
                    remplacer(p, m.start(), m.end(), valeur)
                    change = True
            if change:
                modifications[nom] = doc.toxml(encoding='UTF-8')
        requis = {'NUMERO_E', 'NUMERO_LIQUIDATION', 'NUMERO_QUITTANCE', 'DATE_CVI'}
        if avec_bl:
            requis |= {'NUMERO_BL', 'DATE_BL', 'CONTENEUR', 'CONTENEUR_SCELLE_BL_1', 'NAVIRE_BL', 'POIDS_BL'}
        if not requis <= trouvees:
            raise ValueError('Modèle CVI non préparé : balises obligatoires manquantes : ' + ', '.join(sorted(requis - trouvees)))
        sortie = BytesIO()
        with ZipFile(sortie, 'w') as cible:
            for info in archive.infolist():
                cible.writestr(info, modifications.get(info.filename, archive.read(info.filename)))
        return sortie.getvalue()


def premiere_part(licence):
    for part in facture_licence.parts(licence):
        if str(part.get('numero')) == '1':
            return part
    raise ValueError('La première répartition (part 1) est absente.')


def generer(licence, modele, complements=None):
    if not mise_a_jour_repartitions.est_a_jour(licence) or not facture_licence.est_a_jour(licence):
        raise ValueError('Validez les répartitions et produisez les factures avant les CVI.')
    part = premiere_part(licence)
    return [(part['numero'], remplir(modele, donnees(licence, part, complements), avec_bl=True))]


def empreinte(licence, complements=None):
    import hashlib
    import json
    return hashlib.sha256(json.dumps({'version_modele': 9, 'donnees': donnees(licence, premiere_part(licence), complements)},
                                    sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def est_a_jour(licence):
    fiche = licence.get('cvi_parts') or {}
    try:
        return (len(fiche.get('fichiers') or []) == 1 and mise_a_jour_repartitions.est_a_jour(licence)
                and facture_licence.est_a_jour(licence) and fiche.get('empreinte') == empreinte(licence)
                and all(Path(p).is_file() for p in fiche['fichiers']))
    except ValueError:
        return False
