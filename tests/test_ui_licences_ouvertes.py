"""Parcours liste → formulaire → validation → liste, sans écran natif."""
from types import SimpleNamespace
import sqlite3
import unittest
from unittest.mock import Mock, patch

from asydec.ui.documents_finaux import PageDocumentsFinaux


class ParcoursLicencesTest(unittest.TestCase):
    def page(self):
        return SimpleNamespace(app=SimpleNamespace(session_verrouillee=False), import_en_cours=False,
                               a_verifier=False, confirme=Mock(), licence=None, modifie=True,
                               _preparer_licence=Mock(return_value={'numero_validation': 'DEC123-ADD0-IB'}),
                               _afficher_liste=Mock(), message=Mock(), carnet=Mock())

    def test_validation_enregistre_avant_retour_et_selectionne_la_licence(self):
        page = self.page()
        with patch('asydec.ui.documents_finaux.licences_ouvertes.enregistrer') as sauvegarder:
            PageDocumentsFinaux.valider(page)
        sauvegarder.assert_called_once_with(page.licence)
        self.assertFalse(page.modifie)
        self.assertEqual(page._afficher_liste.call_args.kwargs['selection'], 'DEC123-ADD0-IB')
        self.assertIn('enregistrée', page._afficher_liste.call_args.kwargs['notification'])

    def test_echec_sauvegarde_reste_dans_le_formulaire(self):
        page = self.page()
        with patch('asydec.ui.documents_finaux.licences_ouvertes.enregistrer', side_effect=sqlite3.OperationalError('disque indisponible')):
            PageDocumentsFinaux.valider(page)
        page._afficher_liste.assert_not_called()
        self.assertTrue(page.modifie)
        page.message.afficher.assert_called_once_with('erreur', 'disque indisponible')

    def test_retour_annule_conserve_le_formulaire(self):
        page = self.page()
        page._peut_remplacer = Mock(return_value=False)
        PageDocumentsFinaux.voir_licences(page)
        page._afficher_liste.assert_not_called()
        self.assertTrue(page.modifie)

    def test_entree_module_affiche_liste(self):
        page = self.page()
        page.vue_active = 'liste'
        PageDocumentsFinaux.afficher(page)
        page._afficher_liste.assert_called_once_with()
