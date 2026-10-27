"""Le bouton de simulation ne change plus de parcours ni les données saisies."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import interface


class SimulationTest(unittest.TestCase):
    def formulaire(self,poids):
        return SimpleNamespace(e_poids=[SimpleNamespace(get=lambda v=v:v) for v in poids],_calculer=Mock())

    def test_tableau_vide_explique_les_methodes(self):
        app=self.formulaire(['']*8)
        with patch.object(interface.messagebox,'showinfo') as info:
            interface.Application.simuler(app)
        info.assert_called_once()
        app._calculer.assert_not_called()

    def test_tableau_complet_et_partiel_suivent_le_meme_controle(self):
        for poids in (['100']*8,['100','','200','','','','','']):
            app=self.formulaire(poids)
            interface.Application.simuler(app)
            app._calculer.assert_called_once_with(enregistrer=False)
            self.assertEqual([e.get() for e in app.e_poids],poids)


class OptionDeuxTest(unittest.TestCase):
    def test_option_deux_ne_demande_pas_de_fichier(self):
        app=SimpleNamespace(var_methode=Mock(),simuler_depuis_bibliotheque=Mock(),parcourir=Mock(),charger_base=Mock())
        interface.Application.methode_totaux(app,False)
        app.simuler_depuis_bibliotheque.assert_called_once()
        app.parcourir.assert_not_called()
        app.charger_base.assert_not_called()
