from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from asydec.declarations import factures as F
from tests.test_factures import document


class GabaritChoisiTest(TestCase):
    def test_archive_autre_client_ne_remplace_pas_le_word_choisi(self):
        with TemporaryDirectory() as d:
            base = Path(d) / 'factures.db'
            ids = []
            for client in ('STE QUATRE E', 'ETS JAQ'):
                p = Path(d) / (client + '.docx')
                p.write_bytes(document('<w:r><w:t>Consignee: ' + client + '</w:t></w:r>'
                                      '<w:r><w:t> INV NO: {{NUMERO_FACTURE}} {{DATE_FACTURE}} {{POIDS}} {{COLIS}} {{FOB}}</w:t></w:r>'))
                ids.append(F.importer(p, base))
            modele = {'supprime': False, 'importateur': 'SHABANI SUMAILI CHARLY', 'plaque': 'T123ABC',
                      'resultat': {'resume': {'poids': 100, 'fob': 200}, 'colis': [10]}}
            with patch('asydec.declarations.modeles_generes.detail', return_value=modele):
                ancienne = F.generer(26, ids[0], 'test', base)
                correcte = F.generer(26, ids[1], 'test', base)
                retour = F.generer(26, ids[0], 'test', base)
                encore = F.generer(26, ids[1], 'test', base)
                with self.assertRaisesRegex(ValueError, 'introuvable'):
                    F.generer(26, 99999, 'test', base)
            self.assertEqual(F.analyser_gabarit(correcte['contenu'])['destinataire'], 'ETS JAQ')
            self.assertEqual(correcte['gabarit_id'], ids[1])
            self.assertNotEqual(ancienne['numero'], correcte['numero'])
            self.assertEqual(ancienne['date_facture'], correcte['date_facture'])
            self.assertEqual(retour['contenu'], ancienne['contenu'])
            self.assertEqual(encore['contenu'], correcte['contenu'])
            self.assertEqual(F.lire(ancienne['id'], base)['contenu'], ancienne['contenu'])
            archives = F.lister_factures(26, base)
            self.assertEqual(len(archives), 2)
            self.assertEqual(archives[0]['nom_gabarit'], 'ETS JAQ')
