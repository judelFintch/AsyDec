import unittest

import moteur
import variantes


class RepartitionColisTest(unittest.TestCase):
    def test_total_minimal_et_parts_egales_sont_repartis_deterministement(self):
        premiere = moteur.colis_gradues([1] * 8, [1] * 8, 108)
        seconde = moteur.colis_gradues([1] * 8, [1] * 8, 108)

        self.assertEqual(premiere, list(range(10, 18)))
        self.assertEqual(seconde, premiere)
        self.assertEqual(sum(premiere), 108)

    def test_repartition_usuelle_garde_totaux_et_colis_distincts(self):
        colis = moteur.colis_gradues([100, 200, 300, 400, 500, 600, 700, 800],
                                     [100] * 8, 790)

        self.assertEqual(sum(colis), 790)
        self.assertGreaterEqual(min(colis), 10)
        self.assertEqual(len(set(colis)), 8)


class RatiosHomogenesTest(unittest.TestCase):
    def test_fob_total_inferieur_a_huit_centimes_refuse(self):
        with self.assertRaisesRegex(ValueError, 'FOB strictement positif'):
            variantes.generer(9, .01, 108, [.003] * 8, nombre=1)

    def test_variantes_secondaires_homogenes_excluent_fob_arrondi_nul(self):
        propositions = variantes.generer(24, .08, 108, [.003] * 8, nombre=4)
        self.assertEqual(len(propositions), 4)
        for proposition in propositions:
            self.assertTrue(all(fob > 0 for fob in proposition['fob']))
            self.assertEqual(round(sum(proposition['fob']), 2), .08)
            self.assertEqual(sum(proposition['poids']), 24)
            self.assertEqual(sum(proposition['colis']), 108)

    def test_generation_homogene_conserve_totaux_et_precisions(self):
        propositions = variantes.generer(800, 800, 108, [1.0] * 8, nombre=1)

        self.assertEqual(len(propositions), 1)
        proposition = propositions[0]
        self.assertEqual(sum(proposition['poids']), 800)
        self.assertEqual(sum(proposition['fob']), 800)
        self.assertEqual(sum(proposition['colis']), 108)
        self.assertTrue(all(isinstance(p, int) and p > 0 for p in proposition['poids']))
        self.assertTrue(all(f > 0 and round(f * 100) == f * 100 for f in proposition['fob']))
        self.assertEqual(proposition['colis'], list(range(10, 18)))

    def test_homogene_preserve_le_nombre_de_propositions_demande(self):
        propositions = variantes.generer(800, 800, 108, [1.0] * 8, nombre=4)

        self.assertEqual(len(propositions), 4)
        self.assertEqual(len({tuple(p['poids']) for p in propositions}), 4)
        for proposition in propositions:
            self.assertEqual(sum(proposition['poids']), 800)
            self.assertEqual(sum(proposition['fob']), 800)
            self.assertEqual(sum(proposition['colis']), 108)

    def test_refuse_un_total_incompatible_avec_les_arrondis(self):
        with self.assertRaisesRegex(ValueError, 'Aucune répartition entière'):
            variantes.generer(8, .12, 108, [.015] * 8, nombre=1)


if __name__ == '__main__':
    unittest.main()
