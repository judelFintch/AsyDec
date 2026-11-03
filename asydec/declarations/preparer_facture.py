"""Reconnaissance des factures commerciales avec tableau et packing list.

Seuls les textes variables sont remplacés ; aucun paragraphe, dessin ou style
n'est ajouté ni retiré. Les deux représentations des zones de texte sont traitées.
"""
from io import BytesIO
import re
from zipfile import ZipFile

from asydec.declarations import factures as F


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
    m = re.search(r'\d[\d\s.,]*\d|\d', contenu)
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
            if entete == ['N°', 'GOODS DESCRIPTION', 'QUANTITY', 'U. PRICE', 'TOTAL PRICE']:
                type_ = 'facture'
            elif entete == ['N°', 'GOODS DESCRIPTION', 'QUANTITY', 'UNIT W', 'TOTAL WEIGHT']:
                type_ = 'colisage'
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
                    champ = {'TOTAL FOB': 'FOB', 'TOTAL FREIGHT': 'FRET', 'INSSURENCE': 'ASSURANCE',
                             'TOTAL CIF': 'CIF_USD', 'TOTAL WEIGHT': 'POIDS'}.get(label)
                    if champ:
                        champ_cellule(cs[1], champ)
            reperes.append(descriptions)
            types.append(type_)
        if sorted(types) != ['colisage', 'facture'] or not reperes[0] or reperes[0] != reperes[1]:
            raise ValueError('Structure non reconnue : utilisez un modèle balisé ou une facture avec sa liste de colisage aux mêmes articles.')
        for p in paragraphes(doc):
            s = texte(p)
            motifs = [
                (r'(?i)(?<=INV NO:)\s*([^\s]+)', 'NUMERO_FACTURE', 1),
                (r'(?i)(?<=DATE:)\s*(\d{2}[–/-]\d{2}[–/-]\d{4})', 'DATE_FACTURE', 1),
                (r'(?i)\b(\d[\d ]*)(?=\s+PKG\b)', 'COLIS', 1),
                (r'(?i)(?<=Total Weight )(\d[\d ]*)(?=\s+Kgs)', 'POIDS', 1),
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
                m = re.search(r'\b\d{4}-ML\d{4}\b', s)
                if m:
                    remplacer(p, m.start(), m.end(), '{{NUMERO_MANIFESTE}}')
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


def preparer_plaque(contenu):
    """Repère une plaque déjà balisée, un libellé explicite ou la zone UMBA connue."""
    archive, parties = F._parties(contenu)
    try:
        change = False
        for doc in parties.values():
            if any('{{PLAQUE}}' in texte(p) for p in paragraphes(doc)):
                continue
            for p in paragraphes(doc):
                s = texte(p)
                m = re.search(r'(?i)(?:PLAQUE|TRUCK\s*(?:NO\.?|NUMBER)|REGISTRATION\s*(?:NO\.?|NUMBER))\s*:\s*(\S[^\r\n]*)', s)
                if m:
                    remplacer(p, m.start(1), m.end(1), '{{PLAQUE}}')
                    change = True
            # Le modèle UMBA fourni possède cette zone de saisie vide, à côté
            # de REGISTRATION NO’S. Traiter Choice et Fallback sans redessiner.
            if 'REGISTRATION NO’S' in texte(doc) and 'MANIFEST NO:' in texte(doc):
                for forme in doc.getElementsByTagName('v:shape'):
                    if forme.getAttribute('id') == 'Text Box 27' and not texte(forme).strip():
                        ts = forme.getElementsByTagNameNS(F.W, 't')
                        if ts:
                            F._ecrire(ts[0], '{{PLAQUE}}')
                            change = True
                for ancre in doc.getElementsByTagName('wp:anchor'):
                    noms = ancre.getElementsByTagName('wp:docPr')
                    if any(n.getAttribute('name') == 'Text Box 27' for n in noms) and not texte(ancre).strip():
                        ts = ancre.getElementsByTagNameNS(F.W, 't')
                        if ts:
                            F._ecrire(ts[0], '{{PLAQUE}}')
                            change = True
        if not change:
            return contenu
        sortie = BytesIO()
        with ZipFile(sortie, 'w') as cible:
            for info in archive.infolist():
                cible.writestr(info, F.serialiser(parties[info.filename]) if info.filename in parties else archive.read(info.filename))
        return sortie.getvalue()
    finally:
        archive.close()
