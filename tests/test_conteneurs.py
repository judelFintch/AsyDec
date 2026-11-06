import tempfile
import unittest
from pathlib import Path

from asydec.declarations import conteneurs, licences_ouvertes as registre
from asydec.declarations.documents_finaux import preparer_licence


class ConteneursTest(unittest.TestCase):
    def test_chiffre_controle_iso_6346(self):
        # Numéros réels connus : CSQU3054383 (exemple de la norme), MSKU9070323.
        self.assertEqual(conteneurs.chiffre_controle('CSQU305438'), 3)
        self.assertTrue(conteneurs.est_valide('CSQU 3054383'))
        self.assertTrue(conteneurs.est_valide('MSKU 9070323'))
        self.assertFalse(conteneurs.est_valide('MRSU 6083519'))
        self.assertFalse(conteneurs.est_valide('MRSU6083518'))

    def test_propositions_valides_uniques_et_conservees(self):
        paires = conteneurs.proposer(12)
        self.assertEqual(len({p['conteneur'] for p in paires}), 12)
        self.assertEqual(len({p['scelle'] for p in paires}), 12)
        for paire in paires:
            self.assertRegex(paire['conteneur'], r'^MRSU \d{7}$')
            self.assertTrue(conteneurs.est_valide(paire['conteneur']))
            self.assertRegex(paire['scelle'], r'^G915\d{4}$')
        self.assertEqual(conteneurs.proposer(12, paires), paires)
        doublon = [paires[0], dict(paires[0]), {'conteneur': 'MRSU 6083519', 'scelle': 'G9150287'}]
        corrige = conteneurs.proposer(3, doublon)
        self.assertEqual(corrige[0], paires[0])
        self.assertNotEqual(corrige[1]['conteneur'], paires[0]['conteneur'])
        self.assertTrue(conteneurs.est_valide(corrige[2]['conteneur']))

    def test_persistance_par_part(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / 'licences.sqlite'
            licence = preparer_licence('DEC123', '300000', 'LIC', '17/03/2026')
            registre.enregistrer(licence, fichier)
            registre.enregistrer_repartition('LIC', '300000', 23000, fichier)
            premier = registre.charger('LIC', fichier)
            paires = [(p['conteneur'], p['scelle']) for p in premier['repartition']['parts']]
            self.assertEqual(len(set(paires)), 3)
            registre.enregistrer_repartition('LIC', '300000', 22000, fichier)
            relu = registre.charger('LIC', fichier)
            self.assertEqual([(p['conteneur'], p['scelle']) for p in relu['repartition']['parts']], paires)
            lignes = registre.lister_repartitions('LIC', fichier)
            self.assertEqual([(l['conteneur'], l['scelle']) for l in lignes], paires)
