"""Plaque à inscrire : un seul champ partagé par les pages, lu sans créer de fenêtre."""
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import Mock

from asydec.ui import plaque


class PlaquePartageeTest(unittest.TestCase):
    def test_sans_champ_plaque_du_xml(self):
        app = SimpleNamespace(info={'camion': 'ABC123'})
        self.assertEqual(plaque.lire(app), '')
        plaque.remettre(app, 'X')  # sans champ : rien à rétablir, aucune erreur
        self.assertFalse(hasattr(app, 'var_plaque'))
        self.assertEqual(plaque.texte_plaque(app), 'ABC123')
        self.assertEqual(plaque.texte_plaque(SimpleNamespace()), '—')

    def test_une_variable_pour_toutes_les_pages_et_bandeau_actualise(self):
        racine = tk.Tk()
        racine.withdraw()
        self.addCleanup(racine.destroy)
        app = SimpleNamespace(info={'camion': 'ABC123'}, afficher_bandeau=Mock())
        cadre1, cadre2 = tk.Frame(racine), tk.Frame(racine)
        champ1, champ2 = plaque.selecteur(cadre1, app), plaque.selecteur(cadre2, app, aide=False)
        self.assertIs(plaque.variable(app), app.var_plaque)
        champ1.insert(0, 't546ecq / t618ect')
        self.assertEqual(champ2.get(), 't546ecq / t618ect')
        app.afficher_bandeau.assert_called()
        self.assertEqual(plaque.texte_plaque(app), 'T546ECQ / T618ECT (saisie)')
        app.var_plaque.set('plaque#?')
        self.assertEqual(plaque.texte_plaque(app), 'plaque#? (invalide)')

    def test_validation_appelle_la_mise_a_jour(self):
        racine = tk.Tk()
        racine.withdraw()
        self.addCleanup(racine.destroy)
        apres = Mock()
        champ = plaque.selecteur(racine, SimpleNamespace(), apres=apres)
        self.assertTrue(champ.bind('<Return>') and champ.bind('<FocusOut>'))
        self.assertFalse(plaque.selecteur(racine, SimpleNamespace()).bind('<Return>'))


if __name__ == '__main__':
    unittest.main()
