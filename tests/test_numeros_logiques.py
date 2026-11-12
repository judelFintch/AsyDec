from datetime import date
import random
import unittest

from asydec.declarations import numeros_logiques as N


def point(type_, numero, jour, bureau=''):
    return dict(type=type_, numero=numero, date=jour, bureau=bureau, source='test')


class NumerosLogiquesTest(unittest.TestCase):
    def test_entre_deux_dossiers_et_place_des_parts(self):
        points = [point('E', 1000, date(2026, 3, 1)), point('E', 2000, date(2026, 3, 11))]
        valeur, explication = N.proposer_numero(points, 'E', date(2026, 3, 6), 1, tirage=random.Random(0))
        self.assertTrue(1400 <= valeur <= 1600, valeur)
        self.assertIn('entre 1000', explication)
        # 30 parts juste avant le dossier suivant : on laisse la place des incréments.
        valeur, _ = N.proposer_numero(points, 'E', date(2026, 3, 10), 30, tirage=random.Random(0))
        self.assertLessEqual(valeur + round(N.INCREMENT_MOYEN * 29), 2000)

    def test_apres_le_dernier_dossier_au_rythme_observe(self):
        points = [point('E', 100, date(2026, 1, 10)), point('E', 1100, date(2026, 1, 30))]
        valeur, explication = N.proposer_numero(points, 'E', date(2026, 2, 9), tirage=random.Random(0))
        self.assertTrue(1500 <= valeur <= 1610, valeur)  # environ 50 par jour
        self.assertIn('après 1100', explication)

    def test_debut_d_annee_et_annee_sans_donnee(self):
        points = [point('E', 900, date(2026, 1, 10))]
        valeur, explication = N.proposer_numero(points, 'E', date(2026, 1, 5), tirage=random.Random(0))
        self.assertTrue(0 < valeur < 900)
        self.assertIn('1er janvier', explication)
        valeur, explication = N.proposer_numero(points, 'E', date(2025, 7, 1), tirage=random.Random(0))
        self.assertIn('aucun numéro connu en 2025', explication)
        self.assertGreater(valeur, 1000)

    def test_numero_aberrant_ecarte(self):
        points = [point('E', 100, date(2026, 1, 10)), point('E', 9000, date(2026, 4, 1)),
                  point('E', 50, date(2026, 5, 1)), point('E', 12000, date(2026, 10, 1))]
        valeur, _ = N.proposer_numero(points, 'E', date(2026, 6, 1), tirage=random.Random(0))
        self.assertTrue(9000 < valeur < 12000, valeur)

    def test_meme_bureau_prefere_et_numeros_lus(self):
        points = [point('E', 100, date(2026, 1, 10), '725B'), point('E', 5000, date(2026, 1, 10), '999Z')]
        valeur, _ = N.proposer_numero(points, 'E', date(2026, 1, 12), bureau='725B', tirage=random.Random(0))
        self.assertLess(valeur, 1000)
        self.assertEqual(N.numero('2026 7628'), 7628)
        self.assertEqual(N.numero('E 4567'), 4567)
        self.assertEqual(N.lire_date('10/20/26'), date(2026, 10, 20))
        self.assertEqual(N.lire_date('05/11/2026'), date(2026, 11, 5))

    def test_proposer_tous_les_champs(self):
        licence = {'repartition': {'parts': [{'informations_declaration': {
            'numero_e': '219', 'date_enregistrement': '09/01/2026', 'numero_liquidation': '233',
            'date_liquidation': '12/01/2026', 'numero_quittance': '105', 'date_quittance': '12/01/2026',
            'manifeste': '122'}}]}}
        points = N.collecter([('A', licence)])
        resultat = N.proposer(points, {'date_enregistrement': '20/01/2026', 'date_liquidation': '22/01/2026',
                                       'date_quittance': '22/01/2026'}, 3, tirage=random.Random(0))
        self.assertEqual(set(resultat), {'numero_e', 'numero_liquidation', 'numero_quittance', 'manifeste'})
        self.assertGreater(int(resultat['numero_e'][0]), 219)
        self.assertGreater(int(resultat['numero_quittance'][0]), 105)


if __name__ == '__main__':
    unittest.main()


class ListeCollectee(unittest.TestCase):
    TEXTE = ('#\tPLAQUES\tPAIEMENT\tE\tPAIEMENT ORANGE\tDECLARTION\n'
             '1\tT396CVG/T143CFW\tOUI\tE1532\t02.03.2026\t02.03.2026\n'
             '2\tT156EFR/T374DNJ\tOUI\tE1293\t09.03.2026\t11.03.2023\n'   # année fautive : ignorée
             '3\tT642DNU/T883DNG\tOUI\tE7222\t22.07.2026\t\n'              # sans déclaration : ignorée
             '4\tT221DPP/T886DVY\tOUI\te2357\t24.03.2026\t30.03.2026\n'
             '5\tT240EAK/T165EAL\tOUI\t\t07.03.2026\t\n')

    def test_lecture_date_de_declaration(self):
        points, ignorees = N.lire_liste(self.TEXTE)
        self.assertEqual([(p['numero'], p['date']) for p in points],
                         [(1532, date(2026, 3, 2)), (2357, date(2026, 3, 30))])
        self.assertEqual(ignorees, 2)
        self.assertEqual(points[0]['source'], 'liste T396CVG/T143CFW')

    def test_enregistrement_sans_doublon(self):
        import tempfile
        from pathlib import Path
        from asydec.declarations import licences_ouvertes as R
        points, _ = N.lire_liste(self.TEXTE)
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / 'base.sqlite'
            self.assertEqual(R.ajouter_numeros_connus(points, base), 2)
            self.assertEqual(R.ajouter_numeros_connus(points, base), 0)
            self.assertEqual(len(R.lister_numeros_connus(base)), 2)


