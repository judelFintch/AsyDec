"""Reconnaissance des factures commerciales avec tableau et packing list.

Seuls les textes variables sont remplacés ; aucun dessin ni style n'est ajouté ou retiré. Deux
exceptions, sans toucher police, taille ni interligne : la date absente reçoit sa ligne vide prévue
(preparer_date), et un paragraphe vide portant un saut de section est retiré (retirer_page_vide).
Les deux représentations des zones de texte sont traitées.
"""
from io import BytesIO
import re
from zipfile import ZipFile

from asydec.declarations import factures as F


# Montant en lettres : « AMT IN WORDS … UNITED STATES DOLLARS » ou « … US DOLLARS ».
MONTANT_LETTRES = r'(?i)AMT IN WORDS\s+(.+?)(?=\s+(?:UNITED\s+STATES|U\.?\s?S\.?)\s+DOLLARS)'


def libelles_anglais(contenu):
    """Traduit les libellés fixes, sans toucher aux données ni aux styles du Word."""
    archive, parties = F._parties(contenu)
    modifies = {}
    try:
        for nom, doc in parties.items():
            change = False
            for table in doc.getElementsByTagNameNS(F.W, 'tbl'):
                rows = [n for n in table.childNodes if n.localName == 'tr']
                if not rows:
                    continue
                cells = [n for n in rows[0].childNodes if n.localName == 'tc']
                if len(cells) != 5 or 'DESCRIPTION' not in texte(cells[1]).upper():
                    continue
                packing = bool(re.search(r'(?i)\bKGS?\b|\{\{POIDS', ''.join(texte(r) for r in rows[1:])))
                traductions = {'QUANTITE': 'QUANTITY', 'QUANTITÉ': 'QUANTITY',
                               'PRIX UNITAIRE': 'UNIT WEIGHT' if packing else 'UNIT PRICE',
                               'MONTANT': 'TOTAL WEIGHT' if packing else 'TOTAL AMOUNT'}
                for cell in cells:
                    for p in paragraphes(cell):
                        s = texte(p)
                        anglais = traductions.get(s.strip().upper())
                        if anglais:
                            debut = len(s) - len(s.lstrip())
                            remplacer(p, debut, len(s.rstrip()), anglais)
                            change = True
            for p in paragraphes(doc):
                for m in reversed(list(re.finditer(r'\bConsignée\b', texte(p), re.I))):
                    remplacer(p, m.start(), m.end(), 'Consignee')
                    change = True
            if change:
                modifies[nom] = F.serialiser(doc)
        if not modifies:
            return contenu
        sortie = BytesIO()
        with ZipFile(sortie, 'w') as cible:
            for info in archive.infolist():
                cible.writestr(info, modifies.get(info.filename, archive.read(info.filename)))
        return sortie.getvalue()
    finally:
        archive.close()


