"""Catalogue commun, types persistants et profils calculés sans mélanger les ratios."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from asydec.calcul import moteur, variantes
from asydec.references import base_references as B, catalogue_xml as C
from asydec.systeme import gestion_locale as L
from asydec.ui.app import AsyDec
from tests import test_modeles_dynamiques as fixtures


class ClassementModulesTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ModelesDynamiquesTest(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.racine = self.fixture.fixture.racine
        config = patch.object(L, 'CONFIGURATION', self.racine/'CONFIG_LOCAL')
        config.start()
        self.addCleanup(config.stop)
        self.source = self.fixture.source(3)
        self.autre = self.racine/'divers.xml'
        arbre = moteur.charger(self.source)
        moteur.recalculer(arbre, [(300,100)]*3, [10,11,12])
        arbre.write(self.autre)
        self.conn = B.ouvrir(self.racine/'catalogue.db')
        self.addCleanup(self.conn.close)
        C.partager(self.conn, [self.source, self.autre])
        self.sha = variantes.hashlib.sha256(self.autre.read_bytes()).hexdigest()

    def test_catalogue_commun_et_selection_par_type(self):
        C.classer(self.conn, [self.sha], 'divers')
        self.assertEqual(len(C.lister(self.conn)), 2)
        friperie = C.lister(self.conn, module='friperie', generation=True)
        divers = C.lister(self.conn, module='divers', generation=True)
        self.assertEqual(len(friperie), 1)
        self.assertEqual(len(divers), 1)
        for documents, ratio in ((friperie, 1.5), (divers, 3)):
            chemins = [d['chemin'] for d in documents]
            profil = variantes.construire_profil(chemins[0], chemins, dynamique=True)
            self.assertEqual(profil['ratios'], [ratio]*3)
            self.assertEqual(profil['bornes'], [(ratio,ratio)]*3)
            self.assertEqual(len(profil['references']), 1)

    def test_copie_et_reimport_ne_changent_pas_le_type(self):
        C.classer(self.conn, [self.sha], 'divers')
        copie = self.racine/'renomme.xml'
        copie.write_bytes(self.autre.read_bytes())
        C.partager(self.conn, [copie])
        C.classer(self.conn, [self.sha], 'friperie', remplacer=False)
        self.assertEqual(C.module_document(self.conn, self.sha), 'divers')
        self.assertEqual(len(C.lister(self.conn, [copie], module='divers')), 1)
        autre_conn = B.ouvrir(self.racine/'catalogue.db')
        self.addCleanup(autre_conn.close)
        self.assertEqual(C.module_document(autre_conn, self.sha), 'divers')

    def test_type_invalide_refuse_sans_modifier_le_catalogue(self):
        with self.assertRaises(ValueError):
            C.classer(self.conn, [self.sha], 'autre')
        self.assertEqual(C.module_document(self.conn, self.sha), 'friperie')

    def test_application_filtre_les_xml_du_module_et_media_affiche_tous(self):
        C.classer(self.conn, [self.sha], 'divers')
        app = SimpleNamespace(base=None, base_refs=lambda:self.conn, module_travail='divers')
        with patch.object(variantes, 'modeles', return_value=[]):
            self.assertEqual(len(AsyDec.xml_disponibles(app, generation=True)), 1)
            self.assertEqual(len(AsyDec.xml_disponibles(app, tous_modules=True)), 2)

    def test_reference_d_autre_type_refusee_avant_changement_de_ratio(self):
        C.classer(self.conn, [self.sha], 'divers')
        app = SimpleNamespace(base_refs=lambda:self.conn, module_travail='friperie',
                              reference='origine.xml', profil={'ratios':[1.5]*3})
        with patch('asydec.ui.app.messagebox.showerror') as erreur:
            self.assertFalse(AsyDec.choisir_reference(app, self.autre))
        erreur.assert_called_once()
        self.assertEqual(app.reference, 'origine.xml')
        self.assertEqual(app.profil['ratios'], [1.5]*3)
