"""Compteur des pages de génération : estimation des modèles possibles et modèles déjà générés."""
import unittest

from asydec import chemins
from asydec.calcul import moteur
from asydec.calcul import variantes as V
from asydec.declarations import modeles_generes as M
from asydec.ui import compteur as C
from tests import test_modeles_generes as TM

BASE = next(iter(sorted(chemins.MODELES_XML.glob('*.xml'))), None)


class TexteCompteurTest(unittest.TestCase):
    def test_grands_nombres_et_pourcentages(self):
        self.assertEqual(C.grand_nombre(12345), '12 345')
        self.assertEqual(C.grand_nombre(1.86e18), '1,9 × 10¹⁸')
        self.assertEqual(C.pourcentage(0), '0 %')
        self.assertEqual(C.pourcentage(1e-12), '< 0,0001 %')
        self.assertEqual(C.pourcentage(0.25), '25,0 %')

    def test_texte_possibles_generes_et_probabilite(self):
        texte = C.texte({'estimation': 200, 'plafond': 1000, 'acceptes': 20, 'essais': 100}, 3, 1)
        self.assertIn('≈ 200', texte)
        self.assertIn('3 cette session · 1 enregistré(s)', texte)
        self.assertIn('2,0 %', texte)  # (3 + 1) / 200
        rare = C.texte({'estimation': 0, 'plafond': 5e7, 'acceptes': 0, 'essais': 1200}, 0, 0)
        self.assertIn('très peu (moins de 5,0 × 10⁷, aucun sur 1200 essais)', rare)


@unittest.skipIf(BASE is None, 'aucun modèle XML local')
class EstimationTest(unittest.TestCase):
    def setUp(self):
        self.info = moteur.infos_dossier(moteur.charger(str(BASE)).getroot())
        self.profil = V.construire_profil(str(BASE))

    def test_totaux_du_dossier_beaucoup_de_modeles_reproductible(self):
        i = self.info
        e = V.estimer_possibles(i['poids'], i['fob'], i['colis'], self.profil)
        self.assertGreater(e['estimation'], 1000)
        self.assertGreater(e['acceptes'], 0)
        self.assertEqual(e, V.estimer_possibles(i['poids'], i['fob'], i['colis'], self.profil))

    def test_colis_impossibles_aucun_modele(self):
        i = self.info
        e = V.estimer_possibles(i['poids'], i['fob'], 20, self.profil)  # moins de 10 colis par article
        self.assertEqual((e['estimation'], e['acceptes']), (0, 0))
        self.assertGreater(e['plafond'], 0)

    def test_totaux_non_entiers_pas_de_compteur(self):
        i = self.info
        self.assertEqual(C.calculer(object(), str(BASE), self.profil, i['poids'] + 0.5, i['fob'], i['colis'], 0), '')


class ModelesEnregistresTest(unittest.TestCase):
    def setUp(self):
        TM.ModelesGeneresTest.setUp(self)
        self.identifiant = M.enregistrer(self.resultat, self.source, 'alice', base=self.base)
        self.signature = M._signature_modele(self.identifiant, self.base)

    def test_compte_les_memes_articles_et_totaux_hors_supprimes(self):
        r = self.resultat
        totaux = (r['resume']['poids'], r['resume']['fob'], sum(r['colis']))
        self.assertEqual(M.nombre_generes(self.signature, *totaux, base=self.base), 1)
        self.assertEqual(M.nombre_generes(self.signature, totaux[0] + 1, *totaux[1:], base=self.base), 0)
        self.assertEqual(M.nombre_generes(['autres'], *totaux, base=self.base), 0)
        M.supprimer(self.identifiant, 'alice', base=self.base)
        self.assertEqual(M.nombre_generes(self.signature, *totaux, base=self.base), 0)


if __name__ == '__main__':
    unittest.main()
