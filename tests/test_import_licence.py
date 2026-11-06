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
        # La date de facture n'est jamais prise pour la date de validation.
        self.assertEqual(resultat, {'date_facture': '05/11/2026'})

    def test_fob_francais_et_libelle_suivi_sur_autre_ligne(self):
        self.assertEqual(extraire_champs('FOB : 12.345,67\nNuméro de validation\nVAL/42'),
                         {'montant_fob': '12345.67', 'numero_validation': 'VAL/42'})

    def test_ocr_sans_espaces(self):
        self.assertEqual(extraire_champs('MontantFOB:USD12345.67'), {'montant_fob': '12345.67'})

    def test_modele_ib_fob_cif_et_dates_distinctes(self):
        texte = '''N° Validation       DEC1234567-ADD0-IB
5) Montant FOB total à payer / CIF total à payer     168430.00 / 170000.00
Date Facture   16 Mars 2026
Date extrême de validité 12 Mars 2027 00h00
10.4 Régime Douanier     Date de validation 17 Mars 2026 00h00
V 2.1 Edité le : 12 Oct. 2026 10H38:09'''
        self.assertEqual(extraire_champs(texte), dict(numero_dec='DEC1234567',
                         numero_validation='DEC1234567-ADD0-IB', montant_fob='168430.00',
                         date_validation='17/03/2026', date_facture='16/03/2026'))

    def test_mois_francais_et_dec_explicitement_saisi(self):
        resultat = extraire_champs('DEC : AUTRE/42\nN° Validation DEC1234567-ADD0-IB\n'
                                  'Date de validation 29 Février 2024\nFOB total à payer 10 200,50')
        self.assertEqual(resultat['numero_dec'], 'AUTRE/42')
        self.assertEqual(resultat['date_validation'], '29/02/2024')
        self.assertEqual(resultat['montant_fob'], '10200,50')

    def test_validation_ambigu_evite_dec_derive(self):
        self.assertEqual(extraire_champs('N° Validation DEC1234567-ADD0-IB\n'
                                        'N° Validation DEC7654321-ADD0-IB'), {})
