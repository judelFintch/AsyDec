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
    'CONSTAT': 'Constat sous palan', 'FRET': 'Fret de la première part (USD)',
    'ASSURANCE': 'Assurance de la première part (USD)',
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
                      RAPPORT_INSPECTION='09899670', BORDEREAU='20')

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
CHAMPS += tuple(CHAMPS_BL) + ('DATE_BL', 'DATE_FACTURE_BL', 'POIDS_BL', 'QUANTITE_BL')
CHAMPS_LIGNES = tuple(f'{prefixe}_LIGNE_{i}' for prefixe, maximum in
                     (('IMPORTATEUR', 5), ('FOURNISSEUR', 8), ('AGENT_BL', 7))
                     for i in range(1, maximum+1))
CHAMPS_LISTE_BL = tuple(f'CONTENEUR_SCELLE_BL_{i}' for i in range(1, 20))
CHAMPS += CHAMPS_LIGNES + CHAMPS_LISTE_BL + ('NOMBRE_CONTENEURS_BL', 'QUANTITE_BL_LETTRES', 'NUMERO_FACTURE_BL')


def modele_defaut():
    from asydec import chemins
    return chemins.CODE / 'ressources' / 'cvi' / 'CVI-modele.docx'


def incrementer_reference(reference):
    correspondance = re.fullmatch(r'(.*?)([0-9]+)([^0-9]*)', reference)
    if not correspondance:
        raise ValueError('Référence CVI sans partie numérique : ' + reference)
    prefixe, chiffres, suffixe = correspondance.groups()
    return prefixe + str(int(chiffres) + 1).zfill(len(chiffres)) + suffixe


