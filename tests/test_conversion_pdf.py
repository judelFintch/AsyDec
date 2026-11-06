"""Conversion Word -> PDF : refus clair sans Word, nettoyage du dossier de Word, message d'autorisation."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from asydec.systeme import conversion_pdf as C


class ConversionTest(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.docx = self.dossier / 'facture.docx'
        self.docx.write_bytes(b'docx')

    def test_sans_word_refus_clair(self):
        with patch.object(C, 'disponible', return_value=False):
            with self.assertRaisesRegex(C.ConversionImpossible, 'Word n’est pas installé'):
                C.docx_vers_pdf(self.docx)

    def test_mac_pdf_rapporte_a_cote_du_word(self):
        word = self.dossier / 'word'

        def faux_osascript(commande, **_):
            Path(commande[3]).write_bytes(b'%PDF')  # Word écrit le PDF dans son dossier
            return subprocess.CompletedProcess(commande, 0, 'ok', '')
        with patch.object(C, 'disponible', return_value=True), patch.object(C.sys, 'platform', 'darwin'), \
                patch.object(C, 'DOSSIER_WORD_MAC', word), patch.object(C.subprocess, 'run', side_effect=faux_osascript):
            pdf = C.docx_vers_pdf(self.docx)
        self.assertEqual(pdf, self.dossier / 'facture.pdf')
        self.assertEqual(pdf.read_bytes(), b'%PDF')
        self.assertEqual(list(word.iterdir()), [])  # copies de travail effacées

    def test_mac_autorisation_refusee(self):
        refus = subprocess.CompletedProcess([], 1, '', 'execution error: Non autorisé à envoyer des évènements Apple (-1743)')
        with patch.object(C, 'disponible', return_value=True), patch.object(C.sys, 'platform', 'darwin'), \
                patch.object(C, 'DOSSIER_WORD_MAC', self.dossier / 'word'), patch.object(C.subprocess, 'run', return_value=refus):
            with self.assertRaisesRegex(C.ConversionImpossible, 'Automatisation'):
                C.docx_vers_pdf(self.docx)


if __name__ == '__main__':
    unittest.main()
