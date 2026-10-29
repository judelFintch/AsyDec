"""Aperçu, annulation et enregistrement depuis la fenêtre Tkinter."""
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from asydec.declarations import modeles_generes as M
from asydec.ui.correction_modele import FenetreCorrection
from tests import test_correction_modele as fixtures


class FenetreCorrectionTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CorrectionModeleTest(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.racine = tk.Tk()
        self.racine.withdraw()
        self.addCleanup(self.racine.destroy)
        self.page = SimpleNamespace(app=SimpleNamespace(session_verrouillee=False, utilisateur='bob'),
                                    filtre=Mock(), afficher=Mock(), table=Mock())
        patch_base = patch.object(M, 'BASE', self.fixture.f.base)
        patch_base.start()
        self.addCleanup(patch_base.stop)
        self.fen = FenetreCorrection(self.page, self.fixture.identifiant, parent=self.racine)
        self.addCleanup(lambda: self.fen.destroy() if self.fen.winfo_exists() else None)

    def test_apercu_puis_creation_sans_modifier_la_validation_initiale(self):
        self.fen.donneur = self.fixture.donneur
        self.fen.actualiser()
        self.assertIsNotNone(self.fen.apercu)
        self.assertEqual(str(self.fen.enregistrer_bouton.cget('state')), 'normal')
        self.assertEqual(len(self.fen.table.get_children()), 13)
        self.fen.update_idletasks()
        self.assertGreater(self.fen.enregistrer_bouton.winfo_height(), 1)
        self.assertIn('CDF', self.fen.var_total.get())
        self.fen.motif.set('Corriger le mauvais importateur')
        with patch('asydec.ui.correction_modele.messagebox.showinfo'):
            self.fen.enregistrer()
        self.assertEqual(len(M.lister()), 2)
        self.assertEqual(M.detail(self.fixture.identifiant)['statut'], 'valide')
        self.assertEqual(M.lister()[0]['statut'], 'en_attente')
        self.page.afficher.assert_called_once()

    def test_changement_du_mode_actualise_les_taxes(self):
        self.fen.donneur = self.fixture.donneur
        self.fen.actualiser()
        avant = self.fen.apercu.resultat['resume']['taxes_totales']
        self.fen.mode.set('base')
        self.fen.actualiser()
        self.assertNotEqual(self.fen.apercu.resultat['resume']['taxes_totales'], avant)
        self.assertEqual(len(M.lister()), 1)

    def test_verrouillage_empeche_lenregistrement(self):
        self.fen.donneur = self.fixture.donneur
        self.fen.actualiser()
        self.page.app.session_verrouillee = True
        self.fen.enregistrer()
        self.assertEqual(len(M.lister()), 1)
