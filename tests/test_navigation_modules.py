"""Navigation métier sans mélanger Divers et les écrans de friperie."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from asydec.ui.app import AsyDec


class NavigationModulesTest(unittest.TestCase):
    def app(self):
        pages = {cle: Mock() for cle in ('accueil', 'divers', 'dossier', 'repartitions', 'parametres')}
        pages['repartitions'].liste.get_children.return_value = ()
        pages['repartitions'].detail.get_children.return_value = ()
        return SimpleNamespace(session_verrouillee=False, base=None, liens={}, pages=pages,
                               var_module=Mock(), navigation_friperie=Mock(), module_actif=None, module_travail="friperie")

    def test_accueil_masque_les_outils_metier_sans_fermer_le_dossier(self):
        app = self.app()
        app.base = '/dossier.xml'
        app.module_actif = 'friperie'
        AsyDec.montrer(app, 'accueil')
        self.assertIsNone(app.module_actif)
        self.assertEqual(app.base, '/dossier.xml')
        app.navigation_friperie.pack_forget.assert_called_once()
        app.pages['accueil'].tkraise.assert_called_once()

    def test_divers_presente_les_outils_du_module(self):
        app = self.app()
        AsyDec.montrer(app, 'divers')
        self.assertEqual(app.module_actif, 'divers')
        app.navigation_friperie.pack.assert_called_once()
        app.pages['divers'].tkraise.assert_called_once()

    def test_retour_friperie_reaffiche_les_outils(self):
        app = self.app()
        app.module_actif = 'divers'
        AsyDec.montrer(app, 'repartitions')
        self.assertEqual(app.module_actif, 'friperie')
        app.navigation_friperie.pack.assert_called_once()
        app.pages['repartitions'].afficher.assert_called_once()

    def test_entree_friperie_respecte_la_page_preferee(self):
        app = self.app()
        app.reglages = {'page_demarrage': 'repartitions'}
        app.montrer = Mock()
        AsyDec.ouvrir_module(app, 'friperie')
        app.montrer.assert_called_once_with('repartitions')

    def test_entree_divers(self):
        app = self.app()
        app.reglages = {'page_demarrage': 'dossier'}
        app.montrer = Mock()
        AsyDec.ouvrir_module(app, 'divers')
        app.montrer.assert_called_once_with('dossier')
        self.assertEqual(app.module_travail, 'divers')

    def test_annulation_changement_module_conserve_le_travail(self):
        app = self.app()
        app.base = '/dossier.xml'
        app.fermer_dossier = Mock(return_value=False)
        app.montrer = Mock()
        AsyDec.ouvrir_module(app, 'divers')
        self.assertEqual(app.module_travail, 'friperie')
        app.montrer.assert_not_called()
