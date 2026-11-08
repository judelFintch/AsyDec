import unittest
from datetime import date, timedelta
from decimal import Decimal

from asydec.declarations.documents_finaux import preparer_licence
from asydec.declarations.dates_documents import est_ouvrable


class LicenceTest(unittest.TestCase):
    def test_fenetre_sur_toute_une_annee(self):
        for jour in range(366):
            depart = date(2028, 1, 1) + timedelta(days=jour)
            if not est_ouvrable(depart):
                continue
            candidats = [depart + timedelta(days=d) for d in (3,4,5)]
            if not any(est_ouvrable(c) for c in candidats):
                with self.assertRaisesRegex(ValueError, 'Aucune date BL'):
                    preparer_licence('DEC', '100', 'VAL', depart.strftime('%d/%m/%Y'))
                continue
            resultat = preparer_licence(' DEC-1 ', '12 345,67', ' VAL-9 ', depart.strftime('%d/%m/%Y'))
            self.assertIn(resultat['delai'], (3, 4, 5))
            self.assertTrue(est_ouvrable(resultat['date_bl']))
            for delai in range(3, resultat['delai']):
                self.assertFalse(est_ouvrable(depart + timedelta(days=delai)))
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

    def test_date_licence_weekend_refusee_sans_modification(self):
        for jour in ('07/11/2026', '08/11/2026'):
            with self.assertRaisesRegex(ValueError, 'jour ouvrable'):
                preparer_licence('DEC', '100', 'VAL', jour)


class FactureTest(unittest.TestCase):
    def test_date_proposee_au_moins_un_mois_avant_la_licence(self):
        import random
        from asydec.declarations.documents_finaux import proposer_date_facture, ECART_FACTURE_MIN, ECART_FACTURE_MAX
        validation = date(2026, 3, 17)
        for graine in range(40):
            texte = proposer_date_facture('17/03/2026', random.Random(graine))
            jour = date(int(texte[6:]), int(texte[3:5]), int(texte[:2]))
            self.assertTrue(est_ouvrable(jour))
            self.assertTrue(ECART_FACTURE_MIN <= (validation - jour).days <= ECART_FACTURE_MAX)
        self.assertEqual(len(proposer_date_facture('2026-03-17')), 10)  # date enregistrée (ISO) acceptée

    def test_facture_de_la_licence_importee_fait_foi(self):
        # Licence DEC1710304 réelle : facture 02343-26 du 16/03/2026, licence du 17/03/2026.
        licence = preparer_licence('DEC1', '1000', 'DEC1-A-IB', '17/03/2026', '02343-26', '16/03/2026')
        self.assertEqual((licence['numero_facture'], licence['date_facture']), ('02343-26', '16/03/2026'))
        with self.assertRaises(ValueError):  # facture après la licence : impossible
            preparer_licence('DEC1', '1000', 'DEC1-A-IB', '17/03/2026', 'INV1', '20/03/2026')


class NumeroFactureTest(unittest.TestCase):
    def test_numero_suivant_jamais_reutilise(self):
        import tempfile
        from pathlib import Path
        from asydec.declarations import licences_ouvertes as L
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / 'licences.sqlite'
            self.assertEqual(L.proposer_numero_facture(fichier), 'INV1001')
            import json
            with L.connexion(fichier) as conn:
                for numero, facture in (('A', 'INV1023'), ('B', 'ORD0000013709'), ('C', 'INV 0998')):
                    conn.execute('INSERT INTO licences VALUES (?, ?, ?)', (numero, json.dumps({'numero_facture': facture}), ''))
                conn.execute('INSERT INTO licences_supprimees (numero, contenu, modifie_le, supprime_le) VALUES (?, ?, ?, ?)',
                             ('D', json.dumps({'numero_facture': 'INV1030'}), '', ''))
            self.assertEqual(L.proposer_numero_facture(fichier), 'INV1031')  # supprimées comprises
