"""Modèles de référence déjà utilisés : détection depuis les modèles générés et signalement manuel."""
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from asydec.declarations import modeles_generes as M
from asydec.ui import outils as O
from tests.test_modeles_generes import ModelesGeneresTest


class UsagesReferencesTest(unittest.TestCase):
    setUp = ModelesGeneresTest.setUp

    def reference(self, nom='reference.xml'):
        chemin = self.racine / nom
        chemin.write_bytes(self.source.read_bytes() + b'<!-- autre modele -->')
        return chemin

    def test_sans_reference_rattache_au_xml_du_dossier(self):
        identifiant = M.enregistrer(self.resultat, self.source, 'alice', base=self.base)
        usages = M.usages_references(base=self.base)
        self.assertEqual(usages[M.empreinte_fichier(self.source)]['modeles'], [identifiant])

    def test_reference_memorisee_par_son_contenu(self):
        reference = self.reference()
        identifiant = M.enregistrer(self.resultat, self.source, 'alice', base=self.base, reference=reference)
        usages = M.usages_references(base=self.base)
        self.assertEqual(set(usages), {M.empreinte_fichier(reference)})
        self.assertEqual(usages[M.empreinte_fichier(reference)]['modeles'], [identifiant])
        # Renommé ou copié ailleurs, le même contenu reste reconnu.
        copie = self.racine / 'copie renommee.xml'
        copie.write_bytes(reference.read_bytes())
        self.assertIn(M.empreinte_fichier(copie), usages)

    def test_modele_supprime_ne_compte_plus(self):
        identifiant = M.enregistrer(self.resultat, self.source, 'alice', base=self.base)
        M.supprimer(identifiant, 'alice', base=self.base)
        self.assertEqual(M.usages_references(base=self.base), {})

    def test_signalement_historise_sans_doublon(self):
        reference = self.reference()
        M.signaler_reference(reference, 'alice', base=self.base)
        M.signaler_reference(reference, 'alice', base=self.base)
        usage = M.usages_references(base=self.base)[M.empreinte_fichier(reference)]
        self.assertEqual((usage['modeles'], usage['signale']['auteur']), ([], 'alice'))
        M.signaler_reference(reference, 'bob', utilise=False, base=self.base)
        self.assertEqual(M.usages_references(base=self.base), {})
        conn = sqlite3.connect(self.base)
        self.addCleanup(conn.close)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM signalements_references').fetchone()[0], 2)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute('DELETE FROM signalements_references')

    def test_signalement_exige_une_session(self):
        with self.assertRaises(ValueError):
            M.signaler_reference(self.reference(), ' ', base=self.base)


class PageRepartitionsUsagesTest(unittest.TestCase):
    def test_texte_usage(self):
        self.assertEqual(O.texte_usage(None), '—')
        usage = {'modeles': [3, 4], 'dernier_utc': '2026-10-27T10:00:00+00:00', 'signale': {'auteur': 'alice'}}
        self.assertRegex(O.texte_usage(usage), r'^2 modèle\(s\) généré\(s\), dernier \d\d/\d\d/2026 · signalé$')
        self.assertEqual(O.texte_usage({'modeles': [], 'dernier_utc': None, 'signale': {'auteur': 'a'}}), 'signalé')

    def page(self, usages):
        v = {'controle': '/x/modele.xml', 'modele': 'modele.xml', 'empreinte': 'abc'}
        return SimpleNamespace(app=SimpleNamespace(session_verrouillee=False, utilisateur='alice'), usages=usages,
                               selection=lambda: v, _lire_usages=Mock(), _remplir_liste=Mock(), detailler=Mock(),
                               message=Mock())

    def test_bouton_signale_puis_retire(self):
        for usages, attendu in (({}, True), ({'abc': {'modeles': [], 'signale': {'auteur': 'a'}}}, False)):
            page = self.page(usages)
            with patch.object(O.modeles_generes, 'signaler_reference') as signaler:
                O.PageRepartitions.basculer_signalement(page)
            signaler.assert_called_once_with('/x/modele.xml', 'alice', utilise=attendu)
            page._remplir_liste.assert_called_once()

    def test_session_verrouillee_ne_signale_rien(self):
        page = self.page({})
        page.app.session_verrouillee = True
        with patch.object(O.modeles_generes, 'signaler_reference') as signaler:
            O.PageRepartitions.basculer_signalement(page)
        signaler.assert_not_called()


if __name__ == '__main__':
    unittest.main()
