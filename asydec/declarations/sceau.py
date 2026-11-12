"""Sceau décoratif du fournisseur, intégré à la zone de signature du Word."""
from functools import lru_cache
from pathlib import Path
import sys
from hashlib import sha256
from io import BytesIO
import random
import re
import textwrap
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from PIL import Image, ImageDraw
from xml.dom import minidom

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/package/2006/relationships'


def _rectangle(nom, adresse='', telephone='', email=''):
    return len(nom) > 24 or bool(adresse or telephone or email)


@lru_cache(maxsize=64)
def image_sceau(nom, adresse='', telephone='', email=''):
    """Sceau bleu transparent, forme et texte adaptés aux coordonnées disponibles."""
    import pymupdf
    nom = ' '.join(nom.split()).upper()
    rectangle = _rectangle(nom, adresse, telephone, email)
    largeur, hauteur = (300, 160) if rectangle else (180, 180)
    page_doc = pymupdf.open()
    page = page_doc.new_page(width=largeur, height=hauteur)
    bleu = (0.08, 0.23, 0.57)
    if rectangle:
        for marge, epaisseur in ((11, 1.8), (16, .7)):
            page.draw_rect((marge, marge, largeur-marge, hauteur-marge),
                           color=bleu, width=epaisseur, radius=.12)
    else:
        for rayon, epaisseur in ((77, 1.8), (71, .8)):
            page.draw_circle((90, 90), rayon, color=bleu, width=epaisseur)

    def texte_fit(texte, boite, taille, police='helv'):
        while True:
            forme = page.new_shape()
            reste = forme.insert_textbox(boite, texte, fontsize=taille,
                                         fontname=police, color=bleu, align=1)
            if reste >= 0:
                forme.commit()
                break
            taille *= .9

    if rectangle:
        lignes_nom = '\n'.join(textwrap.wrap(nom, width=34))
        texte_fit(lignes_nom, (24, 25, 276, 68), 14, 'hebo')
        page.draw_line((40, 72), (260, 72), color=bleu, width=.7)
        details = []
        if adresse:
            details.extend(textwrap.wrap(' '.join(adresse.split()), width=48))
        if telephone:
            details.append('Tel: ' + telephone)
        if email:
            details.append('E-mail: ' + email)
        texte_fit('\n'.join(details) if details else 'FOURNISSEUR', (25, 79, 275, 137), 9)
    else:
        texte_fit('FOURNISSEUR', (30, 39, 150, 57), 10, 'hebo')
        lignes = textwrap.wrap(nom, width=23) or [nom]
        texte_fit('\n'.join(lignes), (27, 65, 153, 120), 13, 'hebo')
        page.draw_line((49, 127), (131, 127), color=bleu, width=.7)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(3, 3), alpha=True)
    im = Image.frombytes('RGBA', (pix.width, pix.height), pix.samples)
    page_doc.close()
    rng = random.Random(sha256(repr((nom, adresse, telephone, email)).encode()).digest())
    alpha = im.getchannel('A').point(lambda a: int(a * .83))
    grain = ImageDraw.Draw(alpha)
    for _ in range(round(im.width * im.height * .009)):
        x, y = rng.randrange(im.width), rng.randrange(im.height)
        grain.ellipse((x, y, x + rng.randint(1, 3), y + rng.randint(1, 2)), fill=0)
    im.putalpha(alpha)
    im = im.rotate(-5 if rectangle else -7, resample=Image.Resampling.BICUBIC, expand=True)
    sortie = BytesIO()
    im.save(sortie, format='PNG')
    return sortie.getvalue()


