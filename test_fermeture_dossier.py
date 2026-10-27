from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest
from ui.app import AsyDec


class FermetureDossierTest(unittest.TestCase):
    def app(self):
        articles=SimpleNamespace(_attente='attente',after_cancel=Mock(),var_fob_total=Mock(),
            var_colis_total=Mock(),remplir=Mock(),message=Mock(),ratios=[Mock()],etats=[Mock()],totaux=[Mock()])
        verifier=SimpleNamespace(resultat={'test':1},fichier='export.xml',finder=Mock(),tableau=Mock(),
            generer=Mock(),regenerer_bouton=Mock(),var_fichier=Mock(),cartes={'poids':Mock()})
        verifier.tableau.get_children.return_value=[]
        return SimpleNamespace(session_verrouillee=False,base='base.xml',info={'test':1},reference='ref.xml',
            profil={'test':1},pages={'articles':articles,'verifier':verifier},var_bandeau=Mock(),montrer=Mock())

    def test_fermer_vide_le_dossier_et_bloque_export(self):
        app=self.app()
        with patch('ui.app.messagebox.askyesno',return_value=True):
            self.assertTrue(AsyDec.fermer_dossier(app))
        self.assertIsNone(app.base)
        self.assertIsNone(app.profil)
        self.assertIsNone(app.pages['verifier'].resultat)
        app.pages['verifier'].generer.configure.assert_called_once_with(state='disabled')
        app.pages['articles'].remplir.assert_called_once_with(None,mode='RATIOS')
        app.pages['articles'].after_cancel.assert_called_once_with('attente')
        app.montrer.assert_called_once_with('dossier')

    def test_annuler_ne_change_aucune_donnee(self):
        app=self.app()
        with patch('ui.app.messagebox.askyesno',return_value=False):
            self.assertFalse(AsyDec.fermer_dossier(app))
        self.assertEqual(app.base,'base.xml')
        self.assertEqual(app.pages['verifier'].fichier,'export.xml')
        app.pages['articles'].remplir.assert_not_called()

    def test_session_verrouillee_ne_peut_pas_fermer(self):
        app=self.app()
        app.session_verrouillee=True
        self.assertFalse(AsyDec.fermer_dossier(app))
        self.assertEqual(app.base,'base.xml')
