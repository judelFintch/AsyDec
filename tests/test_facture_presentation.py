from decimal import Decimal
from unittest import TestCase
from asydec.declarations.nombres_lettres import dollars_us
from asydec.declarations.facture_simple import _adresse, _quantite, _montant
from asydec.declarations.facture_licence import avertissements_quantites
from tests.test_facture_licence import licence


class PresentationFactureTest(TestCase):
    def test_dollars_avant_centimes(self):
        self.assertEqual(dollars_us('100000.56'), 'ONE HUNDRED THOUSAND US DOLLARS AND FIFTY SIX CENTS')
        self.assertEqual(dollars_us('1.01'), 'ONE US DOLLAR AND ONE CENT')
        self.assertEqual(dollars_us('1000000'), 'ONE MILLION US DOLLARS')

    def test_format_anglais_et_pays(self):
        self.assertEqual(_quantite(Decimal('1425.212')), '1,425.212')
        self.assertEqual(_montant(Decimal('100000.56')), '100,000.56')
        self.assertEqual(_adresse('Lubumbashi, Congo, The Democratic Republic of the'),
                         'Lubumbashi, Democratic Republic of the Congo')

    def test_fractions_signalees_sans_modifier_les_quantites(self):
        l = licence(parts=1)
        article = l['repartition']['parts'][0]['articles'][0]
        article['quantite'] = '142.522'
        self.assertEqual(len(avertissements_quantites(l)), 1)
        self.assertEqual(article['quantite'], '142.522')
        article['unite'] = 'kg'
        self.assertEqual(avertissements_quantites(l), [])
