"""Choix automatique et validation manuelle du nombre dans la fenêtre de composition."""
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import Mock

from asydec.calcul import moteur
from asydec.ui.articles_dynamiques import PanneauArticles
from asydec.ui.composition import FenetreComposition
from tests import test_composition as fixtures


class FenetreCompositionTest(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.CompositionTest(methodName='runTest')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root=tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app=SimpleNamespace(session_verrouillee=False,module_travail='friperie',base=str(self.f.base),base_dossier=str(self.f.base),
            profil={},info=moteur.infos_dossier(moteur.charger(self.f.base).getroot()),appliquer_composition=Mock(),
            chemins_xml_disponibles=lambda generation=False:[self.f.base,self.f.autre])
        panneau=PanneauArticles(self.root,self.app,Mock())
        self.fen=FenetreComposition(panneau)
        self.addCleanup(lambda:self.fen.destroy() if self.fen.winfo_exists() else None)

    def test_nombre_et_selection_auto_avant_application(self):
        self.fen.nombre.set('3')
        self.fen.automatique()
        self.assertEqual(len(self.fen.selection),3)
        self.app.appliquer_composition.assert_not_called()
        self.fen.appliquer()
        self.assertEqual(self.app.appliquer_composition.call_args.args[1],3)
        self.assertEqual(len(self.app.appliquer_composition.call_args.args[0]),3)

    def test_nombre_manuel_incorrect_bloque(self):
        self.fen.nombre.set('2')
        self.fen.selection=list(self.fen.entrees)[:1]
        self.fen.appliquer()
        self.app.appliquer_composition.assert_not_called()
        self.assertTrue(self.fen.winfo_exists())

    def test_catalogue_insuffisant_et_session_verrouillee(self):
        self.fen.nombre.set('9')
        self.fen.automatique()
        self.assertEqual(self.fen.selection,[])
        self.app.session_verrouillee=True
        self.fen.revenir()
        self.app.appliquer_composition.assert_not_called()
