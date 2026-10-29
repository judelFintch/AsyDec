"""Le ratio de l'aperçu suit les montants de chaque proposition affichée."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import asydec.ui.etapes as E


class AffichageRatiosTest(unittest.TestCase):
    def setUp(self):
        self.tableau = Mock()
        self.tableau.get_children.return_value = ('ancien',)
        self.page = SimpleNamespace(tableau=self.tableau, cartes={k:Mock() for k in ('poids','fob','colis','taxes')},
            var_fichier=Mock(), var_taux=Mock(), comparer_bouton=Mock(), deja_vues={}, regenerer_bouton=Mock(), generer=Mock(), message=Mock(),
            _contexte_regeneration=Mock(return_value='contexte'), _repartition=E.PageVerifier._repartition)
        self.page._montrer = lambda res: E.PageVerifier._montrer(self.page,res)

    def resultat(self, poids=100, fob=37.45):
        return {'resume': {'poids':poids, 'fob':fob, 'taxes_totales':30, 'taxes_globales':10,
            'cif':50, 'taxes_articles':20,
            'articles':[{'poids':poids,'fob':fob,'cif':50,'taxes':20}]},
            'info':{'designations':['Article']}, 'chemin':E.generer.DEC+'/test.xml',
            'nom':'test.xml','colis':[10], 'fob':[fob], 'alertes':[]}

    def lignes(self):
        return [c.kwargs['values'] for c in self.tableau.insert.call_args_list]

    def test_ratio_par_article_quatre_decimales_et_totaux_alignes(self):
        E.PageVerifier._presenter(self.page,self.resultat())
        article,total,taxes = self.lignes()
        self.assertEqual(article[4], '0,3745')
        self.assertEqual(article[5:], (10,'50','20'))
        self.assertEqual(total[4], '')
        self.assertEqual(taxes[4], '')
        self.assertTrue(all(len(ligne)==8 for ligne in self.lignes()))

    def test_nouvelle_proposition_remplace_ancien_ratio(self):
        E.PageVerifier._presenter(self.page,self.resultat())
        self.tableau.reset_mock()
        E.PageVerifier._presenter(self.page,self.resultat(poids=125,fob=50))
        self.tableau.delete.assert_called_once_with('ancien')
        self.assertEqual(self.lignes()[0][4], '0,4000')

    def test_nouvel_apercu_retire_export_et_desactive_comparaison(self):
        self.page.fichier='ancien-export.xml'
        E.PageVerifier._presenter(self.page,self.resultat())
        self.assertIsNone(self.page.fichier)
        self.page.comparer_bouton.configure.assert_called_with(state='disabled')

    def test_poids_nul_affiche_tiret_sans_division_par_zero(self):
        E.PageVerifier._presenter(self.page,self.resultat(poids=0))
        self.assertEqual(self.lignes()[0][4], '—')


if __name__=='__main__':
    unittest.main()
