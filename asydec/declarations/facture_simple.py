"""Facture simple AsyDec : facture commerciale et packing list d'une part, créées sans modèle.

Deux documents Word (.docx) séparés, écrits directement en OOXML, sans dépendance, A4, Arial, tenant
sur une page autant que possible (taille du texte réduite quand les articles sont nombreux).
- INVOICE : présentée comme les factures commerciales réelles (FCM) — en-tête du vendeur, destinataire,
  numéro et date, puis N°, désignation, quantité, prix unitaire, prix total et totaux FOB / fret /
  assurance / CIF et FOB en toutes lettres. Sans code SH, origine, part ni données douanières.
- PACKING LIST : même en-tête, plus part, unités, poids, FOB et poids en toutes lettres
  (sans licence, DEC, plaque, conteneur, scellé ni manifeste).
"""
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

from asydec.declarations.nombres_lettres import nombre as en_lettres
from asydec.formats import nombre

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
LARGEUR = 10306  # A4 (11 906) moins deux marges de 800 twips
GRIS = 'E7E6E6'
TRAIT = '<w:{0} w:val="single" w:sz="{1}" w:space="0" w:color="000000"/>'


def _run(texte, gras=False, taille=9, souligne=False, couleur=None):
    proprietes = ('<w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>' + ('<w:b/>' if gras else '')
                  + ('<w:u w:val="single"/>' if souligne else '') + (f'<w:color w:val="{couleur}"/>' if couleur else '')
                  + f'<w:sz w:val="{round(taille * 2)}"/><w:szCs w:val="{round(taille * 2)}"/></w:rPr>')
    morceaux = str(texte).split('\n')
    contenu = '<w:br/>'.join(f'<w:t xml:space="preserve">{escape(m)}</w:t>' for m in morceaux)
    return f'<w:r>{proprietes}{contenu}</w:r>'


def _para(*runs, alignement=None, apres=40, avant=0, bordure_bas=False):
    jc = f'<w:jc w:val="{alignement}"/>' if alignement else ''
    bord = f'<w:pBdr>{TRAIT.format("bottom", 12)}</w:pBdr>' if bordure_bas else ''
    return (f'<w:p><w:pPr>{bord}<w:spacing w:before="{avant}" w:after="{apres}" w:line="240" w:lineRule="auto"/>{jc}</w:pPr>'
            f'{"".join(runs)}</w:p>')


def _cellule(contenu, largeur, fond=None, fusion=1, alignement=None, gras=False, taille=9, bordures=None):
    """contenu : texte, ou liste de paragraphes déjà construits. bordures : dict côté → épaisseur (0 = aucune)."""
    if isinstance(contenu, list):
        paragraphes = ''.join(contenu) or _para()
    else:
        paragraphes = _para(_run(contenu, gras=gras, taille=taille), alignement=alignement, apres=0)
    bords = ''
    if bordures is not None:
        bords = '<w:tcBorders>' + ''.join(TRAIT.format(c, e) if e else f'<w:{c} w:val="nil"/>'
                                          for c, e in bordures.items()) + '</w:tcBorders>'
    proprietes = (f'<w:tcW w:w="{largeur}" w:type="dxa"/>' + (f'<w:gridSpan w:val="{fusion}"/>' if fusion > 1 else '')
                  + bords + (f'<w:shd w:val="clear" w:color="auto" w:fill="{fond}"/>' if fond else '') + '<w:vAlign w:val="center"/>')
    return f'<w:tc><w:tcPr>{proprietes}</w:tcPr>{paragraphes}</w:tc>'


