import unittest
from asydec.declarations.import_licence import extraire_champs


class ExtractionTest(unittest.TestCase):
    def test_champs_et_formats(self):
        resultat = extraire_champs('Numéro DEC : DEC/2026/42\nMontant FOB : USD 12,345.67\n'
                                  'Numéro de validation de la licence : VAL-123\nDate de validation : 05-11-2026')
        self.assertEqual(resultat, dict(numero_dec='DEC/2026/42', montant_fob='12345.67',
                                      numero_validation='VAL-123', date_validation='05/11/2026'))

    def test_ambiguite_non_inventee(self):
        resultat = extraire_champs('DEC : ABC\nDEC : DEF\nFOB : 1,234\nDate facture : 05/11/2026')
        self.assertEqual(resultat, {})

    def test_fob_francais_et_libelle_suivi_sur_autre_ligne(self):
        self.assertEqual(extraire_champs('FOB : 12.345,67\nNuméro de validation\nVAL/42'),
                         {'montant_fob': '12345.67', 'numero_validation': 'VAL/42'})

    def test_ocr_sans_espaces(self):
        self.assertEqual(extraire_champs('MontantFOB:USD12345.67'), {'montant_fob': '12345.67'})
