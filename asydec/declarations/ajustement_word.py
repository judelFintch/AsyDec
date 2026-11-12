"""Ajustement typographique des valeurs écrites dans un modèle Word existant.

Les modèles convertis depuis un PDF (KINSHOP…) placent les traits, le tampon et la signature à des
positions fixes de la page, tandis que le texte suit le flux. Une valeur qui prend une ligne de plus
que le texte d'origine décale tout ce qui suit et le fait passer sous les dessins.

Règle appliquée : chaque paragraphe modifié doit tenir dans le même nombre de lignes que son texte
d'origine, dans la même largeur (cellule de tableau ou colonne de section). Si besoin, la taille de
ses caractères est réduite, mesurée avec les métriques de Calibri (ou d'Helvetica, plus large, à défaut).
"""
from functools import lru_cache
from pathlib import Path
import os
import re

from asydec.declarations import factures as F

W = F.W
TAILLE_DEFAUT = 22  # demi-points, docDefaults des modèles
HAUTEUR_LIGNE = 1.2207  # interligne simple de Calibri, en multiple de la taille


@lru_cache(maxsize=4)
def _police(gras):
    import pymupdf
    noms = ('Calibrib.ttf', 'calibrib.ttf') if gras else ('Calibri.ttf', 'calibri.ttf')
    dossiers = [Path('/Applications/Microsoft Word.app/Contents/Resources/DFonts'),
                Path('/Library/Fonts'), Path.home() / 'Library/Fonts',
                Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts']
    for dossier in dossiers:
        for nom in noms:
            chemin = dossier / nom
            if chemin.is_file():
                try:
                    return pymupdf.Font(fontfile=str(chemin))
                except Exception:
                    pass
    return pymupdf.Font('hebo' if gras else 'helv')


def _enfant(element, nom):
    return next((n for n in element.childNodes if n.localName == nom), None)


def _val(element, nom, attribut='val'):
    noeud = _enfant(element, nom) if element is not None else None
    return noeud.getAttribute('w:' + attribut) if noeud is not None else None


def styles(xml_styles):
    """styleId → dict(sz, gras, gauche, droite) des styles de paragraphe."""
    resultat = {}
    if not xml_styles:
        return resultat
    from xml.dom import minidom
    doc = minidom.parseString(xml_styles)
    for style in doc.getElementsByTagNameNS(W, 'style'):
        ppr, rpr = _enfant(style, 'pPr'), _enfant(style, 'rPr')
        ind = _enfant(ppr, 'ind') if ppr is not None else None
        sz = _val(rpr, 'sz')
        resultat[style.getAttribute('w:styleId')] = dict(
            sz=int(sz) if sz else None,
            gras=rpr is not None and _enfant(rpr, 'b') is not None,
            gauche=int(ind.getAttribute('w:left') or 0) if ind is not None else 0,
            droite=int(ind.getAttribute('w:right') or 0) if ind is not None else 0)
    return resultat


def _style(p, table_styles):
    ppr = _enfant(p, 'pPr')
    nom = _val(ppr, 'pStyle')
    return table_styles.get(nom or '', {})


def retraits(p, table_styles):
    ppr = _enfant(p, 'pPr')
    style = _style(p, table_styles)
    ind = _enfant(ppr, 'ind') if ppr is not None else None
    gauche, droite = style.get('gauche', 0), style.get('droite', 0)
    if ind is not None:
        gauche = int(ind.getAttribute('w:left') or ind.getAttribute('w:start') or gauche)
        droite = int(ind.getAttribute('w:right') or ind.getAttribute('w:end') or droite)
    return gauche, droite


def _runs(p):
    return [r for r in p.getElementsByTagNameNS(W, 'r')]


def _proprietes_run(run, p, table_styles):
    rpr = _enfant(run, 'rPr')
    style = _style(p, table_styles)
    sz = _val(rpr, 'sz')
    gras = style.get('gras', False)
    if rpr is not None and _enfant(rpr, 'b') is not None:
        gras = _val(rpr, 'b') not in ('0', 'false')
    espacement = int(_val(rpr, 'spacing') or 0) / 20
    echelle = int(_val(rpr, 'w') or 100) / 100
    return int(sz) if sz else (style.get('sz') or TAILLE_DEFAUT), gras, espacement, echelle


def _caracteres(p, table_styles, facteur=1.0):
    """Suite (caractère, largeur en points) ; '\n' pour un saut de ligne."""
    sortie = []
    for run in _runs(p):
        sz, gras, espacement, echelle = _proprietes_run(run, p, table_styles)
        taille = max(1, round(sz * facteur)) / 2
        police = _police(gras)
        for noeud in run.childNodes:
            if noeud.localName == 't':
                for c in F._texte(noeud):
                    sortie.append((c, police.text_length(c, fontsize=taille) * echelle + espacement))
            elif noeud.localName == 'tab':
                sortie.append((' ', taille))
            elif noeud.localName == 'br' and noeud.getAttribute('w:type') in ('', 'textWrapping'):
                sortie.append(('\n', 0))
    return sortie


def nombre_lignes(p, largeur, table_styles, facteur=1.0):
    """Lignes occupées par le paragraphe dans « largeur » twips (coupure aux espaces et tirets)."""
    disponible = max(1.0, largeur / 20)
    etat = dict(lignes=1, x=0.0, mot=0.0)

    def poser():
        mot = etat['mot']
        if etat['x'] > 0 and etat['x'] + mot > disponible:
            etat['lignes'] += 1
            etat['x'] = 0.0
        while mot > disponible:  # mot plus long que la ligne : Word le coupe
            etat['lignes'] += 1
            mot -= disponible
        etat['x'] += mot
        etat['mot'] = 0.0

    for c, l in _caracteres(p, table_styles, facteur):
        if c == '\n':
            poser()
            etat['lignes'] += 1
            etat['x'] = 0.0
        elif c == ' ':
            poser()
            etat['x'] += l
        else:
            etat['mot'] += l
            if c == '-':
                poser()
    poser()
    return etat['lignes']


def largeurs(doc, table_styles):
    """{paragraphe: largeur utile en twips} pour les paragraphes du corps et des cellules."""
    corps = doc.getElementsByTagNameNS(W, 'body')[0]
    enfants = [n for n in corps.childNodes if n.localName in ('p', 'tbl', 'sectPr')]
    # Regroupement par section : une section se termine par un paragraphe porteur de sectPr.
    sections, courante = [], []
    for n in enfants:
        if n.localName == 'sectPr':
            sections.append((courante, n))
            courante = []
            continue
        courante.append(n)
        ppr = _enfant(n, 'pPr') if n.localName == 'p' else None
        sect = _enfant(ppr, 'sectPr') if ppr is not None else None
        if sect is not None:
            sections.append((courante, sect))
            courante = []
    resultat = {}
    for elements, sect in sections:
        colonnes = colonnes_section(sect)
        indice = 0
        for n in elements:
            if n.localName == 'tbl':
                for tc in n.getElementsByTagNameNS(W, 'tc'):
                    tcpr = _enfant(tc, 'tcPr')
                    tcw = _val(tcpr, 'tcW', 'w')
                    if not tcw or not tcw.isdigit():
                        continue
                    for p in tc.childNodes:
                        if p.localName == 'p':
                            g, d = retraits(p, table_styles)
                            resultat[p] = int(tcw) - g - d
                continue
            avant, total, texte_vu = 0, 0, False
            for noeud in n.getElementsByTagNameNS(W, '*'):
                if noeud.localName == 't' and F._texte(noeud).strip():
                    texte_vu = True
                if noeud.localName == 'br' and noeud.getAttribute('w:type') == 'column':
                    total += 1
                    if not texte_vu:
                        avant += 1
            colonne = colonnes[min(indice + avant, len(colonnes) - 1)]
            g, d = retraits(n, table_styles)
            resultat[n] = colonne - g - d
            indice += total
    return resultat


def colonnes_section(sect):
    pg, marges = _enfant(sect, 'pgSz'), _enfant(sect, 'pgMar')
    utile = int(pg.getAttribute('w:w')) - int(marges.getAttribute('w:left') or 0) - int(marges.getAttribute('w:right') or 0)
    cols = _enfant(sect, 'cols')
    if cols is None:
        return [utile]
    definies = [int(c.getAttribute('w:w')) for c in cols.childNodes if c.localName == 'col']
    if definies:
        return definies
    nombre = int(cols.getAttribute('w:num') or 1)
    espace = int(cols.getAttribute('w:space') or 720)
    return [(utile - (nombre - 1) * espace) // nombre] * nombre


ORDRE_PPR = ('pStyle', 'keepNext', 'keepLines', 'pageBreakBefore', 'framePr', 'widowControl', 'numPr',
             'suppressLineNumbers', 'pBdr', 'shd', 'tabs', 'suppressAutoHyphens', 'kinsoku', 'wordWrap',
             'overflowPunct', 'topLinePunct', 'autoSpaceDE', 'autoSpaceDN', 'bidi', 'adjustRightInd', 'snapToGrid',
             'spacing', 'ind', 'contextualSpacing', 'mirrorIndents', 'suppressOverlap', 'jc', 'textDirection',
             'textAlignment', 'textboxTightWrap', 'outlineLvl', 'divId', 'cnfStyle', 'rPr', 'sectPr', 'pPrChange')


def propriete_paragraphe(p, nom):
    """Élément de pPr, créé à sa place dans l'ordre du schéma Word s'il manque."""
    ppr = next((n for n in p.childNodes if n.localName == 'pPr'), None)
    if ppr is None:
        ppr = p.ownerDocument.createElementNS(W, 'w:pPr')
        p.insertBefore(ppr, p.firstChild)
    noeud = next((n for n in ppr.childNodes if n.localName == nom), None)
    if noeud is None:
        noeud = p.ownerDocument.createElementNS(W, 'w:' + nom)
        rang = ORDRE_PPR.index(nom)
        suivant = next((n for n in ppr.childNodes if n.localName in ORDRE_PPR
                        and ORDRE_PPR.index(n.localName) > rang), None)
        ppr.insertBefore(noeud, suivant)
    return noeud


def cadrer(p, gauche=None, droite=None, alignement=None):
    if gauche is not None or droite is not None:
        ind = propriete_paragraphe(p, 'ind')
        if gauche is not None:
            ind.setAttribute('w:left', str(gauche))
        if droite is not None:
            ind.setAttribute('w:right', str(droite))
    if alignement:
        propriete_paragraphe(p, 'jc').setAttribute('w:val', alignement)


def definir_taille(p, facteur, table_styles):
    for run in _runs(p):
        if not any(n.localName == 't' for n in run.childNodes):
            continue
        sz = _proprietes_run(run, p, table_styles)[0]
        nouvelle = max(1, round(sz * facteur))
        rpr = _enfant(run, 'rPr')
        if rpr is None:
            rpr = run.ownerDocument.createElementNS(W, 'w:rPr')
            run.insertBefore(rpr, run.firstChild)
        for cle in ('sz', 'szCs'):
            noeud = _enfant(rpr, cle)
            if noeud is None:
                noeud = run.ownerDocument.createElementNS(W, 'w:' + cle)
                rpr.appendChild(noeud)
            noeud.setAttribute('w:val', str(nouvelle))


def ajuster(p, largeur, lignes_max, table_styles, taille_min=10):
    """Réduit la taille du paragraphe jusqu'à tenir dans lignes_max lignes ; renvoie le facteur appliqué."""
    tailles = [_proprietes_run(r, p, table_styles)[0] for r in _runs(p) if any(n.localName == 't' for n in r.childNodes)]
    if not tailles or nombre_lignes(p, largeur, table_styles) <= lignes_max:
        return 1.0
    facteur_min = taille_min / max(tailles)
    facteur = 1.0
    while facteur > facteur_min:
        facteur = max(facteur_min, facteur - 0.02)
        if nombre_lignes(p, largeur, table_styles, facteur) <= lignes_max:
            break
    definir_taille(p, facteur, table_styles)
    # Hauteur de ligne d'origine conservée : le texte qui suit ne remonte pas sous les traits.
    espacement = propriete_paragraphe(p, 'spacing')
    regle = espacement.getAttribute('w:lineRule') or 'auto'
    if regle == 'auto':
        multiple = int(espacement.getAttribute('w:line') or 240) / 240
        espacement.setAttribute('w:line', str(round(max(tailles) / 2 * HAUTEUR_LIGNE * multiple * 20)))
        espacement.setAttribute('w:lineRule', 'atLeast')
    return facteur


def instantane(doc, table_styles, paragraphes):
    """Texte et nombre de lignes d'origine de chaque paragraphe mesurable."""
    tailles = largeurs(doc, table_styles)
    from asydec.declarations.preparer_facture import texte
    return {p: (texte(p), nombre_lignes(p, tailles[p], table_styles)) for p in paragraphes if p in tailles}


def respecter(doc, table_styles, origine, une_ligne=(), taille_min=10):
    """Ajuste chaque paragraphe dont le texte a changé à son nombre de lignes d'origine."""
    from asydec.declarations.preparer_facture import texte
    tailles = largeurs(doc, table_styles)
    for p, (ancien, lignes) in origine.items():
        if p not in tailles or texte(p) == ancien or not texte(p).strip():
            continue
        ajuster(p, tailles[p], 1 if p in une_ligne else lignes, table_styles, taille_min)


def texte_brut(valeur):
    return re.sub(r'\s+', ' ', str(valeur)).strip()
