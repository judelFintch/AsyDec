"""Extraction des parties et des articles du modèle de licence IB."""
import re
import unicodedata

COLONNES_PRODUITS = ('tarif_douanier', 'designation', 'pays_origine', 'quantite',
                     'unite', 'prix_unitaire', 'devise')


def normaliser(texte):
    return ''.join(c for c in unicodedata.normalize('NFD', texte.lower())
                   if not unicodedata.combining(c))


def extraire_details(texte, tableaux=()):
    resultat = {'soussigne': {}, 'fournisseur': {}, 'produits': []}
    bloc = re.search(r'je\s+soussign[eé]\s+(.+?)(?=d[eé]clare\s+r[eé]aliser)', texte, re.I | re.S)
    if bloc:
        lignes = [re.sub(r'\s+', ' ', l).strip() for l in bloc.group(1).splitlines() if l.strip()]
        if lignes:
            resultat['soussigne']['nom'] = lignes[0]
        adresse = []
        for ligne in lignes[1:]:
            if re.search(r'\bTel\s*:', ligne, re.I):
                contact = re.search(r'Tel\s*:\s*(.+?)(?:\s+-\s+|$)(.*)', ligne, re.I)
                if contact:
                    resultat['soussigne']['telephone'] = contact[1].strip()
                    resultat['soussigne']['email'] = contact[2].strip()
            elif re.search(r'N[°ºo]\s*N\.?R\.?C', ligne, re.I):
                resultat['soussigne']['identifiants'] = ligne
            else:
                adresse.append(ligne)
        resultat['soussigne']['adresse'] = '\n'.join(adresse)
    compte = re.search(r'liste\s*des\s*produits\s*\(\s*(\d+)\s*\)', texte, re.I)
    if compte:
        resultat['nombre_produits_attendu'] = int(compte[1])
    # Secours texte, utile pour les scans ; les cellules PDF ont priorité.
    nom = re.search(r'nom\s+du\s+fournisseur\s+[eé]tranger\s*[:\-]?\s*([^\n]+)', texte, re.I)
    if nom:
        resultat['fournisseur']['nom'] = nom[1].strip()
    details = re.search(r'd[eé]tails\s+du\s+fournisseur\s*[:\-]?\s*(.+?)(?=N[°ºo]\s*de\s*t[eé]l[eé]phone|4\)\s*Monnaie)', texte, re.I | re.S)
    if details:
        resultat['fournisseur']['adresse'] = re.sub(r'[ \t]+', ' ', details[1]).strip()
    for tableau in tableaux:
        if not tableau:
            continue
        entete = [normaliser(c or '') for c in tableau[0]]
        if len(entete) == 7 and 'tarif' in entete[0] and 'designation' in entete[1]:
            for ligne in tableau[1:]:
                if len(ligne) != 7 or not re.fullmatch(r'\d{8,12}', (ligne[0] or '').strip()):
                    continue
                resultat['produits'].append({cle: (valeur or '').strip()
                                            for cle, valeur in zip(COLONNES_PRODUITS, ligne)})
        fournisseur = False
        for ligne in tableau:
            cellules = [c.strip() for c in ligne if c and c.strip()]
            if not cellules:
                continue
            libelle = normaliser(cellules[0])
            if 'nom du fournisseur' in libelle:
                fournisseur = True
                if len(cellules) > 1:
                    resultat['fournisseur']['nom'] = cellules[-1]
            elif fournisseur and ('monnaie' in libelle or re.match(r'4\)', libelle)):
                fournisseur = False
            elif fournisseur and len(cellules) > 1:
                for mot, cle in [('details du fournisseur', 'adresse'), ('telephone', 'telephone'),
                                 ('e-mail', 'email'), ('fax', 'fax')]:
                    if mot in libelle:
                        resultat['fournisseur'][cle] = cellules[-1] if cellules[-1] != '.' else ''
    return resultat
