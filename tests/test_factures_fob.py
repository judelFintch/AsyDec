"""Facture commerciale en FOB : fret et assurance à zéro, total égal au FOB, sans calcul."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
from xml.dom import minidom
from zipfile import ZipFile

from asydec.declarations import factures as F
from tests.test_factures import document


class FactureFobTest(TestCase):
    def test_fret_assurance_zero_et_total_egal_fob(self):
        with TemporaryDirectory() as dossier:
            base = Path(dossier) / 'factures.db'
            source = Path(dossier) / 'facture.docx'
            source.write_bytes(document(
                '<w:r><w:t>{{NUMERO_FACTURE}} {{POIDS}} {{COLIS}} FOB {{FOB}} | FRET {{FRET}} | '
                'ASSURANCE {{ASSURANCE}} | TOTAL {{CIF_USD}}</w:t></w:r>'))
            gabarit = F.importer(source, base)
            # La déclaration a du fret et de l'assurance : la facture ne doit pas les reprendre.
            modele = {'supprime': False, 'importateur': 'A', 'plaque': 'ABC123',
                      'resultat': {'resume': {'poids': 1000, 'fob': 7600, 'fret': 300, 'assurance': 50},
                                   'colis': [10]}}
            with patch('asydec.declarations.modeles_generes.detail', return_value=modele):
                facture = F.generer(42, gabarit, 'test', base)
            with ZipFile(BytesIO(facture['contenu'])) as z:
                doc = minidom.parseString(z.read('word/document.xml'))
            texte = ''.join(F._texte(t) for t in doc.getElementsByTagNameNS(F.W, 't'))
        self.assertIn('FOB 7 600,00 | FRET 0,00 | ASSURANCE 0,00 | TOTAL 7 600,00', texte)

    def test_montant_en_lettres_us_dollars_remplace_par_le_fob(self):
        # Modèle déjà importé avec le montant d'exemple en texte fixe (« US DOLLARS »).
        from asydec.declarations.preparer_facture import preparer_lettres
        with TemporaryDirectory() as dossier:
            base = Path(dossier) / 'factures.db'
            source = Path(dossier) / 'facture.docx'
            source.write_bytes(document(
                '<w:r><w:t>{{NUMERO_FACTURE}} {{POIDS}} {{COLIS}} {{FOB}} {{PLAQUE}}</w:t></w:r></w:p><w:p>'
                '<w:r><w:t>AMT IN WORDS EIGHT THOUSAND </w:t></w:r><w:r><w:t>EIGHT HUNDRED US DOLLARS</w:t></w:r>'))
            gabarit = F.importer(source, base)
            modele = {'supprime': False, 'importateur': 'A', 'plaque': 'ABC123',
                      'resultat': {'resume': {'poids': 1000, 'fob': 7600}, 'colis': [10]}}
            with patch('asydec.declarations.modeles_generes.detail', return_value=modele):
                facture = F.generer(42, gabarit, 'test', base)
            with ZipFile(BytesIO(facture['contenu'])) as z:
                doc = minidom.parseString(z.read('word/document.xml'))
        texte = ''.join(F._texte(t) for t in doc.getElementsByTagNameNS(F.W, 't'))
        self.assertIn('AMT IN WORDS SEVEN THOUSAND SIX HUNDRED US DOLLARS', texte)
        self.assertNotIn('EIGHT', texte)
        # Déjà balisé : rien ne change.
        prepare = preparer_lettres(document('<w:r><w:t>AMT IN WORDS {{FOB_LETTRES}} UNITED STATES DOLLARS</w:t></w:r>'))
        self.assertIn(b'{{FOB_LETTRES}}', ZipFile(BytesIO(prepare)).read('word/document.xml'))

    def test_date_toujours_trois_mois_avant(self):
        from datetime import date
        cas = {date(2026, 11, 3): date(2026, 8, 3), date(2026, 1, 15): date(2025, 10, 15),
               date(2026, 5, 31): date(2026, 2, 28), date(2024, 5, 30): date(2024, 2, 29)}
        for jour, attendu in cas.items():
            self.assertEqual(F.date_facture(jour), attendu)
            self.assertGreaterEqual((jour - F.date_facture(jour)).days, 89)

    def test_facture_jamais_datee_du_jour(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        with TemporaryDirectory() as dossier:
            base = Path(dossier) / 'factures.db'
            source = Path(dossier) / 'facture.docx'
            source.write_bytes(document('<w:r><w:t>{{NUMERO_FACTURE}} {{POIDS}} {{COLIS}} {{FOB}} '
                                        'Date: {{DATE_FACTURE}}</w:t></w:r>'))
            gabarit = F.importer(source, base)
            modele = {'supprime': False, 'importateur': 'A', 'plaque': 'ABC123',
                      'resultat': {'resume': {'poids': 1000, 'fob': 7600}, 'colis': [10]}}
            with patch('asydec.declarations.modeles_generes.detail', return_value=modele):
                facture = F.generer(42, gabarit, 'test', base)
            with ZipFile(BytesIO(facture['contenu'])) as z:
                doc = minidom.parseString(z.read('word/document.xml'))
            emission = datetime.fromisoformat(F.lister_factures(42, base)[0]['date'])
        texte = ''.join(F._texte(t) for t in doc.getElementsByTagNameNS(F.W, 't'))
        aujourdhui = datetime.now(ZoneInfo('Africa/Lubumbashi')).date()
        self.assertIn(f"Date: {F.date_facture(aujourdhui):%d/%m/%Y}", texte)
        self.assertNotIn(f'{aujourdhui:%d/%m/%Y}', texte)
        self.assertEqual(emission.date(), aujourdhui)  # l'archive garde la vraie date d'émission


if __name__ == '__main__':
    main()