def cadrer_immatriculation(contenu, plaque=None):
    """Aligne libellé et immatriculation d'après la géométrie du modèle.

    Les dessins VML et DrawingML sont traités indépendamment, sans identifiant
    de zone ni coordonnées propres à un fournisseur.
    """
    def rectangle(forme, tag):
        if tag == 'v:shape':
            style = forme.getAttribute('style')
            def mesure(cle, defaut=0):
                m = re.search(r'(?:^|;)' + cle + r':(-?[0-9.,]+)pt(?:;|$)', style)
                return float(m[1].replace(',', '.')) if m else defaut
            return mesure('margin-left'), mesure('margin-top'), mesure('width')
        def position(tag):
            ps = forme.getElementsByTagName(tag)
            offsets = ps[0].getElementsByTagName('wp:posOffset') if ps else []
            return float(F._texte(offsets[0])) / 12700 if offsets else 0
        extents = forme.getElementsByTagName('wp:extent')
        largeur = float(extents[0].getAttribute('cx')) / 12700 if extents else 0
        return position('wp:positionH'), position('wp:positionV'), largeur

    def support(forme):
        # Les positions relatives ne sont comparables que pour le même ancrage.
        courant, dernier = forme, None
        while courant is not None:
            if courant.namespaceURI == F.W and courant.localName == 'p':
                dernier = courant
            courant = courant.parentNode
        return dernier

    libelle_re = re.compile(r"REGISTRATION\s+(?:NO[’']?S?|NUMBER)\s*[:.]?", re.I)
    plaque_re = re.compile(r'(?:[A-Z]{1,3}\s*\d{2,5}[A-Z]{1,4})(?:\s*/\s*[A-Z]{1,3}\s*\d{2,5}[A-Z]{1,4})?', re.I)
    archive, parties = F._parties(contenu)
    modifies = {}
    try:
        for nom, doc in parties.items():
            change = False
            for tag in ('v:shape', 'wp:anchor'):
                formes = list(doc.getElementsByTagName(tag))
                for libelle in formes:
                    titre = texte(libelle).strip()
                    if not libelle_re.fullmatch(titre):
                        continue
                    x, y, largeur = rectangle(libelle, tag)
                    voisines = [s for s in formes if s is not libelle and support(s) is support(libelle)]
                    candidates = [s for s in voisines if texte(s).strip() and
                                  ((plaque and texte(s).strip() == plaque.strip())
                                   or (not plaque and (plaque_re.fullmatch(texte(s).strip())
                                                       or texte(s).strip() == '{{PLAQUE}}')))]
                    if not candidates:
                        continue
                    valeur_zone = min(candidates, key=lambda s: abs(rectangle(s, tag)[0] - x)
                                      + 4 * abs(rectangle(s, tag)[1] - y))
                    px, _, pw = rectangle(valeur_zone, tag)
                    limites = [rectangle(s, tag)[0] for s in voisines
                               if re.match(r'(?i)TRAILER\s*\(', texte(s).strip())
                               and rectangle(s, tag)[0] > x and abs(rectangle(s, tag)[1] - y) < 8]
                    droite = min(limites) - 5.75 if limites else max(x + largeur, px + pw)
                    largeur = droite - x
                    if largeur <= 0:
                        continue
                    valeur = texte(valeur_zone).strip()
                    remplacer(libelle, 0, len(texte(libelle)), titre + '  ' + valeur)
                    remplacer(valeur_zone, 0, len(texte(valeur_zone)), '')
                    for sz in list(libelle.getElementsByTagNameNS(F.W, 'sz')) + list(libelle.getElementsByTagNameNS(F.W, 'szCs')):
                        sz.setAttribute('w:val', str(min(int(sz.getAttribute('w:val') or 19), 19)))
                    if tag == 'v:shape':
                        style = re.sub(r'(?<![\w-])width:[^;]+', f'width:{largeur:g}pt', libelle.getAttribute('style'))
                        libelle.setAttribute('style', style)
                    else:
                        for extent in libelle.getElementsByTagName('wp:extent'):
                            extent.setAttribute('cx', str(round(largeur * 12700)))
                        for extent in libelle.getElementsByTagName('a:ext'):
                            if extent.hasAttribute('cx'):
                                extent.setAttribute('cx', str(round(largeur * 12700)))
                    change = True
            if change:
                modifies[nom] = F.serialiser(doc)
        if not modifies:
            return contenu
        sortie = BytesIO()
        with ZipFile(sortie, 'w') as cible:
            for info in archive.infolist():
                cible.writestr(info, modifies.get(info.filename, archive.read(info.filename)))
        return sortie.getvalue()
    finally:
        archive.close()


def paragraphes(doc):
    # Les paragraphes de dessins peuvent être imbriqués dans un paragraphe porteur.
    return [p for p in doc.getElementsByTagNameNS(F.W, 'p')
            if not p.getElementsByTagNameNS(F.W, 'p')]


def texte(element):
    return ''.join(F._texte(t) for t in element.getElementsByTagNameNS(F.W, 't'))


