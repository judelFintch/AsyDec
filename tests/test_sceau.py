from io import BytesIO
from unittest import TestCase
from zipfile import ZipFile
from xml.dom import minidom
from PIL import Image
from asydec.declarations.sceau import apposer, image_sceau
from asydec.declarations.facture_simple import _docx, _para, _run


class SceauTest(TestCase):
    def test_nom_fournisseur_et_transparence(self):
        a = image_sceau('ETS KATANGA')
        self.assertEqual(a, image_sceau('ETS KATANGA'))
        self.assertNotEqual(a, image_sceau('AUTRE IMPORTATEUR'))
        im = Image.open(BytesIO(a))
        self.assertEqual(im.mode, 'RGBA')
        self.assertEqual(im.getchannel('A').getextrema()[0], 0)

    def test_ancrage_et_relation_valides(self):
        source = _docx(_para(_run('Authorized signature and stamp')))
        resultat = apposer(source, {'fournisseur': {'nom': 'KINSHOP GENERAL TRADING FZE'}})
        with ZipFile(BytesIO(resultat)) as z:
            doc = minidom.parseString(z.read('word/document.xml'))
            rel = minidom.parseString(z.read('word/_rels/document.xml.rels'))
            ancre = doc.getElementsByTagNameNS('http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing', 'inline')
            self.assertEqual(len(ancre), 1)
            cible = rel.getElementsByTagNameNS('http://schemas.openxmlformats.org/package/2006/relationships', 'Relationship')[0]
            self.assertIn('word/' + cible.getAttribute('Target'), z.namelist())

    def test_pas_de_nom_ou_pas_de_zone(self):
        source = _docx(_para(_run('Authorized signature and stamp')))
        self.assertEqual(apposer(source, {}), source)
        source = _docx(_para(_run('Autre texte')))
        self.assertEqual(apposer(source, {'fournisseur': {'nom': 'KINSHOP GENERAL TRADING FZE'}}), source)

    def test_sceau_du_fournisseur_et_jamais_de_l_importateur(self):
        source = _docx(_para(_run('Authorized signature and stamp')))
        licence = {'fournisseur': {'nom': 'KINSHOP GENERAL TRADING FZE'},
                   'soussigne': {'nom': 'ETS KATANGA'}}
        resultat = apposer(source, licence)
        from pathlib import Path
        with ZipFile(BytesIO(resultat)) as z:
            self.assertEqual(z.read('word/media/asydec-sceau-1.png'),
                             Path('ressources/factures/kinshop/sceau.png').read_bytes())
        self.assertEqual(apposer(source, {'soussigne': licence['soussigne']}), source)