REFERENCE_BL_MODELE = 'E 008948899'


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
            autre = conn.execute('SELECT MAX(sequence) FROM cvi_references WHERE champ=?', (cle,)).fetchone()[0]
            maximum = max(maximum, autre or 0)
            utilisees = set()
            for dossier in anciens:
                valeur = ((dossier.get('cvi_parts') or {}).get('complements') or {}).get(cle)
                if cle == 'NUMERO_BL':
                    try:
                        valeur = numero_bl_connu(dossier) or valeur
                    except ValueError:
                        pass
                if valeur and re.search(r'[0-9]+[^0-9]*$', valeur):
                    maximum = max(maximum, extraire(valeur))
                    if str(dossier.get('numero_validation') or dossier.get('numero_dec')) != identifiant:
                        utilisees.add(extraire(valeur))
            reference = str(existants.get(cle) or '')
            sequence = extraire(reference) if reference and re.search(r'[0-9]+[^0-9]*$', reference) else None
            collision = sequence is not None and (sequence in utilisees or conn.execute(
                'SELECT 1 FROM cvi_references WHERE champ=? AND sequence=?', (cle,sequence)).fetchone())
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
    valeurs['DESIGNATION'] = adapter_designation(valeurs['DESIGNATION'])
    valeurs.update(reserver_references(licence, fichier))
    return {cle: valeurs.get(cle, '') for cle in CHAMPS_COMPLEMENTAIRES}


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
    valeurs.update({k: str(v).strip() for k, v in complements.items() if k in CHAMPS_COMPLEMENTAIRES
                    and (k != 'NUMERO_BL' or not numero_bl_connu(licence, part))})
    for cle, valeur in {**DEFAUTS_CVI, **DEFAUTS_BL}.items():
        if not str(valeurs.get(cle) or '').strip():
            valeurs[cle] = valeur
    valeurs['DESIGNATION'] = adapter_designation(valeurs['DESIGNATION'])
    for cle, prefixe in (('NUMERO_E', 'E'), ('NUMERO_LIQUIDATION', 'L'), ('NUMERO_QUITTANCE', 'Q')):
        if valeurs[cle] and not re.match(r'^'+prefixe+r'\b', valeurs[cle], re.I):
            valeurs[cle] = prefixe + ' ' + valeurs[cle]
    try:
        quantite = sum((Decimal(str(a['quantite'])) for a in part.get('articles') or []), Decimal(0))
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
    # Le BL rassemble les conteneurs et scellés de toutes les répartitions.
    parts_bl = sorted((licence.get('repartition') or {}).get('parts') or [part], key=lambda p: int(p['numero']))
    if len(parts_bl) > 10:
        raise ValueError('Le modèle BL permet 10 conteneurs sur une page. Un modèle avec suite est nécessaire pour afficher toutes les répartitions sans omission.')
    valeurs['NOMBRE_CONTENEURS_BL'] = str(len(parts_bl))
    lignes_bl = []
    if any(p.get('conteneur') or p.get('scelle') for p in parts_bl):
        vus = set()
        for i, p in enumerate(parts_bl):
            conteneur = str(p.get('conteneur') or '').strip()
            scelle = str(p.get('scelle') or '').strip()
            if not conteneur or not scelle:
                raise ValueError(f"Conteneur ou scellé manquant sur la répartition {p.get('numero')}.")
            if conteneur in vus:
                raise ValueError('Un conteneur apparaît sur plusieurs répartitions : ' + conteneur)
            vus.add(conteneur)
            if i == 0:
                valeurs['CONTENEUR'] = conteneur
            else:
                lignes_bl.append(conteneur)
            lignes_bl.append('SEAL ' + scelle)
    for i, cle in enumerate(CHAMPS_LISTE_BL):
        valeurs[cle] = lignes_bl[i] if i < len(lignes_bl) else ''
    from asydec.declarations.nombres_lettres import nombre as en_lettres
    try:
        quantite_bl = sum((Decimal(str(a['quantite'])) for p in parts_bl for a in p.get('articles') or []), Decimal(0))
        if not quantite_bl:
            quantite_bl = Decimal(DEFAUTS_CVI['QUANTITE'].replace(',', '.'))
        valeurs['QUANTITE_BL'] = nombre(quantite_bl, 2).replace(',', '.')
        valeurs['QUANTITE_BL_LETTRES'] = en_lettres(quantite_bl)
    except (InvalidOperation, ValueError):
        raise ValueError('Quantités BL invalides sur les répartitions.') from None
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
    for cle, largeur in (('VOYAGE_BL', 45.6), ('NUMERO_BL', 75.6)):
        if valeurs.get(cle):
            import pymupdf
            if pymupdf.get_text_length(valeurs[cle], fontname='helv', fontsize=7.5) > largeur:
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


def remplir(modele, valeurs, avec_bl=False):
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
            for p in doc.getElementsByTagNameNS(W, 'p'):
                # Un paragraphe de zone de texte peut être inclus dans un autre :
                # ne traiter que les paragraphes contenant directement leurs textes.
                if p.getElementsByTagNameNS(W, 'p'):
                    continue
                contenu = texte(p)
                for m in reversed(list(BALISE.finditer(contenu))):
                    cle = m.group(1)
                    if cle not in CHAMPS:
                        raise ValueError(f'Champ CVI inconnu : {cle}.')
                    if cle not in CHAMPS_LIGNES + CHAMPS_LISTE_BL and not str(valeurs.get(cle) or '').strip():
                        raise ValueError(f'Donnée CVI manquante : {cle}. Complétez la licence ou la déclaration.')
                    trouvees.add(cle)
                    valeur = str(valeurs.get(cle, ''))
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
    return hashlib.sha256(json.dumps({'version_modele': 8, 'donnees': donnees(licence, premiere_part(licence), complements)},
                                    sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def est_a_jour(licence):
    fiche = licence.get('cvi_parts') or {}
    try:
        return (len(fiche.get('fichiers') or []) == 1 and mise_a_jour_repartitions.est_a_jour(licence)
                and facture_licence.est_a_jour(licence) and fiche.get('empreinte') == empreinte(licence)
                and all(Path(p).is_file() for p in fiche['fichiers']))
    except ValueError:
        return False