def remplacer(element, debut, fin, valeur):
    position = 0
    premier = True
    for t in element.getElementsByTagNameNS(F.W, 't'):
        actuel = F._texte(t)
        a, b = position, position + len(actuel)
        position = b
        if a < fin and b > debut:
            F._ecrire(t, actuel[:max(0, debut-a)] + (valeur if premier else '') +
                      (actuel[fin-a:] if fin < b else ''))
            premier = False


def champ_cellule(cellule, champ):
    contenu = texte(cellule)
    if not contenu.strip():
        return
    # Garde les unités, symboles monétaires et espaces autour de la valeur.
    m = re.search(r'\d[\d\s.,;]*\d|\d', contenu)
    if not m:
        raise ValueError('Valeur numérique introuvable dans le tableau de facture.')
    remplacer(cellule, m.start(), m.end(), '{{'+champ+'}}')


def preparer(contenu):
    """Prépare les tableaux reconnus, sinon demande un modèle déjà balisé."""
    archive, parties = F._parties(contenu)
    try:
        doc = parties['word/document.xml']
        reperes = []
        types = []
        for table in doc.getElementsByTagNameNS(F.W, 'tbl'):
            lignes = [n for n in table.childNodes if n.localName == 'tr']
            cellules = lambda r: [n for n in r.childNodes if n.localName == 'tc']
            if not lignes:
                continue
            entete = [texte(c).strip().upper() for c in cellules(lignes[0])]
            premiere = next((cellules(r) for r in lignes[1:]
                              if len(cellules(r)) == 5 and texte(cellules(r)[0]).strip().isdigit()), None)
            if len(entete) != 5 or 'DESCRIPTION' not in entete[1] or entete[2] not in ('QUANTITY','QUANTITE','QTY') or premiere is None:
                continue
            if 'WEIGHT' in entete[4] or re.search(r'(?i)\bKGS?\b', texte(premiere[4])):
                type_ = 'colisage'
            elif any(c in entete[3] for c in ('PRICE','PRIX')):
                type_ = 'facture'
            else:
                continue
            descriptions = []
            for ligne in lignes[1:]:
                cs = cellules(ligne)
                if len(cs) == 5 and texte(cs[0]).strip().isdigit():
                    i = len(descriptions) + 1
                    descriptions.append(texte(cs[1]).strip())
                    champ_cellule(cs[2], f'COLIS_{i}')
                    if type_ == 'facture':
                        champ_cellule(cs[3], f'PRIX_UNITAIRE_{i}')
                        champ_cellule(cs[4], f'FOB_{i}')
                    else:
                        champ_cellule(cs[4], f'POIDS_{i}')
                elif len(cs) == 2:
                    label = texte(cs[0]).strip().upper()
                    champ = {'TOTAL FOB': 'FOB', 'TOTAL FREIGHT': 'FRET', 'FREIGHT `': 'FRET', 'FREIGHT': 'FRET', 'INSURENCE': 'ASSURANCE', 'INSSURENCE': 'ASSURANCE',
                             'TOTAL CIF': 'CIF_USD', 'TOTAL WEIGHT': 'POIDS'}.get(label)
                    if champ:
                        champ_cellule(cs[1], champ)
                elif len(cs) == 1 and re.fullmatch(r'\s*\d[\d ,.;]*\s*', texte(cs[0])):
                    champ_cellule(cs[0], 'COLIS')
                elif len(cs) == 5 and not texte(cs[0]).strip() and re.search(r'(?i)\bKGS?\b', texte(cs[4])):
                    champ_cellule(cs[4], 'POIDS')
            reperes.append(descriptions)
            types.append(type_)
        if sorted(types) != ['colisage', 'facture'] or not reperes[0] or reperes[0] != reperes[1]:
            raise ValueError('Structure non reconnue : utilisez un modèle balisé ou une facture avec sa liste de colisage aux mêmes articles.')
        for p in paragraphes(doc):
            s = texte(p)
            motifs = [
                # « INV NO : », « INV N° : », « INVOICE : » et aussi « Invoice no : », « Invoice N° : », « Invoice number : ».
                (r'(?i)\b(?:INV(?:OICE)?\s*(?:NO\.?|N[°º]|NUMBER)|INVOICE)\s*:\s*([^\s]+)', 'NUMERO_FACTURE', 1),
                (r'(?i)DATE\s*:\s*(\d{2}[–/-]\d{2}[–/-]\d{4})', 'DATE_FACTURE', 1),
                (r'(?i)\b(\d[\d ]*)(?=\s+(?:PKG|BALES)\b)', 'COLIS', 1),
                (r'(?i)Total Weight\s+(\d[\d ,.]*)\s+Kgs', 'POIDS', 1),
                (r'(?i)TOTAL\s+WEIGHT\s*:\s*KGS\s*(\d[\d ,.]*)', 'POIDS', 1),
                (r'(?i)TOTAL\s+AMOUNT\s*:\s*\$\s*(\d[\d ,.]*)', 'CIF_USD', 1),
                (r'(?i)Insurrance\s*:\s*\$\s*(\d[\d ,.]*)', 'ASSURANCE', 1),
                (r'(?i)Freight\s*:\s*\$\s*(\d[\d ,.]*)', 'FRET', 1),
                (MONTANT_LETTRES, 'FOB_LETTRES', 1),
                (r'(?i)T\. WEIGHT IN WORDS\s+(.+?)(?=\s+KGS)', 'POIDS_LETTRES', 1),
            ]
            for motif, champ, groupe in motifs:
                for m in reversed(list(re.finditer(motif, s))):
                    remplacer(p, m.start(groupe), m.end(groupe), '{{'+champ+'}}')
                s = texte(p)
        sortie = BytesIO()
        with ZipFile(sortie, 'w') as cible:
            for info in archive.infolist():
                cible.writestr(info, F.serialiser(doc) if info.filename == 'word/document.xml' else archive.read(info.filename))
        resultat = sortie.getvalue()
        F.inspecter(resultat)
        return resultat, reperes[0]
    finally:
        archive.close()


