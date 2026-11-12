from decimal import Decimal
import tempfile
from pathlib import Path
import unittest

from asydec.declarations import taux_declaration as td, mise_a_jour_repartitions, declaration_licence

XML = '<ASYCUDA><Valuation><Gs_Invoice><Currency_rate>{}</Currency_rate></Gs_Invoice></Valuation></ASYCUDA>'


class TauxDeclarationTest(unittest.TestCase):
    def test_lire(self):
        self.assertEqual(td.lire('2 262,32'), Decimal('2262.32'))
        self.assertEqual(td.lire('2,262.32'), Decimal('2262.32'))
        self.assertIsNone(td.lire(''))
        for mauvais in ('abc', '-3', '0'):
            with self.assertRaises(ValueError):
                td.lire(mauvais)
        self.assertEqual(td.texte(Decimal('2262.32')), '2262.3200')

    def test_ordre_des_propositions(self):
        dossier = {'taux_change': {'valeur': '2800.0000'},
                   'recuperation_simulation': {'imports': [{'fichier': 'a.xml', 'contenu': XML.format('2500')}]}}
        self.assertEqual(td.proposer(dossier)[0], Decimal('2800'))
        dossier.pop('taux_change')
        self.assertEqual(td.proposer(dossier), (Decimal('2500'), 'XML SYDONIA importé a.xml'))
        autre = {'numero_validation': 'L2', 'taux_change': {'valeur': '2700'}}
        self.assertEqual(td.proposer({}, [autre])[0], Decimal('2700'))
        with tempfile.TemporaryDirectory() as dossier_reel:
            (Path(dossier_reel) / 'reel.xml').write_text(XML.format('2262.32'))
            self.assertEqual(td.proposer({}, [], dossier_reel), (Decimal('2262.32'), 'déclaration réelle reel.xml'))
        self.assertEqual(td.proposer({}, preference='2600')[0], Decimal('2600'))
        self.assertEqual(td.proposer({}), (None, ''))

    def test_sans_effet_sur_les_autres_etapes(self):
        licence = {'numero_validation': 'L1', 'informations_declaration': {'numero_e': '1'}}
        avant = mise_a_jour_repartitions.empreinte(licence)
        licence['taux_change'] = {'valeur': '2900.0000'}
        self.assertEqual(mise_a_jour_repartitions.empreinte(licence), avant)

    def test_declarations_a_regenerer_si_le_taux_change(self):
        licence = {'xml_genere': {'genere_le': 'x'}, 'recuperation_simulation': {'importe_le': 'y'},
                   'taux_change': {'valeur': '2900.0000'},
                   'declarations': {'fichiers': ['a'], 'taux': '2900.0000', 'xml_genere_le': 'x', 'recuperation_le': 'y',
                                    'version_police': 2}}
        self.assertTrue(declaration_licence.est_a_jour(licence))
        licence['taux_change']['valeur'] = '2950.0000'
        self.assertFalse(declaration_licence.est_a_jour(licence))


if __name__ == '__main__':
    unittest.main()


class DateDeclarationTest(unittest.TestCase):
    def test_jour_et_mois_jamais_inverses(self):
        from asydec.declarations.declaration_licence import date_dcu
        self.assertEqual(date_dcu('05/11/2026'), '05/11/2026')  # étape 3 : 5 novembre, pas 11 mai
        self.assertEqual(date_dcu('12/06/2026'), '12/06/2026')
        self.assertEqual(date_dcu('3/15/19'), '15/03/2019')     # SYDONIA m/j/aa
        self.assertEqual(date_dcu('2/5/19'), '05/02/2019')
        self.assertEqual(date_dcu('2019-05-17'), '17/05/2019')

    def test_projet_garde_les_dates_de_l_etape_3(self):
        from asydec.declarations.declaration_licence import projet_part
        licence = {'repartition': {'parts': [{'numero': 1, 'informations_declaration': {
            'date_enregistrement': '03/04/2019', 'date_liquidation': '05/04/2019', 'date_quittance': '08/04/2019'}}]}}
        projet = projet_part(licence, 1)
        self.assertEqual((projet['DATE_E'], projet['DATE_L'], projet['DATE_Q']), ('03/04/2019', '05/04/2019', '08/04/2019'))


class LicenceCourteTest(unittest.TestCase):
    def test_case_44_numero_dec_seul(self):
        from asydec.declarations.declaration_licence import licence_courte
        self.assertEqual(licence_courte('DEC1707768-7CD6545D-RC'), 'DEC1707768')
        self.assertEqual(licence_courte('DEC0679470-BE94-RC'), 'DEC0679470')
        self.assertEqual(licence_courte('AUTRE-123'), 'AUTRE-123')
