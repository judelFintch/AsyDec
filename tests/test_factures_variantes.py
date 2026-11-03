from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
from zipfile import ZipFile
from asydec.declarations import factures as F
from asydec.declarations.nombres_lettres import nombre
from asydec.declarations.preparer_facture import base_prix
from tests.test_preparer_facture import modele


def variante():
    source=modele()
    sortie=BytesIO()
    with ZipFile(BytesIO(source)) as a, ZipFile(sortie,'w') as b:
        for i in a.infolist():
            data=a.read(i.filename)
            if i.filename=='word/document.xml':
                s=data.decode().replace('Goods Description','DESCRIPTION').replace('U. Price','UNIT KGS PRICE').replace('Total Price','T. AMOUNT')
                s=s.replace('INV NO: OLD','INV N°:EXP/25-26/OLD').replace('0499-ML1757','7654YT')
                s=s.replace('800 PKG','800 BALES').replace('$160.00','$150.00').replace('$2.00','$1.5000')
                s=s.replace('</w:body>','<w:p><w:r><w:t>AMT IN WORDS ONE HUNDRED FIFTY UNITED STATES DOLLARS</w:t></w:r></w:p><w:p><w:r><w:t>T. WEIGHT IN WORDS ONE HUNDRED KGS</w:t></w:r></w:p></w:body>')
                data=s.encode()
            b.writestr(i,data)
        b.writestr('word/header1.xml', f'<?xml version="1.0" standalone="yes"?><w:hdr xmlns:w="{F.W}"><w:p><w:r><w:t>LOGO</w:t></w:r></w:p></w:hdr>')
    return sortie.getvalue()


class FacturesVariantesTest(TestCase):
    def test_generation_par_kg_et_remplacement_lettres(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'facture.docx';p.write_bytes(variante())
            base=Path(d)/'f.db'
            g=F.importer(p,base)
            modele_genere={'supprime':False,'plaque':'T123ABC','importateur':'X','resultat':{
                'colis':[10],'resume':{'poids':200,'fob':300,'articles':[{'poids':200,'fob':300}]}}}
            self.assertEqual(F.lister_modeles(base)[0]['prix_base'],'kg')
            with patch('asydec.declarations.modeles_generes.detail',return_value=modele_genere):
                facture=F.generer(1,g,'test',base,correspondance_confirmee=True)
            with ZipFile(BytesIO(facture['contenu'])) as z:
                xml=z.read('word/document.xml').decode()
                self.assertIn('1,5000',xml)
                self.assertIn('THREE HUNDRED UNITED STATES DOLLARS',xml)
                self.assertIn('TWO HUNDRED KGS',xml)
                self.assertNotIn('7654YT',xml)
                self.assertNotIn('EXP/25-26/OLD',xml)
                self.assertIn('10 BALES',xml)
                with ZipFile(p) as original:
                    self.assertEqual(z.read('word/header1.xml'), original.read('word/header1.xml'))

    def test_inference_sans_entete_kg(self):
        b=BytesIO()
        with ZipFile(BytesIO(variante())) as a, ZipFile(b,'w') as z:
            for i in a.infolist():
                z.writestr(i,a.read(i.filename).replace(b'UNIT KGS PRICE',b'UNIT PRICE'))
        self.assertEqual(base_prix(b.getvalue()),'kg')

    def test_nombres_en_lettres(self):
        self.assertEqual(nombre(7800,True),'SEVEN THOUSAND EIGHT HUNDRED')
        self.assertEqual(nombre(20150),'TWENTY THOUSAND ONE HUNDRED FIFTY')
        self.assertEqual(nombre('7400.25',True),'SEVEN THOUSAND FOUR HUNDRED AND TWENTY FIVE CENTS')
        self.assertEqual(nombre('12.50'),'TWELVE POINT FIVE ZERO')

if __name__=='__main__':
    main()
