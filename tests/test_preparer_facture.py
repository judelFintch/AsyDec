from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
from xml.dom import minidom
from zipfile import ZipFile

from asydec.declarations import factures as F
from asydec.declarations.preparer_facture import preparer


def modele():
    def p(t):
        return '<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>'+t+'</w:t></w:r></w:p>'
    def row(cs):
        return '<w:tr>'+''.join('<w:tc>'+p(c)+'</w:tc>' for c in cs)+'</w:tr>'
    tables = []
    for facture in (True, False):
        tables.append('<w:tbl>'+row(['N°','Goods Description','Quantity', 'U. Price' if facture else 'Unit W', 'Total Price' if facture else 'Total Weight'])+
                      row(['1','TEXTILE','80','$2.00' if facture else '', '$160.00' if facture else 'KGS 100.00'])+
                      row(['TOTAL FOB' if facture else 'TOTAL WEIGHT', '$160.00' if facture else 'KGS 100 KG'])+
                      '</w:tbl>')
    xml = f'<w:document xmlns:w="{F.W}"><w:body data="a&#10;b&#9;c">'+p('INV NO: OLD DATE:27–07–2026')+p('PLAQUE : T123ABC')+''.join(tables)+p('800 PKG')+p('Total Weight 100 Kgs')+p('MANIFEST NO:')+p('   0499-ML1757')+p('MANIFEST NO: 0499-ML1757')+'</w:body></w:document>'
    b=BytesIO()
    with ZipFile(b,'w') as z:
        z.writestr('[Content_Types].xml','<Types/>')
        z.writestr('word/document.xml',xml)
        z.writestr('word/media/logo.png',b'unchanged')
    return b.getvalue()


class PreparationTest(TestCase):
    def test_structure_preservee_et_champs_reconnus(self):
        source=modele()
        contenu, descriptions=preparer(source)
        self.assertEqual(descriptions,['TEXTILE'])
        self.assertIn('FOB_1', F.inspecter(contenu))
        def structure(xml):
            d=minidom.parseString(xml)
            for t in d.getElementsByTagNameNS(F.W,'t'):
                for enfant in list(t.childNodes):
                    t.removeChild(enfant)
                t.removeAttribute('xml:space') if t.hasAttribute('xml:space') else None
            return d.toxml()
        with ZipFile(BytesIO(source)) as a, ZipFile(BytesIO(contenu)) as b:
            self.assertEqual(structure(a.read('word/document.xml')),structure(b.read('word/document.xml')))
            self.assertEqual(a.read('word/media/logo.png'),b.read('word/media/logo.png'))

    def test_import_generation_et_garde_correspondance(self):
        with TemporaryDirectory() as d:
            chemin=Path(d)/'facture.docx'
            chemin.write_bytes(modele())
            base=Path(d)/'factures.db'
            g=F.importer(chemin,base)
            self.assertEqual(F.importer(chemin,base),g)
            self.assertEqual(F.lister_modeles(base)[0]['articles'],['TEXTILE'])
            modele_genere={'supprime':False,'importateur':'X','plaque':'T974EBZ', 'resultat':{
                'colis':[20], 'resume':{'poids':200,'fob':80,'articles':[{'poids':200,'fob':80}]}}}
            with patch('asydec.declarations.modeles_generes.detail',return_value=modele_genere):
                with self.assertRaisesRegex(ValueError,'Confirmez'):
                    F.generer(1,g,'test',base)
                f=F.generer(1,g,'test',base,correspondance_confirmee=True)
                with ZipFile(BytesIO(f['contenu'])) as z:
                    xml=z.read('word/document.xml').decode()
                    self.assertNotIn('{{',xml)
                    self.assertIn('200,00',xml)
                    self.assertIn('$0,4000',xml)  # prix = ratio de l'article : 80 USD ÷ 200 kg
                    self.assertNotIn('4,0000',xml.replace('0,4000',''))  # plus FOB ÷ colis (80 ÷ 20)
                    self.assertIn('20 PKG',xml)
                    self.assertNotIn('0499-ML1757', xml)
                    self.assertEqual(xml.count(f['manifeste']), 2)
                modele_genere['resultat']['resume']['articles']=[]
                with self.assertRaisesRegex(ValueError,'contient 1 articles'):
                    F.generer(2,g,'test',base,correspondance_confirmee=True)

if __name__=='__main__':
    main()
