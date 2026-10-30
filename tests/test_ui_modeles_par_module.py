"""La liste visible des modèles change réellement avec le module actif."""
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import patch

from asydec.declarations import modeles_generes as M
from asydec.ui.modeles_generes import PageModelesGeneres
from tests import test_modeles_generes as fixtures


class ListeModelesParModuleTest(unittest.TestCase):
    def test_liste_friperie_et_divers_sans_melange(self):
        fixture=fixtures.ModelesGeneresTest(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        racine=tk.Tk()
        racine.withdraw()
        self.addCleanup(racine.destroy)
        with patch.object(M,'BASE',fixture.base), patch('asydec.ui.modeles_generes.analyser_modeles',return_value={}):
            friperie=M.enregistrer(fixture.resultat,fixture.source,'alice',module='friperie')
            divers=M.enregistrer(fixture.resultat,fixture.source,'alice',module='divers')
            app=SimpleNamespace(module_travail='friperie',session_verrouillee=False)
            page=PageModelesGeneres(racine,app)
            page.afficher()
            self.assertEqual(page.table.get_children(),(str(friperie),))
            app.module_travail='divers'
            page.afficher()
            self.assertEqual(page.table.get_children(),(str(divers),))
            self.assertNotIn(str(friperie),page.modeles)
            page.filtre.set('Validé localement')
            page.afficher()
            self.assertEqual(page.table.get_children(),())
