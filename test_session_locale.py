"""Contrats de session et de raccordement au reset, sans fenêtre ni données réelles."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import ui.app as app_module


class SessionLocaleTest(unittest.TestCase):
    def test_annulation_connexion_ne_construit_pas_application(self):
        with patch.object(app_module, 'demander_connexion', return_value=None), \
             patch.object(app_module, 'AsyDec') as application:
            app_module.main()
        application.assert_not_called()

    def test_connexion_avant_creation_interface(self):
        with patch.object(app_module, 'demander_connexion', return_value='admin') as connexion, \
             patch.object(app_module, 'AsyDec') as application:
            application.return_value.reconnexion = False
            app_module.main()
        connexion.assert_called_once()
        application.assert_called_once_with('admin')
        application.return_value.mainloop.assert_called_once()

    def test_refus_service_arrete_preparation_reset(self):
        premier = Mock(return_value=False)
        suivant = Mock()
        app = SimpleNamespace(_preparations_reset=[premier, suivant])
        with self.assertRaisesRegex(ValueError, 'service refuse'):
            app_module.AsyDec.preparer_reset(app)
        suivant.assert_not_called()

    def test_minuteur_non_recree_apres_fermeture(self):
        app = SimpleNamespace(_minuteur_session='ancien', reglages={'verrouillage_minutes': 1},
                              session_verrouillee=False, derniere_activite=0, _fermeture=False, after=Mock())
        def fermer():
            app._fermeture = True
        app.verrouiller = Mock(side_effect=fermer)
        with patch.object(app_module.time, 'monotonic', return_value=61):
            app_module.AsyDec._surveiller_session(app)
        app.verrouiller.assert_called_once()
        app.after.assert_not_called()

    def test_fermeture_idempotente(self):
        app = SimpleNamespace(_fermeture=False, _minuteur_session='session', after_cancel=Mock(), destroy=Mock())
        app_module.AsyDec.fermer_sans_preferences(app)
        app_module.AsyDec.fermer_sans_preferences(app)
        app.after_cancel.assert_called_once_with('session')
        app.destroy.assert_called_once()
