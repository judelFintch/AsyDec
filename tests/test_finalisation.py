import tempfile
from pathlib import Path
import unittest
from unittest import mock

from asydec.declarations import finalisation, licences_ouvertes as registre, mise_a_jour_repartitions
from asydec.declarations.documents_finaux import preparer_licence


def _complet(licence):
    licence.update(repartition={'parts': [{}, {}]}, informations_declaration={'numero_e': '1'},
                   xml_genere={'genere_le': 'x'}, recuperation_simulation={'importe_le': 'y', 'resume': {}},
                   declarations={'genere_le': 'z', 'fichiers': ['a.docx', 'b.docx']})
    return licence


class _DocumentsAJour:
    def __enter__(self):
        self.patches = [mock.patch.object(finalisation.mise_a_jour_repartitions, 'est_a_jour', return_value=True),
                        mock.patch.object(finalisation.facture_licence, 'est_a_jour', return_value=True),
                        mock.patch.object(finalisation.cvi, 'est_a_jour', return_value=True),
                        mock.patch.object(finalisation.declaration_licence, 'est_a_jour', return_value=True)]
        for p in self.patches:
            p.start()

    def __exit__(self, *_):
        for p in self.patches:
            p.stop()


class FinalisationTest(unittest.TestCase):
    def test_dossier_incomplet_bloque(self):
        licence = preparer_licence('DEC1', '100', 'L1', '17/03/2026')
        self.assertFalse(finalisation.pret(licence))
        self.assertEqual(finalisation.statut(licence), finalisation.EN_COURS)
        with self.assertRaises(ValueError):
            finalisation.fiche(licence)

    def test_declarations_manquantes_bloquent(self):
        licence = _complet(preparer_licence('DEC1', '100', 'L1', '17/03/2026'))
        licence['declarations']['fichiers'] = ['a.docx']
        with _DocumentsAJour():
            self.assertIn('Déclarations à jour (1 / 2 parts)', finalisation.bloquants(licence))

    def test_ecarts_sydonia_non_bloquants(self):
        licence = _complet(preparer_licence('DEC1', '100', 'L1', '17/03/2026'))
        licence['recuperation_simulation']['resume'] = {'controles_differents': 3}
        with _DocumentsAJour():
            self.assertTrue(finalisation.pret(licence))

    def test_regeneration_apres_finalisation(self):
        licence = _complet(preparer_licence('DEC1', '100', 'L1', '17/03/2026'))
        with _DocumentsAJour():
            licence['finalisation'] = finalisation.fiche(licence, 'ok')
        self.assertEqual(finalisation.statut(licence), finalisation.EN_ATTENTE_ARCHIVAGE)
        licence['declarations']['genere_le'] = 'plus tard'
        self.assertEqual(finalisation.statut(licence), finalisation.A_REFAIRE)

    def test_finalisation_ne_change_pas_l_empreinte_des_repartitions(self):
        licence = preparer_licence('DEC1', '100', 'L1', '17/03/2026')
        avant = mise_a_jour_repartitions.empreinte(licence)
        licence['finalisation'] = {'statut': finalisation.EN_ATTENTE_ARCHIVAGE}
        self.assertEqual(mise_a_jour_repartitions.empreinte(licence), avant)


class RegistreFinalisationTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.fichier = Path(temp.name) / 'licences.sqlite'
        licence = preparer_licence('DEC1', '100', 'L1', '17/03/2026')
        licence.update(soussigne={'nom': 'S'}, produits=[])
        registre.enregistrer(licence, self.fichier)

    def test_finaliser_puis_annuler(self):
        self.assertEqual(registre.lister(self.fichier)[0]['statut'], finalisation.EN_COURS)
        with mock.patch.object(finalisation, 'bloquants', return_value=[]):
            registre.finaliser('L1', 'prêt', self.fichier)
        self.assertEqual(registre.lister(self.fichier)[0]['statut'], finalisation.EN_ATTENTE_ARCHIVAGE)
        self.assertEqual(registre.charger('L1', self.fichier)['finalisation']['observation'], 'prêt')
        registre.annuler_finalisation('L1', self.fichier)
        self.assertEqual(registre.lister(self.fichier)[0]['statut'], finalisation.EN_COURS)

    def test_finaliser_dossier_incomplet_refuse(self):
        with self.assertRaises(ValueError):
            registre.finaliser('L1', fichier=self.fichier)
        self.assertNotIn('finalisation', registre.charger('L1', self.fichier))


if __name__ == '__main__':
    unittest.main()


class VerificationXMLTest(unittest.TestCase):
    XML = ('<ASYCUDA><Valuation><Gs_Invoice><Currency_rate>2000</Currency_rate>'
           '<Amount_national_currency>2000000.00</Amount_national_currency><Amount_foreign_currency>1000</Amount_foreign_currency>'
           '</Gs_Invoice><Total_CIF>2200000</Total_CIF></Valuation>'
           '<Financial><Amounts><Global_taxes>100000</Global_taxes><Totals_taxes>320000</Totals_taxes></Amounts></Financial>'
           '<Item><Tarification><Value_item>200,000+0+2,000+0-0</Value_item></Tarification>'
           '<Taxation><Item_taxes_amount>220000</Item_taxes_amount>'
           '<Taxation_line><Duty_tax_code>DD</Duty_tax_code><Duty_tax_Base>2200000</Duty_tax_Base><Duty_tax_amount>220000</Duty_tax_amount></Taxation_line>'
           '</Taxation></Item></ASYCUDA>')

    def test_montants_cdf_recalcules_au_taux(self):
        import xml.etree.ElementTree as ET
        from asydec.declarations import verification_xml as V
        texte = V.simuler(self.XML, 2100)
        r = ET.fromstring(texte.split('-->', 1)[1])
        self.assertEqual(r.findtext('Valuation/Gs_Invoice/Currency_rate'), '2100')
        self.assertEqual(r.findtext('Valuation/Gs_Invoice/Amount_national_currency'), '2100000.00')
        self.assertEqual(r.findtext('Valuation/Gs_Invoice/Amount_foreign_currency'), '1000')  # USD inchangé
        self.assertEqual(r.findtext('Valuation/Total_CIF'), '2310000')
        self.assertEqual(r.findtext('Item/Tarification/Value_item'), '210,000+0+2,100+0-0')
        self.assertEqual(r.findtext('Item/Taxation/Taxation_line/Duty_tax_amount'), '231000')
        self.assertEqual(r.findtext('Item/Taxation/Item_taxes_amount'), '231000')
        self.assertEqual(r.findtext('Financial/Amounts/Totals_taxes'), '336000')  # 231 000 + 105 000
        self.assertTrue(V.est_verification(texte))
        self.assertFalse(V.est_verification(self.XML))

    def test_parts_a_completer(self):
        from asydec.declarations import verification_xml as V
        refs = [dict(parts=[1]), dict(parts=[2]), dict(parts=[3, 4])]
        self.assertEqual(V.a_completer(refs, [dict(parts=[2]), dict(parts=[4])]), [dict(parts=[1])])