def dater_manifeste(contenu, date):
    """Date de départ du manifeste routier : conserve TZ, styles et vues Word.

    La date de facture, les références de commande et les autres dates ne sont
    pas concernées. Les modèles routiers portent la date suivie du pays TZ.
    """
    archive, parties = F._parties(contenu)
    modifies = {}
    try:
        for nom, doc in parties.items():
            if not re.search(r'(?i)MANIFEST\s+NO\s*:', texte(doc)):
                continue
            change = False
            for p in paragraphes(doc):
                for m in reversed(list(re.finditer(r'\b\d{2}[/-]\d{2}[/-]\d{4}(?=\s+TZ\b)', texte(p)))):
                    if m[0] != date:
                        remplacer(p, m.start(), m.end(), date)
                        change = True
            if change:
                modifies[nom] = F.serialiser(doc)
        if not modifies:
            return contenu
        sortie = BytesIO()
        with ZipFile(sortie, 'w') as cible:
            for info in archive.infolist():
                cible.writestr(info, modifies.get(info.filename, archive.read(info.filename)))
        return sortie.getvalue()
    finally:
        archive.close()


def preparer_manifeste(contenu):
    """Reconnaît le numéro d'origine ou déjà balisé dans les deux vues du manifeste."""
    archive, parties = F._parties(contenu)
    try:
        doc = parties['word/document.xml']
        precedent = ''
        change = False
        for p in paragraphes(doc):
            s = texte(p)
            if 'MANIFEST NO:' in s.upper() or 'MANIFEST NO:' in precedent.upper():
                m = re.search(r'(?i)MANIFEST NO:\s*([A-Z0-9][A-Z0-9/-]*)', s)
                if m:
                    debut, fin = m.span(1)
                elif 'MANIFEST NO:' in precedent.upper() and re.fullmatch(r'\s*[A-Za-z0-9][A-Za-z0-9/-]*\s*', s):
                    m = re.search(r'[A-Za-z0-9][A-Za-z0-9/-]*', s)
                    debut, fin = m.span()
                else:
                    m = None
                if m:
                    remplacer(p, debut, fin, '{{NUMERO_MANIFESTE}}')
                    change = True
            if s.strip():
                precedent = s
        if not change:
            return contenu
        sortie = BytesIO()
        with ZipFile(sortie, 'w') as cible:
            for info in archive.infolist():
                cible.writestr(info, F.serialiser(doc) if info.filename == 'word/document.xml' else archive.read(info.filename))
        return sortie.getvalue()
    finally:
        archive.close()


