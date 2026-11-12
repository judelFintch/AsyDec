import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from asydec.declarations import generateur_factures as g

XML = '''<ASYCUDA><Property><Nbers><Total_number_of_packages>{total_colis}</Total_number_of_packages></Nbers></Property>
<Traders><Exporter><Exporter_name>UMBA TEXTILES FZC
DAR ES SALAAM</Exporter_name></Exporter><Consignee><Consignee_name>CLIENT TEST
AV TEST 1</Consignee_name></Consignee></Traders>
<Transport><Means_of_transport><Border_information><Identity>T1/T2</Identity></Border_information></Means_of_transport>
<Delivery_terms><Place>Lubumbashi</Place></Delivery_terms></Transport>
<Valuation><Gs_Invoice><Currency_code>USD</Currency_code></Gs_Invoice>
<Total><Total_invoice>1000</Total_invoice><Total_weight>3000</Total_weight></Total></Valuation>
<Item><Packages><Number_of_packages>10</Number_of_packages></Packages>
<Tarification><HScode><Commodity_code>63090090</Commodity_code></HScode><Item_price>750</Item_price></Tarification>
<Goods_description><Commercial_Description>FRIPERIE</Commercial_Description></Goods_description>
<Valuation_item><Weight_itm><Gross_weight_itm>2000</Gross_weight_itm></Weight_itm></Valuation_item></Item>
<Item><Packages><Number_of_packages>5</Number_of_packages></Packages>
<Tarification><HScode><Commodity_code>63041900</Commodity_code></HScode><Item_price>250</Item_price></Tarification>
<Valuation_item><Weight_itm><Gross_weight_itm>1000</Gross_weight_itm></Weight_itm></Valuation_item></Item>
<Item><Packages><Number_of_packages/></Packages></Item>
</ASYCUDA>'''


class GenerateurXml(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.xml = self.dossier / 'decl.xml'
        self.xml.write_text(XML.format(total_colis=15), encoding='utf-8')

    def test_dossier_depuis_xml(self):
        m = g.modele_depuis_xml(self.xml)
        self.assertEqual((m['importateur'], m['plaque']), ('CLIENT TEST', 'T1/T2'))
        self.assertEqual(m['resultat']['resume']['fob'], Decimal(1000))
        self.assertEqual(m['resultat']['colis'], [Decimal(10), Decimal(5)])
        self.assertEqual([p['anglais'] for p in g.propositions_articles(m)], ['USED CLOTHING', 'USED BEDSPREADS'])
        self.assertEqual(g.profil_dossier(m)['fournisseur'], 'UMBA TEXTILES FZC')
        self.assertEqual(m['alertes'], [])

    def test_generation_stable_et_distincte_par_xml(self):
        base = self.dossier / 'f.db'
        m = g.modele_depuis_xml(self.xml)
        r1 = g.generer_modele(m, 'marine', g.profil_dossier(m), 'test', base=base)
        r2 = g.generer_modele(m, 'compact', g.profil_dossier(m), 'test', base=base)
        self.assertEqual(r1['numero'], r2['numero'])
        self.assertEqual(set(r1['documents']), {'facture', 'packing', 'manifeste'})
        autre = self.dossier / 'autre.xml'
        autre.write_text(XML.format(total_colis=15) + ' ', encoding='utf-8')
        m2 = g.modele_depuis_xml(autre)
        r3 = g.generer_modele(m2, 'marine', g.profil_dossier(m2), 'test', base=base)
        self.assertNotEqual(r1['numero'], r3['numero'])

    def test_alerte_total_incoherent(self):
        self.xml.write_text(XML.format(total_colis=99), encoding='utf-8')
        self.assertTrue(any('Colis' in a for a in g.modele_depuis_xml(self.xml)['alertes']))

    def test_mise_en_page_valide_jusqu_a_24_articles(self):
        import xml.dom.minidom, zipfile, io
        m = g.modele_depuis_xml(self.xml)
        d = g.preparer_donnees(m, g.profil_dossier(m))
        d.update(numero='AB-123-456', manifeste='1-ML2', date_facture='01/01/2026', date_manifeste='05/01/2026')
        d['lignes'] = d['lignes'] * 12
        for style in g.STYLES:
            for genre in g.TITRES:
                docx = g._document(d, genre, style)
                xml.dom.minidom.parseString(zipfile.ZipFile(io.BytesIO(docx)).read('word/document.xml'))
        self.assertEqual(g.profil_dossier(m)['depart'], '')  # pays absent du XML de test
        self.assertEqual(m['destination'], 'Lubumbashi, DRC')

    def test_modele_word_inconnu_refuse_sans_numero(self):
        m = g.modele_depuis_xml(self.xml)
        base = self.dossier / 'f.db'
        with self.assertRaises(ValueError):
            g.generer_modele(m, 'gabarit:999999', g.profil_dossier(m), 'test', base=base,
                             base_gabarits=self.dossier / 'gabarits.db')
        self.assertFalse((self.dossier / 'numeros_factures.db').exists())


if __name__ == '__main__':
    unittest.main()