def _tableau(colonnes, lignes, bordures=True, hauteur=None, entete=False):
    """colonnes : largeurs ; lignes : listes de cellules déjà construites. entete : 1re ligne répétée."""
    trait = TRAIT.replace('{1}', '6') if bordures else '<w:{0} w:val="nil"/>'
    bords = ''.join(trait.format(cote) for cote in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'))
    grille = ''.join(f'<w:gridCol w:w="{c}"/>' for c in colonnes)
    corps = ''
    for i, l in enumerate(lignes):
        proprietes = '<w:cantSplit/>' + (f'<w:trHeight w:val="{hauteur}"/>' if hauteur else '') + ('<w:tblHeader/>' if entete and i == 0 else '')
        corps += f'<w:tr><w:trPr>{proprietes}</w:trPr>' + ''.join(l) + '</w:tr>'
    return (f'<w:tbl><w:tblPr><w:tblW w:w="{sum(colonnes)}" w:type="dxa"/><w:jc w:val="center"/><w:tblBorders>{bords}</w:tblBorders>'
            '<w:tblLayout w:type="fixed"/><w:tblCellMar><w:top w:w="15" w:type="dxa"/><w:left w:w="80" w:type="dxa"/>'
            '<w:bottom w:w="15" w:type="dxa"/><w:right w:w="80" w:type="dxa"/>'
            f'</w:tblCellMar></w:tblPr><w:tblGrid>{grille}</w:tblGrid>{corps}</w:tbl>')


def _montant(valeur):
    return nombre(float(valeur), 2)


def _quantite(q):
    return nombre(q) if q == q.to_integral_value() else nombre(float(q), 3)


def _taille(donnees):
    """(taille du texte, hauteur de ligne) des tableaux : réduites quand les articles sont nombreux,
    pour que le document tienne sur une page."""
    n = len(donnees['lignes'])
    return (9.5, 300) if n <= 14 else (8.5, 250) if n <= 22 else (7.5, 215) if n <= 32 else (7, 195)


def _contact(d):
    return '   '.join(x for x in (('Tel: ' + d['telephone']) if d.get('telephone') else '',
                                  ('E-mail: ' + d['email']) if d.get('email') else '') if x)


def _entete(titre, licence, donnees, references):
    """En-tête du vendeur, titre, destinataire à gauche et références à droite."""
    fournisseur = licence.get('fournisseur') or {}
    soussigne = licence.get('soussigne') or {}
    xml = []
    if fournisseur.get('nom'):
        xml.append(_para(_run(fournisseur['nom'], gras=True, taille=20), alignement='center', apres=40))
    for ligne in (fournisseur.get('adresse', ''), _contact(fournisseur)):
        if ligne:
            xml.append(_para(_run(ligne, taille=9.5), alignement='center', apres=0))
    xml.append(_para(apres=120, bordure_bas=True))
    xml.append(_para(_run(titre, gras=True, taille=18, souligne=True), alignement='center', avant=160, apres=160))
    references = [(l, v) for l, v in references if v]
    gauche, libelle, valeur = 5900, 1500, LARGEUR - 5900 - 1500
    destinataire = [l for l in (soussigne.get('nom', ''), soussigne.get('adresse', '')) if l]
    bloc_gauche = [_para(_run('Consignee:', gras=True, taille=9.5), apres=20)] + [
        _para(_run(l, gras=i == 0, taille=9.5), apres=0) for i, l in enumerate(destinataire)]
    lignes = []
    for i, (l, v) in enumerate(references or [('', '')]):
        fusion = '<w:vMerge w:val="restart"/>' if i == 0 else '<w:vMerge/>'
        cellule = _cellule(bloc_gauche if i == 0 else [], gauche).replace('<w:tcPr>', '<w:tcPr>' + fusion, 1)
        lignes.append([cellule, _cellule(l + ':' if l else '', libelle, gras=True, taille=9.5),
                       _cellule(v, valeur, taille=9.5)])
    xml.append(_tableau([gauche, libelle, valeur], lignes, bordures=False))
    xml.append(_para(apres=120))
    return ''.join(xml)


def _fob_en_lettres(donnees):
    return _para(_run('TOTAL FOB IN WORDS: ', gras=True, taille=9),
                 _run(en_lettres(donnees['fob'], monnaie=True) + ' US DOLLARS', taille=9), avant=120, apres=20)


def _signature(licence, compact=False):
    nom = (licence.get('fournisseur') or {}).get('nom', '')
    return (_para(_run('For ' + nom if nom else 'Authorized signature', gras=True), alignement='right',
                  avant=200 if compact else 360, apres=500 if compact else 700)
            + _para(_run('Authorized signature and stamp', taille=8.5), alignement='right', apres=0))


def _facture(licence, donnees):
    t, h = _taille(donnees)
    colonnes = [600, 5106, 1400, 1450, 1750]
    entete = ['N°', 'GOODS DESCRIPTION', 'QUANTITY', 'U. PRICE', 'TOTAL PRICE']
    lignes = [[_cellule(e, c, fond=GRIS, gras=True, alignement='center', taille=t) for e, c in zip(entete, colonnes)]]
    for i, l in enumerate(donnees['lignes'], 1):
        valeurs = [(str(i), 'center'), (l['designation'], None), (_quantite(l['quantite']), 'center'),
                   ('$ ' + _montant(l['prix_unitaire']), 'right'), ('$ ' + _montant(l['valeur']), 'right')]
        lignes.append([_cellule(v, c, alignement=a, taille=t) for (v, a), c in zip(valeurs, colonnes)])
    gauche = sum(colonnes[:-1])
    for libelle, valeur in (('TOTAL FOB', donnees['fob']), ('FREIGHT', 0), ('INSURANCE', 0), ('TOTAL CIF', donnees['fob'])):
        final = libelle == 'TOTAL CIF'
        lignes.append([_cellule(libelle, gauche, fusion=len(colonnes) - 1, alignement='right' if final else None,
                                gras=True, taille=t, fond=GRIS if final else None),
                       _cellule('$ ' + _montant(valeur), colonnes[-1], alignement='right', gras=True, taille=t,
                                fond=GRIS if final else None)])
    references = [('INV NO', donnees['numero']), ('DATE', donnees['date'])]
    return (_entete('INVOICE', licence, donnees, references)
            + _tableau(colonnes, lignes, hauteur=h, entete=True) + _fob_en_lettres(donnees) + _signature(licence, h < 300))


def _colisage(licence, donnees):
    t, h = _taille(donnees)
    colonnes = [600, 4806, 1400, 1700, 1800]
    entete = ['N°', 'GOODS DESCRIPTION', 'QUANTITY', 'UNIT', 'WEIGHT (KG)']
    lignes = [[_cellule(e, c, fond=GRIS, gras=True, alignement='center', taille=t) for e, c in zip(entete, colonnes)]]
    for i, l in enumerate(donnees['lignes'], 1):
        valeurs = [(str(i), 'center'), (l['designation'], None), (_quantite(l['quantite']), 'center'),
                   (l.get('unite', ''), 'center'), (nombre(l['poids'], 2), 'right')]
        lignes.append([_cellule(v, c, alignement=a, taille=t) for (v, a), c in zip(valeurs, colonnes)])
    lignes.append([_cellule('TOTAL', colonnes[0] + colonnes[1], fusion=2, alignement='right', gras=True, taille=t, fond=GRIS),
                   _cellule(_quantite(donnees['quantites']), colonnes[2], alignement='center', gras=True, taille=t, fond=GRIS),
                   _cellule('', colonnes[3], fond=GRIS),
                   _cellule(nombre(donnees['poids'], 2), colonnes[4], alignement='right', gras=True, taille=t, fond=GRIS)])
    references = [('INV NO', donnees['numero']), ('DATE', donnees['date']),
                  ('SHIPMENT', f"All {donnees['total_parts']} parts" if donnees['part'] == 'global'
                   else f"Part {donnees['part']} of {donnees['total_parts']}")]
    xml = _entete('PACKING LIST', licence, donnees, references)
    return (xml + _tableau(colonnes, lignes, hauteur=h, entete=True)
            + _fob_en_lettres(donnees)
            + _para(_run('TOTAL WEIGHT IN WORDS: ', gras=True, taille=9), _run(en_lettres(donnees['poids']) + ' KILOGRAMS', taille=9), apres=20)
            + _signature(licence, h < 300))


def creer_facture(licence, donnees):
    """Octets du .docx de la facture commerciale."""
    return _docx(_facture(licence, donnees))


def creer_packing_list(licence, donnees):
    """Octets du .docx de la packing list."""
    return _docx(_colisage(licence, donnees))


def _docx(corps):
    corps = (corps + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="700" w:right="800" w:bottom="700" '
             'w:left="800" w:header="400" w:footer="400" w:gutter="0"/></w:sectPr>')
    document = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{W}"><w:body>{corps}</w:body></w:document>'
    types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/word/document.xml" '
             'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    relations = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                 'Target="word/document.xml"/></Relationships>')
    sortie = BytesIO()
    with ZipFile(sortie, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', types)
        archive.writestr('_rels/.rels', relations)
        archive.writestr('word/document.xml', document)
    return sortie.getvalue()
