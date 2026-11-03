from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from zipfile import ZipFile
from asydec.declarations import factures as F


class ImportLibreTest(TestCase):
    def test_word_inconnu_conserve_puis_association_sans_changer_styles(self):
        with TemporaryDirectory() as d:
            source=Path(d)/'facture.docx'
            b=BytesIO()
            with ZipFile(b,'w') as z:
                z.writestr('[Content_Types].xml','<Types/>')
                z.writestr('word/document.xml', f'<w:document xmlns:w="{F.W}"><w:body><w:p><w:r><w:rPr><w:b/></w:rPr><w:t>FACTURE ZZ900 — 100 kg — 8 colis — 200 USD — T123ABC</w:t></w:r></w:p></w:body></w:document>')
                z.writestr('word/styles.xml',b'unchanged')
            source.write_bytes(b.getvalue())
            base=Path(d)/'f.db'
            g=F.importer(source,base)
            self.assertFalse(F.lister_modeles(base)[0]['pret'])
            zones=F.zones_disponibles(g,base)
            associations=[dict(zones[0],champ=c,valeur=v) for c,v in
                          [('NUMERO_FACTURE','ZZ900'),('POIDS','100'),('COLIS','8'),('FOB','200'),('PLAQUE','T123ABC')]]
            F.configurer_zones(g,associations,base)
            self.assertTrue(F.lister_modeles(base)[0]['pret'])
            self.assertEqual(F.lister_factures(1,base),[])
            self.assertEqual(source.read_bytes(),b.getvalue())
            with F.connexion(base) as db:
                contenu=db.execute('SELECT contenu FROM gabarits').fetchone()[0]
            with ZipFile(BytesIO(contenu)) as z:
                self.assertEqual(z.read('word/styles.xml'),b'unchanged')
                self.assertIn(b'<w:b/>',z.read('word/document.xml'))
                self.assertIn(b'{{POIDS}} kg',z.read('word/document.xml'))

    def test_zones_qui_se_chevauchent_refusees(self):
        with TemporaryDirectory() as d:
            b=BytesIO()
            with ZipFile(b,'w') as z:
                z.writestr('[Content_Types].xml','<Types/>')
                z.writestr('word/document.xml',f'<w:document xmlns:w="{F.W}"><w:body><w:p><w:r><w:t>123</w:t></w:r></w:p></w:body></w:document>')
            source=Path(d)/'f.docx'; source.write_bytes(b.getvalue())
            base=Path(d)/'f.db'; g=F.importer(source,base)
            zone=F.zones_disponibles(g,base)[0]
            with self.assertRaisesRegex(ValueError,'chevauchent'):
                F.configurer_zones(g,[dict(zone,champ='FOB',valeur='123'),dict(zone,champ='POIDS',valeur='23')],base)

if __name__=='__main__':
    main()