def preparer_lettres(contenu):
    """Balise le montant en lettres (FOB) resté en texte fixe, y compris dans les modèles déjà
    importés : sinon la facture garderait le montant d'exemple du Word."""
    archive, parties = F._parties(contenu)
    try:
        doc = parties['word/document.xml']
        change = False
        for p in paragraphes(doc):
            s = texte(p)
            for m in reversed(list(re.finditer(MONTANT_LETTRES, s))):
                if m.group(1).strip() != '{{FOB_LETTRES}}':
                    remplacer(p, m.start(1), m.end(1), '{{FOB_LETTRES}}')
                    change = True
        if not change:
            return contenu
        sortie = BytesIO()
        with ZipFile(sortie, 'w') as cible:
            for info in archive.infolist():
                cible.writestr(info, F.serialiser(doc) if info.filename == 'word/document.xml' else archive.read(info.filename))
        return sortie.getvalue()
    finally:
        archive.close()


def preparer_plaque(contenu):
    """Repère une plaque déjà balisée, un libellé explicite ou la zone UMBA connue."""
    archive, parties = F._parties(contenu)
    try:
        change = False
        modifies = set()
        for nom, doc in parties.items():
            if any('{{PLAQUE}}' in texte(p) for p in paragraphes(doc)):
                continue
            for p in paragraphes(doc):
                s = texte(p)
                m = re.search(r'(?i)(?:PLAQUE|TRUCK\s*(?:NO\.?|NUMBER)|REGISTRATION\s*(?:NO\.?|NUMBER))\s*:\s*(\S[^\r\n]*)', s)
                if m:
                    remplacer(p, m.start(1), m.end(1), '{{PLAQUE}}')
                    change = True
                    modifies.add(nom)
            # Le modèle UMBA fourni possède cette zone de saisie vide, à côté
            # de REGISTRATION NO’S. Traiter Choice et Fallback sans redessiner.
            if 'REGISTRATION NO’S' in texte(doc) and 'MANIFEST NO:' in texte(doc):
                noms_plaques = {'Text Box 27'}
                for forme in doc.getElementsByTagName('v:shape'):
                    style = forme.getAttribute('style')
                    if (re.search(r'margin-left:53[.,]1pt(?:;|$)', style) and
                            re.search(r'margin-top:-2pt(?:;|$)', style) and not texte(forme).strip()):
                        noms_plaques.add(forme.getAttribute('id'))
                    if forme.getAttribute('id') in noms_plaques and not texte(forme).strip():
                        ts = forme.getElementsByTagNameNS(F.W, 't')
                        if ts:
                            F._ecrire(ts[0], '{{PLAQUE}}')
                            change = True
                            modifies.add(nom)
                for ancre in doc.getElementsByTagName('wp:anchor'):
                    noms = ancre.getElementsByTagName('wp:docPr')
                    if any(n.getAttribute('name') in noms_plaques for n in noms) and not texte(ancre).strip():
                        ts = ancre.getElementsByTagNameNS(F.W, 't')
                        if ts:
                            F._ecrire(ts[0], '{{PLAQUE}}')
                            change = True
                            modifies.add(nom)
        if not change:
            return contenu
        sortie = BytesIO()
        with ZipFile(sortie, 'w') as cible:
            for info in archive.infolist():
                cible.writestr(info, F.serialiser(parties[info.filename]) if info.filename in modifies else archive.read(info.filename))
        return sortie.getvalue()
    finally:
        archive.close()


