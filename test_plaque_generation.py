"""Plaque facultative saisie à l'étape Dossier : inscrite à la génération, sur un vrai modèle lu seulement."""
import hashlib
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import generer
import modeles_generes as M
import moteur
import variantes
from import_references import extraire

BASE = next(iter(sorted(Path(__file__).resolve().parent.glob('MODELES_XML/*.xml'))), None)


@unittest.skipIf(BASE is None, 'aucun modèle XML local')
class PlaqueGenerationTest(unittest.TestCase):
    def setUp(self):
        self.empreinte = hashlib.sha256(BASE.read_bytes()).hexdigest()
        articles = [a for a in extraire(BASE.read_bytes())['articles'] if a['fob']]
        self.poids = [float(a['poids_brut']) for a in articles]
        self.fob = [float(a['fob']) for a in articles]
        self.colis = [int(float(a['colis'])) for a in articles]
        self.profil = variantes.construire_profil(str(BASE))

    def tearDown(self):
        self.assertEqual(hashlib.sha256(BASE.read_bytes()).hexdigest(), self.empreinte)

    def produire(self, plaque=None):
        return generer.produire(str(BASE), self.poids, self.profil['ratios'], [], {}, mode='SAISI',
                                fob_saisis=self.fob, colis_saisis=self.colis, enregistrer=False,
                                profil=self.profil, plaque=plaque)

    def test_sans_plaque_comportement_inchange(self):
        res = self.produire('   ')
        self.assertIsNone(res['plaque'])
        self.assertEqual(res['info']['camion'], moteur.infos_dossier(moteur.charger(str(BASE)).getroot())['camion'])
        self.assertFalse(any('Plaque inscrite' in a for a in res['alertes']))

    def test_plaque_saisie_dans_info_alerte_et_modele(self):
        res = self.produire(' t111aaa / t222bbb ')
        self.assertEqual(res['plaque'], 'T111AAA / T222BBB')
        self.assertEqual(res['info']['camion'], 'T111AAA / T222BBB')
        self.assertTrue(any('Plaque inscrite dans le XML : T111AAA / T222BBB' in a for a in res['alertes']))
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / 'modeles.db'
            identifiant = M.enregistrer(res, BASE, 'alice', base=base)
            d = M.detail(identifiant, base=base)
            valeurs = [e.text for e in ET.fromstring(bytes(d['modele_xml'])).findall('Transport/Means_of_transport/*/Identity')]
            self.assertEqual(valeurs, ['T111AAA / T222BBB'] * 2)
            self.assertEqual(d['plaque'], 'T111AAA / T222BBB')
            # Même répartition sans plaque : modèle distinct, empreinte historique inchangée.
            self.assertNotEqual(M.enregistrer(self.produire(), BASE, 'alice', base=base), identifiant)

    def test_plaque_invalide_refusee(self):
        self.assertRaises(ValueError, self.produire, '../etc')


class EcrirePlaqueTest(unittest.TestCase):
    def test_null_remplace_et_absence_refusee(self):
        racine = ET.fromstring('<ASYCUDA><Transport><Means_of_transport><Departure_arrival_information>'
                               '<Identity><null/></Identity></Departure_arrival_information></Means_of_transport>'
                               '</Transport></ASYCUDA>')
        moteur.ecrire_plaque(racine, 'ab12')
        identite = racine.find(moteur.CHEMINS_PLAQUE[0])
        self.assertEqual((identite.text, len(identite)), ('AB12', 0))
        self.assertRaises(ValueError, moteur.ecrire_plaque, ET.fromstring('<ASYCUDA/>'), 'AB12')


if __name__ == '__main__':
    unittest.main()
