import tempfile
from pathlib import Path
import sqlite3
import unittest

from asydec.declarations import licences_ouvertes as registre
from asydec.declarations.documents_finaux import preparer_licence
from asydec.ui.liste_licences import COCHE, VIDE, libelle_physique


class DossierPhysiqueTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.fichier = Path(temp.name) / 'licences.sqlite'
        for numero in ('L1', 'L2'):
            licence = preparer_licence('DEC' + numero, '100', numero, '17/03/2026')
            licence.update(soussigne={'nom': 'S'}, produits=[])
            registre.enregistrer(licence, self.fichier)

    def _modifie_le(self, numero):
        with sqlite3.connect(self.fichier) as conn:
            return conn.execute('SELECT modifie_le FROM licences WHERE numero=?', (numero,)).fetchone()[0]

    def test_cocher_puis_decocher(self):
        self.assertEqual({l['numero']: l['physique'] for l in registre.lister(self.fichier)}, {'L1': '', 'L2': ''})
        avant = self._modifie_le('L1')
        date = registre.marquer_physique('L1', True, fichier=self.fichier)
        self.assertTrue(date)
        self.assertEqual({l['numero']: l['physique'] for l in registre.lister(self.fichier)}, {'L1': date, 'L2': ''})
        # Cocher ne réordonne pas la liste des licences.
        self.assertEqual(self._modifie_le('L1'), avant)
        self.assertEqual(registre.marquer_physique('L1', False, fichier=self.fichier), '')
        self.assertNotIn('physique', registre.charger('L1', self.fichier))

    def test_source_impression_retenue(self):
        registre.marquer_physique('L2', True, source='impression', fichier=self.fichier)
        self.assertEqual(registre.charger('L2', self.fichier)['physique']['source'], 'impression')

    def test_enregistrement_du_formulaire_conserve_la_coche(self):
        # Formulaire ouvert avant la coche : il ne connaît pas « physique ».
        licence = preparer_licence('DECL1', '100', 'L1', '17/03/2026')
        licence.update(soussigne={'nom': 'S'}, produits=[])
        date = registre.marquer_physique('L1', True, fichier=self.fichier)
        registre.enregistrer(licence, self.fichier)
        self.assertEqual(registre.charger('L1', self.fichier)['physique']['le'], date)

    def test_licence_inconnue(self):
        with self.assertRaises(ValueError):
            registre.marquer_physique('INCONNUE', True, fichier=self.fichier)

    def test_libelle(self):
        self.assertEqual(libelle_physique(''), VIDE)
        self.assertTrue(libelle_physique('2026-11-10T08:00:00+00:00').startswith(COCHE + ' 10/11'))


if __name__ == '__main__':
    unittest.main()