def base_prix(contenu):
    """Infère FOB/kg ou FOB/colis à partir des valeurs d’exemple du Word."""
    def valeur(s):
        s = re.sub(r'[^0-9,.;]', '', s).replace(';', ',')
        if not s:
            return None
        if ',' in s and '.' in s:
            if s.rfind(',') > s.rfind('.'):
                s = s.replace('.', '').replace(',', '.')
            else:
                s = s.replace(',', '')
        else:
            s = s.replace(',', '.')
        try:
            return float(s)
        except ValueError:
            return None
    archive, parties = F._parties(contenu)
    try:
        factures, poids = [], []
        for table in parties['word/document.xml'].getElementsByTagNameNS(F.W, 'tbl'):
            rows = [r for r in table.childNodes if r.localName == 'tr']
            if not rows:
                continue
            cs = lambda r: [c for c in r.childNodes if c.localName == 'tc']
            header = [texte(c).strip().upper() for c in cs(rows[0])]
            if len(header) != 5 or 'DESCRIPTION' not in header[1]:
                continue
            if 'KGS' in header[3] or 'KG PRICE' in header[3]:
                return 'kg'
            valeurs = [cs(r) for r in rows[1:] if len(cs(r)) == 5 and texte(cs(r)[0]).strip().isdigit()]
            if not valeurs:
                continue
            if 'WEIGHT' in header[4] or 'KGS' in texte(valeurs[0][4]).upper():
                poids = [valeur(texte(r[4])) for r in valeurs]
            else:
                factures = [(valeur(texte(r[2])), valeur(texte(r[3])), valeur(texte(r[4]))) for r in valeurs]
        votes = {'kg': 0, 'colis': 0}
        if len(poids) == len(factures):
            for (colis, prix, fob), kg in zip(factures, poids):
                if not prix or not fob:
                    continue
                for base, quantite in (('kg', kg), ('colis', colis)):
                    if quantite and abs(prix*quantite-fob)/fob < .08:
                        votes[base] += 1
        return 'kg' if votes['kg'] > votes['colis'] else 'colis'
    finally:
        archive.close()


def _reecrire(archive, doc):
    sortie = BytesIO()
    with ZipFile(sortie, 'w') as cible:
        for info in archive.infolist():
            cible.writestr(info, F.serialiser(doc) if info.filename == 'word/document.xml' else archive.read(info.filename))
    return sortie.getvalue()


def _enfants(noeud, nom):
    return [n for n in noeud.childNodes if n.nodeType == n.ELEMENT_NODE and n.namespaceURI == F.W and n.localName == nom]


def preparer_date(contenu):
    """Modèle sans {{DATE_FACTURE}} : la ligne vide juste au-dessus de « INV N° », dans la même zone
    de texte, reçoit « Date: {{DATE_FACTURE}} » avec la police et la taille de la ligne « INV N° »
    (disposition des autres modèles du même fournisseur). Aucun paragraphe n'est ajouté."""
    if 'DATE_FACTURE' in inspecter_champs(contenu):
        return contenu
    archive, parties = F._parties(contenu)
    try:
        doc = parties['word/document.xml']
        change = False
        for p in paragraphes(doc):
            if not texte(p).strip().upper().startswith('INV N'):
                continue
            avant = p.previousSibling
            while avant is not None and avant.nodeType != avant.ELEMENT_NODE:
                avant = avant.previousSibling
            if (avant is None or avant.namespaceURI != F.W or avant.localName != 'p' or texte(avant).strip()
                    or avant.getElementsByTagNameNS(F.W, 'drawing') or avant.getElementsByTagNameNS(F.W, 'pict')):
                continue
            modele = next((r for r in _enfants(p, 'r') if r.getElementsByTagNameNS(F.W, 't')), None)
            if modele is None:
                continue
            run = modele.cloneNode(True)
            for enfant in list(run.childNodes):
                if not (enfant.nodeType == enfant.ELEMENT_NODE and enfant.localName == 'rPr'):
                    run.removeChild(enfant)
            t = doc.createElementNS(F.W, 'w:t')
            run.appendChild(t)
            F._ecrire(t, 'Date: {{DATE_FACTURE}}')
            avant.appendChild(run)
            change = True
        return _reecrire(archive, doc) if change else contenu
    finally:
        archive.close()


