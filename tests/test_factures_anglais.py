from io import BytesIO
from unittest import TestCase
from zipfile import ZipFile
from tests.test_facture_licence import modele, texte
from asydec.declarations.preparer_facture import libelles_anglais


class LibellesAnglaisTest(TestCase):
    def test_entetes_adaptes_aux_poids_et_styles_preserves(self):
        source = modele()
        out = BytesIO()
        with ZipFile(BytesIO(source)) as a, ZipFile(out, 'w') as z:
            for info in a.infolist():
                b = a.read(info.filename)
                if info.filename == 'word/document.xml':
                    b = b.replace(b'Quantity', b'QUANTITE').replace(b'Unit W', b'PRIX UNITAIRE').replace(b'Total Weight', b'MONTANT')
                z.writestr(info, b)
        source = out.getvalue()
        result = libelles_anglais(source)
        t = texte(result)
        self.assertIn('UNIT WEIGHT', t)
        self.assertIn('TOTAL WEIGHT', t)
        self.assertIn('QUANTITY', t)
        self.assertNotIn('PRIX UNITAIRE', t)
        self.assertNotIn('MONTANT', t)
        self.assertEqual(libelles_anglais(result), result)
        with ZipFile(BytesIO(source)) as a, ZipFile(BytesIO(result)) as b:
            self.assertEqual(a.read('word/media/logo.png'), b.read('word/media/logo.png'))
            self.assertEqual(a.read('word/document.xml').count(b'Arial Black'), b.read('word/document.xml').count(b'Arial Black'))