class ControleSaisieTest(unittest.TestCase):
    def setUp(self):
        self.points = [point('E', 1000 + 36 * i, date(2026, 3, 1 + i)) for i in range(20)]

    def test_numero_coherent_sans_alerte(self):
        self.assertIsNone(N.controler(self.points, 'E', 'E 1180', date(2026, 3, 6)))

    def test_numero_plus_petit_qu_un_dossier_anterieur(self):
        message = N.controler(self.points, 'E', '900', date(2026, 3, 10))
        self.assertIn('plus petit que', message)

    def test_numero_loin_de_la_progression(self):
        points = [point('E', 1000, date(2026, 3, 1)), point('E', 9000, date(2026, 9, 1))]
        message = N.controler(points, 'E', '8500', date(2026, 3, 5))
        self.assertIn('loin de la progression', message)

    def test_saisie_tracee_et_remplacee(self):
        import tempfile
        from pathlib import Path
        from asydec.declarations import licences_ouvertes as R
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / 'b.sqlite'
            with R.connexion(base) as conn:
                licence = {'repartition': {'parts': [{'numero': 1, 'informations_declaration': {
                    'numero_e': '500', 'date_enregistrement': '10/03/2026'}}]}}
                R._tracer_saisie(conn, 'L1', licence)
                licence['repartition']['parts'][0]['informations_declaration']['numero_e'] = '510'
                R._tracer_saisie(conn, 'L1', licence)
            points = R.lister_numeros_connus(base)
            self.assertEqual([(p['type'], p['numero'], p['source']) for p in points], [('E', 510, 'saisie L1')])


class SousETest(unittest.TestCase):
    def test_proposition_l_q_m_toujours_sous_e(self):
        # Données où L, Q et M connus sont plus grands que E : la proposition doit quand même rester sous E.
        points = [point('E', 1000, date(2026, 3, 1)), point('L', 1500, date(2026, 3, 1)),
                  point('Q', 1200, date(2026, 3, 1)), point('M', 1300, date(2026, 3, 1))]
        for graine in range(20):
            r = N.proposer(points, {'date_enregistrement': '05/03/2026', 'date_liquidation': '05/03/2026',
                                    'date_quittance': '05/03/2026'}, 3, tirage=random.Random(graine))
            e = int(r['numero_e'][0])
            for cle in ('numero_liquidation', 'numero_quittance', 'manifeste'):
                self.assertLess(int(r[cle][0]), e, (cle, r))

    def test_rapport_habituel_au_e(self):
        p = [dict(point('E', 1000, date(2026, 3, 1)), source='a'), dict(point('L', 900, date(2026, 3, 1)), source='a')]
        self.assertAlmostEqual(N.rapport_au_e(p, 'L'), 0.9)
        self.assertEqual(N.sous_e(p, 'L', 2000, random.Random(0)), 1800)

    def test_controle_saisie(self):
        messages = N.controler_sous_e('E 500', {'numero_liquidation': '510', 'numero_quittance': '300', 'manifeste': '500'})
        self.assertEqual(len(messages), 2)

    def test_parts_suivantes_sous_leur_e(self):
        from asydec.declarations import numeros_repartitions
        licence = {'informations_declaration': {'numero_e': '100', 'numero_liquidation': '99', 'numero_quittance': '50',
                                                'manifeste': '98', 'date_quittance': '05/03/2026'},
                   'repartition': {'parts': [{'numero': i} for i in range(1, 11)]}}
        for graine in range(30):
            numeros_repartitions.completer(licence, random.Random(graine))
            for part in licence['repartition']['parts']:
                infos = part['informations_declaration']
                self.assertLess(int(infos['numero_liquidation']), int(infos['numero_e']))
                self.assertLess(int(infos['manifeste']), int(infos['numero_e']))
            for cle in ('numero_liquidation', 'manifeste'):
                valeurs = [int(p['informations_declaration'][cle]) for p in licence['repartition']['parts']]
                self.assertEqual(valeurs, sorted(valeurs))
            for part in licence['repartition']['parts']:
                part.pop('informations_declaration')


class HorsRegleTest(unittest.TestCase):
    def test_parts_signalees(self):
        licence = {'repartition': {'parts': [
            {'numero': 1, 'informations_declaration': {'numero_e': '219', 'numero_liquidation': '233',
                                                        'numero_quittance': '105', 'manifeste': '122'}},
            {'numero': 2, 'informations_declaration': {'numero_e': '230', 'numero_liquidation': '220',
                                                        'numero_quittance': '105', 'manifeste': '125'}}]}}
        self.assertEqual([n for n, _ in N.parts_hors_regle(licence)], [1])
        self.assertIn('Liquidation ≥ E sur 1 part(s) (1)', N.resume_hors_regle(licence))
        licence['repartition']['parts'][0]['informations_declaration']['numero_liquidation'] = '210'
        self.assertEqual(N.resume_hors_regle(licence), '')
