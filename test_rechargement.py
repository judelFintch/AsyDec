"""Bouton Recharger : détection d'une nouvelle version et relance propre, sans vraie relance."""
from pathlib import Path
import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import rechargement as R
import ui.app as A


class EmpreinteTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.racine = Path(self.temp.name)
        (self.racine / 'ui').mkdir()
        (self.racine / 'moteur.py').write_text('a = 1\n')
        (self.racine / 'ui' / 'app.py').write_text('b = 1\n')
        (self.racine / 'test_x.py').write_text('t = 1\n')

    def test_changement_de_module_detecte(self):
        avant = R.empreinte(self.racine)
        self.assertEqual(set(avant), {'moteur.py', 'ui/app.py'})
        (self.racine / 'ui' / 'app.py').write_text('b = 22\n')
        self.assertNotEqual(R.empreinte(self.racine), avant)

    def test_tests_et_autres_fichiers_ignores(self):
        avant = R.empreinte(self.racine)
        (self.racine / 'test_x.py').write_text('t = 2222\n')
        (self.racine / 'notes.md').write_text('x')
        self.assertEqual(R.empreinte(self.racine), avant)

    def test_commande_relance_point_entree(self):
        commande = R.commande(self.racine)
        self.assertEqual(commande[1], str(self.racine / 'asydec.py'))


class BoutonRechargerTest(unittest.TestCase):
    def app(self, fermeture_acceptee=True):
        app = SimpleNamespace(session_verrouillee=False, rechargement=False, _fermeture=False)
        def quitter():
            app._fermeture = fermeture_acceptee
        app.quitter = Mock(side_effect=quitter)
        return app

    def test_annulation_ne_ferme_rien(self):
        app = self.app()
        with patch.object(A.messagebox, 'askyesno', return_value=False):
            A.AsyDec.recharger(app)
        app.quitter.assert_not_called()
        self.assertFalse(app.rechargement)

    def test_confirmation_ferme_et_demande_relance(self):
        app = self.app()
        with patch.object(A.messagebox, 'askyesno', return_value=True):
            A.AsyDec.recharger(app)
        app.quitter.assert_called_once()
        self.assertTrue(app.rechargement)

    def test_fermeture_refusee_pendant_import(self):
        app = self.app(fermeture_acceptee=False)
        with patch.object(A.messagebox, 'askyesno', return_value=True):
            A.AsyDec.recharger(app)
        self.assertFalse(app.rechargement)

    def test_session_verrouillee(self):
        app = self.app()
        app.session_verrouillee = True
        with patch.object(A.messagebox, 'askyesno') as demander:
            A.AsyDec.recharger(app)
        demander.assert_not_called()

    def test_bandeau_signale_nouvelle_version(self):
        app = SimpleNamespace(_empreinte_code={'a.py': (1, 1)}, var_version=Mock(), _fermeture=True)
        with patch.object(A.rechargement, 'empreinte', return_value={'a.py': (1, 1)}):
            A.AsyDec._surveiller_code(app)
        app.var_version.set.assert_not_called()
        with patch.object(A.rechargement, 'empreinte', return_value={'a.py': (2, 1)}):
            A.AsyDec._surveiller_code(app)
        app.var_version.set.assert_called_once()

    def test_main_relance_apres_fermeture_seulement_si_demande(self):
        for demande in (True, False):
            app = Mock(rechargement=demande, reconnexion=False)
            if not demande:
                del app.rechargement  # comme une doublure sans attribut : aucune relance
            with patch.object(A, 'demander_connexion', return_value='alice'), patch.object(A, 'AsyDec', return_value=app), \
                    patch.object(A.os, 'execv') as relancer:
                A.main()
            app.mainloop.assert_called_once()
            if demande:
                relancer.assert_called_once()
                self.assertTrue(relancer.call_args[0][1][1].endswith('asydec.py'))
            else:
                relancer.assert_not_called()

    def test_doublure_sans_booleen_ne_relance_jamais(self):
        # Régression : un Mock répond « vrai » à tout attribut ; seul True strict relance.
        app = Mock(reconnexion=False)
        with patch.object(A, 'demander_connexion', return_value='alice'), patch.object(A, 'AsyDec', return_value=app), \
                patch.object(A.os, 'execv') as relancer:
            A.main()
        relancer.assert_not_called()


if __name__ == '__main__':
    unittest.main()