def inspecter_champs(contenu):
    return F.inspecter(contenu, exiger=False)


def _vide(p):
    """Paragraphe sans texte visible ni dessin : seulement tabulations, retours ou espaces."""
    return not texte(p).strip() and not any(p.getElementsByTagNameNS(F.W, n) for n in ('drawing', 'pict', 'object'))


def retirer_page_vide(contenu):
    """Un saut de section porté par un paragraphe vide ajoute une ligne en bas de page : quand la page
    est pleine (packing list), Word crée une page blanche avant la section suivante (manifeste).
    Le saut de section passe dans le paragraphe précédent et le paragraphe vide est retiré ;
    police, taille, interligne et position des dessins ne changent pas."""
    archive, parties = F._parties(contenu)
    try:
        doc = parties['word/document.xml']
        corps = doc.getElementsByTagNameNS(F.W, 'body')[0]
        change = False
        for p in _enfants(corps, 'p'):
            ppr = next(iter(_enfants(p, 'pPr')), None)
            section = next(iter(_enfants(ppr, 'sectPr')), None) if ppr is not None else None
            # Certains modèles portent le tampon flottant sur le paragraphe du
            # saut de section : cette ligne vide déborde seule sur une page.
            tampon = (section is not None and not texte(p).strip()
                      and bool(p.getElementsByTagNameNS(F.W, 'drawing'))
                      and not p.getElementsByTagName('wp:inline')
                      and all(a.getElementsByTagName('wp:wrapNone')
                              for a in p.getElementsByTagName('wp:anchor')))
            if section is None or (not _vide(p) and not tampon):
                continue
            if any(t.getAttributeNS(F.W, 'val') == 'continuous' for t in _enfants(section, 'type')):
                continue
            avant = p.previousSibling
            while avant is not None and avant.nodeType != avant.ELEMENT_NODE:
                avant = avant.previousSibling
            if avant is None or avant.namespaceURI != F.W or avant.localName != 'p':
                continue
            ppr_avant = next(iter(_enfants(avant, 'pPr')), None)
            if ppr_avant is not None and _enfants(ppr_avant, 'sectPr'):
                continue
            if ppr_avant is None:
                ppr_avant = doc.createElementNS(F.W, 'w:pPr')
                avant.insertBefore(ppr_avant, avant.firstChild)
            if tampon:
                # Conserver les images dans une ligne d'ancrage minimale ;
                # aucun contenu commercial ou tampon n'est supprimé.
                if not _vide(avant):
                    continue
                for run in list(_enfants(p, 'r')):
                    if run.getElementsByTagNameNS(F.W, 'drawing'):
                        p.removeChild(run)
                        avant.appendChild(run)
                for br in list(avant.getElementsByTagNameNS(F.W, 'br')):
                    if not br.getAttributeNS(F.W, 'type'):
                        br.parentNode.removeChild(br)
                spacing = next(iter(_enfants(ppr_avant, 'spacing')), None)
                if spacing is None:
                    spacing = doc.createElementNS(F.W, 'w:spacing')
                    ppr_avant.appendChild(spacing)
                for cle, valeur in [('before', '0'), ('after', '0'), ('line', '20'), ('lineRule', 'exact')]:
                    spacing.setAttribute('w:' + cle, valeur)
            suivi = next(iter(_enfants(ppr_avant, 'pPrChange')), None)
            ppr.removeChild(section)
            ppr_avant.insertBefore(section, suivi)
            corps.removeChild(p)
            change = True
        return _reecrire(archive, doc) if change else contenu
    finally:
        archive.close()
