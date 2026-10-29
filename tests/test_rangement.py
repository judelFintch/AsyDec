"""Rangement des fichiers par importateur, sur un dossier DEC temporaire."""
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from asydec.declarations import generer
import asydec.ui.modeles_generes as U


class RangementTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.object(generer, 'DEC', self.temp.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_sous_dossiers_par_type_crees_au_besoin(self):
        table = [('SOCIETE K.D.META', 'KDMETA')]
        attendu = {'historique': '1 - HISTORIQUE', 'sources': '2 - VOS FICHIERS (bases et SYDONIA)',
                   'valides': '4 - XML VALIDES', 'pdf': '5 - PDF'}
        for cle, nom in attendu.items():
            chemin = Path(generer.dossier_rangement('SOCIETE K.D.META', cle, table))
            self.assertEqual(chemin, Path(self.temp.name) / 'KDMETA' / nom)
            self.assertTrue(chemin.is_dir())

    def test_sans_creation_et_importateur_inconnu(self):
        chemin = Path(generer.dossier_rangement('SOCIETE NOUVELLE', 'pdf', [], creer=False))
        self.assertEqual(chemin.parent.name, 'NOUVELLE')
        self.assertFalse(chemin.exists())

    def test_contenu_existant_jamais_touche(self):
        dossier = Path(self.temp.name) / 'KDMETA' / '5 - PDF'
        dossier.mkdir(parents=True)
        (dossier / 'ancien.pdf').write_bytes(b'x')
        generer.dossier_rangement('SOCIETE K.D.META', 'pdf', [('SOCIETE K.D.META', 'KDMETA')])
        self.assertEqual((dossier / 'ancien.pdf').read_bytes(), b'x')

    def test_aide_interface_sans_importateur_ou_en_erreur(self):
        self.assertIsNone(U.rangement(SimpleNamespace(), '', 'pdf'))
        with patch.object(generer, 'dossier_rangement', side_effect=OSError('lecture seule')):
            self.assertIsNone(U.rangement(SimpleNamespace(), 'X', 'pdf'))


if __name__ == '__main__':
    unittest.main()
