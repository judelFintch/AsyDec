import logging
import tempfile
import unittest
from pathlib import Path
from logging.handlers import RotatingFileHandler

from asydec.systeme import journal


class JournalTest(unittest.TestCase):
    def tearDown(self):
        for h in list(journal.journal.handlers):
            if isinstance(h, RotatingFileHandler):
                journal.journal.removeHandler(h)
                h.close()

    def test_sans_activation_rien_n_est_ecrit(self):
        try:
            raise ValueError('test')
        except ValueError:
            journal.erreur_ignoree('aide facultative')
        self.assertFalse(any(isinstance(h, RotatingFileHandler) for h in journal.journal.handlers))

    def test_erreur_ignoree_garde_la_trace(self):
        with tempfile.TemporaryDirectory() as d:
            fichier = Path(d) / 'sous' / 'asydec.log'
            journal.activer(fichier)
            journal.activer(fichier)
            try:
                raise ValueError('totaux impossibles')
            except ValueError:
                journal.erreur_ignoree('compteur')
            for h in journal.journal.handlers:
                h.flush()
            texte = fichier.read_text(encoding='utf-8')
            self.assertIn('Erreur ignorée — compteur', texte)
            self.assertIn('ValueError: totaux impossibles', texte)
            self.assertIn('Traceback', texte)
            self.assertEqual(texte.count('Erreur ignorée'), 1)


if __name__ == '__main__':
    unittest.main()
