"""Intentions de génération : notes de chaque intention et choix de la proposition, sur des données inventées."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from asydec.calcul import variantes as V


def reference(poids, fob, colis):
    return {'nom': 'ref', 'info': {'poids_articles': poids, 'fob_articles': fob, 'colis_articles': colis}}


# Article 1 : ratios observés 1 à 3 (milieu 2) ; article 2 : 0,5 à 1,5 (milieu 1).
PROFIL = {'ratios': [2, 1], 'references': [reference([100, 100], [100, 50], [10, 30]),
                                           reference([300, 100], [900, 150], [30, 10])]}


def proposition(poids, fob, colis=(20, 20), distance=0.1):
    return {'poids': list(poids), 'fob': list(fob), 'colis': list(colis), 'distance': distance}


class ScoreIntentionTest(unittest.TestCase):
    def test_ratio_sur_zero_au_milieu_un_sur_les_bords(self):
        self.assertEqual(V.score_intention(proposition((100, 100), (200, 100)), PROFIL, 'ratio_sur'), 0)
        self.assertEqual(V.score_intention(proposition((100, 100), (300, 50)), PROFIL, 'ratio_sur'), 1)
        centre = V.score_intention(proposition((100, 100), (210, 100)), PROFIL, 'ratio_sur')
        bord = V.score_intention(proposition((100, 100), (290, 100)), PROFIL, 'ratio_sur')
        self.assertLess(centre, bord)

    def test_moyen_zero_sur_les_parts_moyennes(self):
        # Parts moyennes : poids (5/8, 3/8), FOB (2/3+6/7 ... ) calculées comme le module.
        moyenne = V._parts_moyennes(PROFIL)
        self.assertAlmostEqual(sum(moyenne['poids']), 1)
        exacte = {cle: [x * 1000 for x in parts] for cle, parts in moyenne.items()}
        self.assertAlmostEqual(V.score_intention(exacte, PROFIL, 'moyen'), 0)
        ecartee = proposition((900, 100), (900, 100), (35, 5))
        self.assertGreater(V.score_intention(ecartee, PROFIL, 'moyen'), 0.2)

    def test_taxes_basses_exige_le_total(self):
        self.assertEqual(V.score_intention(proposition((1, 1), (1, 1)), PROFIL, 'taxes_basses', 1234), 1234)
        with self.assertRaises(ValueError):
            V.score_intention(proposition((1, 1), (1, 1)), PROFIL, 'taxes_basses')

    def test_proche_reprend_la_distance_et_intention_inconnue_refusee(self):
        self.assertEqual(V.score_intention(proposition((1, 1), (1, 1), distance=0.3), PROFIL, 'proche'), 0.3)
        with self.assertRaises(ValueError):
            V.score_intention(proposition((1, 1), (1, 1)), PROFIL, 'autre')


class ChoixSelonIntentionTest(unittest.TestCase):
    def test_intention_par_defaut_le_plus_proche(self):
        from asydec.ui.intentions import intention_choisie
        self.assertEqual(intention_choisie(SimpleNamespace()), 'proche')
        self.assertEqual(intention_choisie(SimpleNamespace(var_intention=SimpleNamespace(
            get=lambda: V.INTENTIONS['taxes_basses']))), 'taxes_basses')

    def test_risque_d_abord_puis_intention(self):
        import asydec.ui.modeles_generes as U
        eleve = [{'niveau': 'eleve', 'message': 'x', 'article': None}]
        risques = {'a': eleve, 'b': [], 'c': [], 'd': eleve}
        notes = {'a': 0, 'b': 5, 'c': 2, 'd': 1}
        propositions = [{'nom': n} for n in 'abcd']
        with patch.object(U, '_contexte_anomalies', return_value=({}, [])), \
                patch.object(U.Path, 'read_bytes', return_value=b''), \
                patch.object(U.service, 'donnees_proposition', side_effect=lambda _x, v, _a: v['nom']), \
                patch.object(U.anomalies, 'analyser', side_effect=lambda nom, *_: risques[nom]):
            classees = U.classer_propositions(SimpleNamespace(), propositions, base='base.xml',
                                              profil={'ajustables': ()}, cle=lambda v: notes[v['nom']])
        self.assertEqual([v['nom'] for v, _ in classees], ['c', 'b', 'a', 'd'])

    def test_sans_references_l_intention_classe_seule(self):
        import asydec.ui.modeles_generes as U
        propositions = [{'n': 3}, {'n': 1}, {'n': 2}]
        classees = U.classer_propositions(SimpleNamespace(), propositions, cle=lambda v: v['n'])
        self.assertEqual([v['n'] for v, _ in classees], [1, 2, 3])


if __name__ == '__main__':
    unittest.main()
