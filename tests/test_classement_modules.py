"""Une médiathèque par type de dossier : aucun partage, ratios et profils propres à chaque module."""
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from asydec.calcul import moteur, variantes
from asydec.references import base_references as B, catalogue_xml as C
from asydec.references import import_references as I
from asydec.systeme import gestion_locale as L
from asydec.ui.app import AsyDec
from tests import test_modeles_dynamiques as fixtures


class MediathequesModulesTest(unittest.TestCase):
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
        self.sha = variantes.hashlib.sha256(self.autre.read_bytes()).hexdigest()

    def noms(self, module):
        return sorted(d['nom'] for d in C.lister(self.conn, module=module))

    def test_chaque_module_ne_voit_que_sa_mediatheque(self):
        C.partager(self.conn, [self.source], 'friperie')
        C.partager(self.conn, [self.autre], 'divers')
        self.assertEqual(self.noms('friperie'), [self.source.name])
        self.assertEqual(self.noms('divers'), ['divers.xml'])
        for module, ratio in (('friperie', 1.5), ('divers', 3)):
            chemins = [d['chemin'] for d in C.lister(self.conn, module=module, generation=True)]
            profil = variantes.construire_profil(chemins[0], chemins, dynamique=True)
            self.assertEqual(profil['ratios'], [ratio]*3)
            self.assertEqual(len(profil['references']), 1)

    def test_meme_xml_dans_deux_mediatheques_retrait_independant(self):
        C.partager(self.conn, [self.autre], 'friperie')
        C.partager(self.conn, [self.autre], 'divers')
        self.assertEqual((self.noms('friperie'), self.noms('divers')), (['divers.xml'], ['divers.xml']))
        C.retirer_du_module(self.conn, [self.sha], 'divers')
        self.assertEqual((self.noms('friperie'), self.noms('divers')), (['divers.xml'], []))
        self.assertTrue(self.conn.execute('SELECT 1 FROM documents WHERE sha256=?', (self.sha,)).fetchone())
        # Un nouvel ajout le remet dans la médiathèque Divers, avec le même document.
        C.partager(self.conn, [self.autre], 'divers')
        self.assertTrue(C.dans_module(self.conn, self.sha, 'divers'))

    def test_type_ou_empreinte_invalides_refuses(self):
        with self.assertRaises(ValueError):
            C.ajouter(self.conn, [self.sha], 'autre')
        with self.assertRaises(ValueError):
            C.ajouter(self.conn, ['pas-une-empreinte'], 'divers')
        self.assertFalse(C.dans_module(self.conn, self.sha, 'divers'))

    def test_migration_reprend_les_classements_existants(self):
        conn = sqlite3.connect(self.racine/'ancienne.db', isolation_level=None)
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        B.migrer(conn, B.MIGRATIONS[:3])
        I.importer_fichier(conn, self.source)
        I.importer_fichier(conn, self.autre)
        conn.execute("INSERT INTO xml_modules(sha256, module) VALUES (?, 'divers')", (self.sha,))
        B.migrer(conn)
        membres = sorted(tuple(r) for r in conn.execute('SELECT module, sha256 FROM xml_mediatheques'))
        sha_source = variantes.hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.assertEqual(membres, sorted([('divers', self.sha), ('friperie', sha_source)]))
        self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='xml_modules'").fetchone())

    def test_application_modeles_locaux_seulement_en_friperie(self):
        C.partager(self.conn, [self.autre], 'divers')
        modele_local = self.racine/'modele-local.xml'
        modele_local.write_bytes(self.source.read_bytes() + b'<!-- local -->')
        app = SimpleNamespace(base=None, base_dossier=None, base_refs=lambda: self.conn, module_travail='divers')
        with patch.object(variantes, 'modeles', return_value=[modele_local]):
            self.assertEqual([d['nom'] for d in AsyDec.xml_disponibles(app)], ['divers.xml'])
            app.module_travail = 'friperie'
            self.assertEqual([d['nom'] for d in AsyDec.xml_disponibles(app)], ['modele-local.xml'])


if __name__ == '__main__':
    unittest.main()