def apposer(contenu, licence):
    """Insère le sceau dans un paragraphe dédié avant le libellé Authorized.

    Un modèle sans ce libellé est conservé tel quel. Aucun nom n'est inventé.
    """
    fournisseur = licence.get('fournisseur') or {}
    nom = str(fournisseur.get('nom') or '').strip()
    if not nom:
        return contenu
    details = tuple(str(fournisseur.get(c) or '').strip() for c in ('adresse', 'telephone', 'email'))
    from asydec.declarations.facture_kinshop import correspond
    reference = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2])) / 'ressources/factures/kinshop/sceau.png'
    original = correspond(licence) and reference.is_file()
    png = reference.read_bytes() if original else image_sceau(nom, *details)
    with Image.open(BytesIO(png)) as image:
        cx = 1150000 if original else (2100000 if _rectangle(nom, *details) else 1250000)
        cy = round(cx * image.height / image.width)
    with ZipFile(BytesIO(contenu)) as archive:
        doc = ET.fromstring(archive.read('word/document.xml'))
        cible = next((p for p in doc.iter(f'{{{W}}}p')
                      if re.search(r'authori[sz]ed.*(?:signature|stamp)',
                                   ''.join(p.itertext()), re.I)), None)
        if cible is None:
            return contenu
        relpath = 'word/_rels/document.xml.rels'
        rels = ET.fromstring(archive.read(relpath)) if relpath in archive.namelist() else ET.Element(f'{{{R}}}Relationships')
        ids = {r.get('Id') for r in rels}
        n = 1
        while f'rIdSceau{n}' in ids or f'word/media/asydec-sceau-{n}.png' in archive.namelist():
            n += 1
        rid = f'rIdSceau{n}'
        media = f'media/asydec-sceau-{n}.png'
        ET.SubElement(rels, f'{{{R}}}Relationship', Id=rid,
                      Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/image', Target=media)
        types = ET.fromstring(archive.read('[Content_Types].xml'))
        ns = 'http://schemas.openxmlformats.org/package/2006/content-types'
        if not any(t.get('Extension') == 'png' for t in types):
            ET.SubElement(types, f'{{{ns}}}Default', Extension='png', ContentType='image/png')
        ids_dessin = [int(e.get('id')) for e in doc.iter() if e.tag.endswith('}docPr') and str(e.get('id', '')).isdigit()]
        dessin = max(ids_dessin, default=0) + 1
        run = ET.fromstring(f'''<w:r xmlns:w="{W}" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:drawing>
          <wp:inline distT="0" distB="0" distL="0" distR="0">
          <wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{dessin}" name="Sceau fournisseur"/>
          <wp:cNvGraphicFramePr/><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
          <pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="Sceau fournisseur"/><pic:cNvPicPr/></pic:nvPicPr>
          <pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
          <pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic>
          </wp:inline></w:drawing></w:r>''')
        # minidom conserve les préfixes et déclarations des modèles Word (mc:Ignorable).
        original = minidom.parseString(archive.read('word/document.xml'))
        position = list(doc.iter(f'{{{W}}}p')).index(cible)
        cible_dom = original.getElementsByTagNameNS(W, 'p')[position]
        fragment = minidom.parseString(ET.tostring(run, encoding='utf-8'))
        paragraphe = original.createElementNS(W, 'w:p')
        proprietes = minidom.parseString(f'<w:pPr xmlns:w="{W}"><w:keepNext/>'
                                        '<w:spacing w:before="0" w:after="0"/>'
                                        '<w:jc w:val="right"/></w:pPr>')
        paragraphe.appendChild(original.importNode(proprietes.documentElement, True))
        paragraphe.appendChild(original.importNode(fragment.documentElement, True))
        cible_dom.parentNode.insertBefore(paragraphe, cible_dom)
        sortie = BytesIO()
        with ZipFile(sortie, 'w') as dest:
            remplacements = {'word/document.xml': original.toxml(encoding='utf-8'),
                             '[Content_Types].xml': ET.tostring(types, encoding='utf-8', xml_declaration=True),
                             relpath: ET.tostring(rels, encoding='utf-8', xml_declaration=True)}
            for info in archive.infolist():
                dest.writestr(info, remplacements.pop(info.filename, archive.read(info.filename)))
            for chemin, data in remplacements.items():
                dest.writestr(chemin, data)
            dest.writestr('word/' + media, png)
        return sortie.getvalue()
