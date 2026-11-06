import tempfile
from pathlib import Path
import unittest

from asydec.declarations import licences_ouvertes as registre
from asydec.declarations.documents_finaux import preparer_licence


class LicencesOuvertesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fichier = Path(self.temp.name) / 'donnees' / 'licences.sqlite'

    def licence(self, numero='DEC123-ADD0-IB', articles=2):
        licence = preparer_licence('DEC123', '12345.67', numero, '17/03/2026')
        licence.update(soussigne={'nom': 'Société été'}, fournisseur={'adresse': 'Ligne 1\nLigne 2'},
                       produits=[{'designation': f'Article {i}\nDétail'} for i in range(articles)])
        return licence

    def test_liste_vide(self):
        self.assertEqual(registre.lister(self.fichier), [])

    def test_persistence_de_toutes_les_informations(self):
        licence = self.licence(articles=17)
        registre.enregistrer(licence, self.fichier)
        relu = registre.charger(licence['numero_validation'], self.fichier)
        self.assertEqual(relu['date_validation'], '17/03/2026')
        self.assertEqual(relu['montant_fob'], '12345.67')
        for cle in ('soussigne', 'fournisseur', 'produits'):
            self.assertEqual(relu[cle], licence[cle])
        ligne = registre.lister(self.fichier)[0]
        self.assertEqual(ligne['articles'], 17)
        self.assertEqual(ligne['soussigne'], 'Société été')

    def test_mise_a_jour_sans_doublon_et_licences_distinctes(self):
        registre.enregistrer(self.licence(), self.fichier)
        registre.enregistrer(self.licence('DEC999-ADD0-IB'), self.fichier)
        registre.enregistrer(self.licence(articles=3), self.fichier)
        self.assertEqual(len(registre.lister(self.fichier)), 2)
        self.assertEqual(len(registre.charger('DEC123-ADD0-IB', self.fichier)['produits']), 3)
        self.assertEqual(len(registre.charger('DEC999-ADD0-IB', self.fichier)['produits']), 2)

    def test_licence_inconnue(self):
        with self.assertRaises(ValueError):
            registre.charger('inconnue', self.fichier)
