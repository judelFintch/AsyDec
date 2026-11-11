from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from asydec.declarations import factures as F
from asydec.declarations.preparer_facture import dater_manifeste
from tests.test_factures import document
from tests.test_facture_licence import texte


class DateManifesteTest(TestCase):
    def test_delai_et_jour_de_semaine_sur_une_annee(self):
        debut = datetime(2026, 1, 1)
        for n in range(366):
            facture = debut + timedelta(days=n)
            date = facture.strftime('%d/%m/%Y')
            resultat = F.date_manifeste(date, 'SX-981-097')
            manifeste = datetime.strptime(resultat, '%d/%m/%Y')
            self.assertIn((manifeste - facture).days, range(3, 7))
            self.assertLess(manifeste.weekday(), 5)
            self.assertEqual(F.date_manifeste(date, 'SX-981-097'), resultat)

    def test_remplacement_fragmente_et_dates_facture_preservees(self):
        source = document('<w:r><w:t>MANIFEST NO: 1234-ML1234 / DATE: 11/08/2026 / </w:t></w:r>'
                          '<w:r><w:t>14/02/</w:t></w:r><w:r><w:t>2025          TZ</w:t></w:r>')
        corrige = dater_manifeste(source, '14/08/2026')
        self.assertIn('DATE: 11/08/2026', texte(corrige))
        self.assertIn('14/08/2026', texte(corrige))
        self.assertIn('          TZ', texte(corrige))
        self.assertNotIn('2025', texte(corrige))
        self.assertEqual(dater_manifeste(corrige, '14/08/2026'), corrige)

    def test_generation_et_retelechargement(self):
        with TemporaryDirectory() as d:
            base = Path(d) / 'factures.db'
            source = Path(d) / 'modele.docx'
            source.write_bytes(document('<w:r><w:t>{{NUMERO_FACTURE}} {{DATE_FACTURE}} {{POIDS}} {{COLIS}} {{FOB}} '
                                        'MANIFEST NO: {{NUMERO_MANIFESTE}} / 14/02/2025          TZ</w:t></w:r>'))
            gabarit = F.importer(source, base)
            modele = {'supprime': False, 'plaque': 'T123ABC', 'importateur': 'TEST',
                      'resultat': {'resume': {'poids': 100, 'fob': 200}, 'colis': [10]}}
            with patch('asydec.declarations.modeles_generes.detail', return_value=modele):
                facture = F.generer(1, gabarit, 'test', base)
                encore = F.generer(1, gabarit, 'test', base)
            date = F.date_manifeste(facture['date_facture'], facture['numero'])
            self.assertIn(date, texte(facture['contenu']))
            self.assertNotIn('14/02/2025', texte(facture['contenu']))
            self.assertEqual(encore['contenu'], facture['contenu'])
            self.assertEqual(F.lire(facture['id'], base)['contenu'], facture['contenu'])
