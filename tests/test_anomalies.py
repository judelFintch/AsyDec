"""Analyse des anomalies : chaque contrôle sur des données inventées, sans base réelle."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from asydec.calcul import anomalies as A

G1, G2 = ('USD', '6309', 'friperie'), ('USD', '6304', 'couvre-lits')


def observations(ratios1, poids=(100, 100)):
    sortie = []
    for doc, r in enumerate(ratios1):
        sortie += [{'document_id': doc, 'groupe': G1, 'poids': poids[0], 'ratio': r},
                   {'document_id': doc, 'groupe': G2, 'poids': poids[1], 'ratio': 0.2}]
    return sortie


def modele(identifiant=1, ratio1=1.5, poids=(100, 100), statut='valide', ecart=None, position1=1):
    return {'id': identifiant, 'statut': statut, 'ecart_comparaison_pct': ecart, 'articles': [
        {'position': position1, 'code': '6309', 'groupe': G1, 'poids': poids[0], 'fob': poids[0] * ratio1, 'colis': 10},
        {'position': 2, 'code': '6304', 'groupe': G2, 'poids': poids[1], 'fob': poids[1] * 0.2, 'colis': 12}]}


class AnomaliesTest(unittest.TestCase):
    def setUp(self):
        self.groupes = A.references_par_groupe(observations([1.4, 1.45, 1.5, 1.5, 1.55, 1.6]))

    def niveaux(self, alertes):
        return [a['niveau'] for a in alertes]

    def test_dans_les_dossiers_connus_aucun_signal(self):
        alertes = A.analyser(modele(), self.groupes)
        self.assertEqual(alertes, [])
        self.assertIsNone(A.niveau(alertes))

    def test_ratio_jamais_observe_eleve_et_ajustable_explique(self):
        alertes = A.analyser(modele(ratio1=2.0), self.groupes)
        self.assertEqual(A.niveau(alertes), 'eleve')
        self.assertIn('jamais observé', alertes[0]['message'])
        self.assertNotIn('ajustable', alertes[0]['message'])
        alertes = A.analyser(modele(ratio1=2.0, position1=4), self.groupes)
        self.assertIn('ajustable', alertes[0]['message'])

    def test_ratio_en_marge_moyen_seulement_avec_assez_de_references(self):
        self.assertEqual(A.niveau(A.analyser(modele(ratio1=1.41), self.groupes)), 'moyen')
        peu = A.references_par_groupe(observations([1.4, 1.5, 1.6]))
        self.assertIsNone(A.niveau(A.analyser(modele(ratio1=1.41), peu)))

    def test_part_du_poids_jamais_vue(self):
        alertes = A.analyser(modele(poids=(300, 100)), self.groupes)
        self.assertTrue(any('Part du poids' in a['message'] for a in alertes))

    def test_sans_reference_information(self):
        alertes = A.analyser(modele(), {})
        self.assertEqual(set(self.niveaux(alertes)), {'info'})
        self.assertIsNone(A.niveau(alertes))

    def test_proche_d_un_rejete_et_recopie(self):
        rejete = dict(modele(identifiant=2, statut='rejete'), motif='ratios trop bas')
        alertes = A.analyser(modele(), self.groupes, [rejete])
        self.assertEqual(A.niveau(alertes), 'eleve')
        self.assertIn('n° 2 rejeté localement (motif : ratios trop bas)', alertes[0]['message'])
        copie = modele(identifiant=3)
        self.assertIn('identiques au modèle n° 3', A.analyser(modele(), self.groupes, [copie])[0]['message'])
        autre_article = dict(copie, articles=[dict(a, groupe=('EUR',) + a['groupe'][1:]) for a in copie['articles']])
        self.assertEqual(A.analyser(modele(), self.groupes, [autre_article]), [])

    def test_ecart_de_comparaison(self):
        self.assertEqual(A.niveau(A.analyser(modele(ecart=-0.21), self.groupes)), None)
        self.assertEqual(A.niveau(A.analyser(modele(ecart=2), self.groupes)), 'moyen')
        self.assertEqual(A.niveau(A.analyser(modele(ecart=-6), self.groupes)), 'eleve')

    def test_tri_grave_d_abord(self):
        alertes = A.analyser(modele(ratio1=2.0, ecart=2, statut='rejete'), self.groupes)
        self.assertEqual(self.niveaux(alertes), sorted(self.niveaux(alertes), key=A.NIVEAUX.index))


class InterfaceAnomaliesTest(unittest.TestCase):
    def test_references_illisibles_liste_utilisable(self):
        import asydec.ui.modeles_generes as U
        self.assertEqual(U.analyser_modeles(SimpleNamespace()), {})
        self.assertIn('aucun signal', U.resume_risque([]))
        self.assertIn('Risque élevé', U.resume_risque([{'niveau': 'eleve', 'message': 'x', 'article': None}]))


if __name__ == '__main__':
    unittest.main()
