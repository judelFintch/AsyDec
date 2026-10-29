"""Suppression d'un modèle : retrait de la liste réversible, sans effacement, sur données temporaires."""
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from asydec.declarations import modeles_generes as M
from tests import test_modeles_generes as TM

import asydec.ui.modeles_generes as U


class SuppressionModeleTest(unittest.TestCase):
    def setUp(self):
        TM.ModelesGeneresTest.setUp(self)
        self.export = self.racine / 'export.xml'
        self.export.write_bytes(self.xml)
        self.identifiant = M.enregistrer(self.resultat, self.source, 'alice', export=self.export, base=self.base)

    def comptes(self):
        conn = sqlite3.connect(self.base)
        return [conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('modeles', 'exports_xml')]

    def test_supprimer_masque_sans_effacer_puis_restaurer(self):
        M.changer_statut(self.identifiant, 'valide', 'alice', base=self.base)
        avant = self.comptes()
        M.supprimer(self.identifiant, 'alice', 'doublon', base=self.base)
        self.assertEqual(M.lister(base=self.base), [])
        self.assertEqual(M.lister('valide', base=self.base), [])
        self.assertEqual([m['id'] for m in M.lister(base=self.base, supprimes=True)], [self.identifiant])
        d = M.detail(self.identifiant, base=self.base)
        self.assertTrue(d['supprime'])
        self.assertEqual(d['statut'], 'valide')
        self.assertEqual(self.comptes(), avant)
        self.assertEqual(M.lire_export(self.identifiant, base=self.base), self.xml)
        self.assertEqual(M.resume_evenement(d['evenements'][-1]), 'Supprimé de la liste · doublon')
        M.restaurer(self.identifiant, 'bob', base=self.base)
        self.assertEqual([m['id'] for m in M.lister(base=self.base)], [self.identifiant])
        self.assertFalse(M.detail(self.identifiant, base=self.base)['supprime'])

    def test_actions_repetees_sans_doublon_et_controles(self):
        M.supprimer(self.identifiant, 'alice', base=self.base)
        M.supprimer(self.identifiant, 'alice', base=self.base)
        M.restaurer(self.identifiant, 'alice', base=self.base)
        M.restaurer(self.identifiant, 'alice', base=self.base)
        actions = [e['action'] for e in M.detail(self.identifiant, base=self.base)['evenements']]
        self.assertEqual(actions.count('suppression'), 1)
        self.assertEqual(actions.count('restauration'), 1)
        self.assertRaises(ValueError, M.supprimer, 999, 'alice', base=self.base)
        self.assertRaises(ValueError, M.supprimer, self.identifiant, ' ', base=self.base)

    def test_effacement_physique_toujours_interdit(self):
        conn = sqlite3.connect(self.base)
        self.assertRaises(sqlite3.DatabaseError, conn.execute, 'DELETE FROM modeles')


class BonModeleTest(unittest.TestCase):
    def setUp(self):
        TM.ModelesGeneresTest.setUp(self)
        self.identifiant = M.enregistrer(self.resultat, self.source, 'alice', base=self.base)
        from asydec.calcul import moteur, variantes
        self.signature = variantes.signature_racine(moteur.charger(str(self.source)).getroot())

    def test_cocher_decocher_sans_doublon_et_historique(self):
        self.assertFalse(M.lister(base=self.base)[0]['bon'])
        M.marquer_bon(self.identifiant, 'alice', base=self.base)
        M.marquer_bon(self.identifiant, 'alice', base=self.base)
        self.assertTrue(M.lister(base=self.base)[0]['bon'])
        d = M.detail(self.identifiant, base=self.base)
        self.assertTrue(d['bon'])
        self.assertEqual(d['statut'], 'en_attente')  # la coche ne valide rien
        self.assertEqual([e['action'] for e in d['evenements']].count('bon_modele'), 1)
        self.assertEqual(M.resume_evenement(d['evenements'][-1]), 'Coché bon modèle ★')
        M.marquer_bon(self.identifiant, 'bob', False, base=self.base)
        self.assertFalse(M.detail(self.identifiant, base=self.base)['bon'])
        self.assertRaises(ValueError, M.marquer_bon, 999, 'alice', base=self.base)

    def test_bons_modeles_meme_articles_et_non_supprimes(self):
        self.assertEqual(M.bons_modeles(self.signature, base=self.base), [])
        M.marquer_bon(self.identifiant, 'alice', base=self.base)
        bons = M.bons_modeles(self.signature, base=self.base)
        self.assertEqual([b['id'] for b in bons], [self.identifiant])
        self.assertEqual(bons[0]['poids'], [a['poids'] for a in self.resultat['resume']['articles']])
        self.assertEqual(bons[0]['colis'], self.resultat['colis'])
        self.assertEqual(M.bons_modeles([('9999', 'autre', 'USD')], base=self.base), [])
        M.supprimer(self.identifiant, 'alice', base=self.base)
        self.assertEqual(M.bons_modeles(self.signature, base=self.base), [])


class ProximiteTest(unittest.TestCase):
    def test_distance_et_plus_proche(self):
        from asydec.calcul import variantes
        bon = {'id': 1, 'poids': [10, 20], 'fob': [1, 2], 'colis': [5, 5]}
        identique = {'poids': [20, 40], 'fob': [2, 4], 'colis': [10, 10]}
        loin = {'poids': [40, 20], 'fob': [4, 2], 'colis': [15, 5]}
        self.assertEqual(variantes.distance_parts(identique, bon), 0)
        self.assertGreater(variantes.distance_parts(loin, bon), 0)
        choix, modele, proximite = variantes.plus_proche([loin, identique], [bon])
        self.assertIs(choix, identique)
        self.assertEqual((modele['id'], proximite), (1, 100))


class BoutonSupprimerTest(unittest.TestCase):
    def page(self, supprime=False):
        return SimpleNamespace(selection=lambda: 3, modeles={'3': {'supprime': supprime}}, afficher=Mock(),
                               app=SimpleNamespace(session_verrouillee=False, utilisateur='alice'))

    def test_annulation_ne_supprime_pas(self):
        page = self.page()
        with patch.object(U.messagebox, 'askyesno', return_value=False), patch.object(U.service, 'supprimer') as supprimer:
            U.PageModelesGeneres.supprimer(page)
        supprimer.assert_not_called()

    def test_confirmation_avec_motif(self):
        page = self.page()
        with patch.object(U.messagebox, 'askyesno', return_value=True), \
                patch.object(U.simpledialog, 'askstring', return_value='erreur'), \
                patch.object(U.service, 'supprimer') as supprimer:
            U.PageModelesGeneres.supprimer(page)
        supprimer.assert_called_once_with(3, 'alice', 'erreur')
        page.afficher.assert_called_once()

    def test_modele_supprime_restaure_sans_question(self):
        page = self.page(supprime=True)
        with patch.object(U.messagebox, 'askyesno') as demander, patch.object(U.service, 'restaurer') as restaurer:
            U.PageModelesGeneres.supprimer(page)
        demander.assert_not_called()
        restaurer.assert_called_once_with(3, 'alice')


if __name__ == '__main__':
    unittest.main()
