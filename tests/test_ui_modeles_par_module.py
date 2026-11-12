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
            self.assertEqual(page.lignes_affichees(),(str(friperie),))
            app.module_travail='divers'
            page.afficher()
            self.assertEqual(page.lignes_affichees(),(str(divers),))
            self.assertNotIn(str(friperie),page.modeles)
            page.filtre.set('Validé localement')
            page.afficher()
            self.assertEqual(page.lignes_affichees(),())


class RangementParEtapeTest(unittest.TestCase):
    def test_etape_periode_recherche(self):
        from datetime import datetime, timedelta, timezone
        import asydec.ui.modeles_generes as U
        maintenant = datetime.now(timezone.utc)
        hier = (maintenant - timedelta(days=1)).isoformat()
        vieux = (maintenant - timedelta(days=40)).isoformat()
        self.assertEqual(U.etape({'statut': 'en_attente'}), 'encours')
        self.assertEqual(U.etape({'statut': 'valide', 'comparaisons': 0}), 'prets')
        self.assertEqual(U.etape({'statut': 'valide', 'comparaisons': 2}), 'passes')
        self.assertEqual(U.etape({'statut': 'rejete', 'comparaisons': 2}), 'rejetes')
        self.assertTrue(U.dans_periode({'modifie_utc': maintenant.isoformat()}, 0))
        self.assertFalse(U.dans_periode({'modifie_utc': hier}, 0))
        self.assertTrue(U.dans_periode({'modifie_utc': hier}, 7))
        self.assertFalse(U.dans_periode({'modifie_utc': vieux}, 30))
        self.assertTrue(U.dans_periode({'modifie_utc': vieux}, None))
        self.assertTrue(U.quand_court(maintenant.isoformat()).startswith("aujourd'hui"))
        self.assertTrue(U.quand_court(hier).startswith('hier'))
        m = {'id': 23, 'plaque': 'T524ECQ/T620ECT', 'importateur': 'SHABANI SUMAILI', 'chemin_xml': None}
        self.assertTrue(U.correspond(m, 't524'))
        self.assertTrue(U.correspond(m, 'shabani'))
        self.assertFalse(U.correspond(m, 'kdmeta'))

    def test_sections_dans_la_table(self):
        fixture=fixtures.ModelesGeneresTest(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        racine=tk.Tk()
        racine.withdraw()
        self.addCleanup(racine.destroy)
        with patch.object(M,'BASE',fixture.base), patch('asydec.ui.modeles_generes.analyser_modeles',return_value={}):
            a=M.enregistrer(fixture.resultat,fixture.source,'alice',module='friperie')
            page=PageModelesGeneres(racine,SimpleNamespace(module_travail='friperie',session_verrouillee=False))
            page.afficher()
            self.assertEqual(page.table.get_children(),('section:encours',))
            self.assertEqual(page.lignes_affichees(),(str(a),))
            page.table.selection_set('section:encours')
            self.assertIsNone(page.selection())
            page.var_recherche.set('aucune-plaque-pareille')
            page.afficher()
            self.assertEqual(page.lignes_affichees(),())
