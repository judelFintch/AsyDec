import unittest
from datetime import date, timedelta
from decimal import Decimal

from asydec.declarations.documents_finaux import preparer_licence


class LicenceTest(unittest.TestCase):
    def test_fenetre_sur_toute_une_annee(self):
        for jour in range(366):
            depart = date(2028, 1, 1) + timedelta(days=jour)
            resultat = preparer_licence(' DEC-1 ', '12 345,67', ' VAL-9 ', depart.strftime('%d/%m/%Y'))
            self.assertIn(resultat['delai'], (3, 4, 5))
            self.assertLess(resultat['date_bl'].weekday(), 5)
            for delai in range(3, resultat['delai']):
                self.assertGreaterEqual((depart + timedelta(days=delai)).weekday(), 5)
            self.assertEqual(resultat['montant_fob'], Decimal('12345.67'))

    def test_samedi_reporte_au_lundi_annee_suivante(self):
        resultat = preparer_licence('DEC', '100', 'VAL', '28/12/2022')
        self.assertEqual(resultat['date_bl'], date(2023, 1, 2))

    def test_refuse_donnees_invalides(self):
        for modifications in ({'numero_dec': ''}, {'numero_validation': ''},
                              {'montant_fob': 'NaN'}, {'montant_fob': 'Infinity'},
                              {'montant_fob': '-1'}, {'montant_fob': '0'},
                              {'montant_fob': 'abc'}, {'date_validation': '31/02/2026'}):
            valeurs = dict(numero_dec='DEC', montant_fob='100', numero_validation='VAL', date_validation='05/11/2026')
            valeurs.update(modifications)
            with self.subTest(modifications=modifications), self.assertRaises(ValueError):
                preparer_licence(**valeurs)
