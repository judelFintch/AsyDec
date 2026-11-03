"""Reconnaissance des factures commerciales avec tableau et packing list.

Seuls les textes variables sont remplacés ; aucun paragraphe, dessin ou style
n'est ajouté ni retiré. Les deux représentations des zones de texte sont traitées.
"""
from io import BytesIO
import re
from zipfile import ZipFile

from asydec.declarations import factures as F


# Montant en lettres : « AMT IN WORDS … UNITED STATES DOLLARS » ou « … US DOLLARS ».
MONTANT_LETTRES = r'(?i)AMT IN WORDS\s+(.+?)(?=\s+(?:UNITED\s+STATES|U\.?\s?S\.?)\s+DOLLARS)'


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
                (r'(?i)\b(?:INV\s*(?:NO\.?|N[°º])|INVOICE)\s*:\s*([^\s]+)', 'NUMERO_FACTURE', 1),
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
