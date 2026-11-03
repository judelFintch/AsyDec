"""Retrait de modèles de facture de la bibliothèque : plus proposés, factures émises conservées."""
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch

from asydec.declarations import factures as F
from tests.test_factures import document


class RetraitTest(TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dossier = Path(temp.name)
        self.base = self.dossier / 'factures.db'
        self.modele = {'supprime': False, 'importateur': 'A', 'plaque': 'ABC123',
                       'resultat': {'resume': {'poids': 100, 'fob': 50}, 'colis': [10]}}
        self.gabarits = []
        for nom, texte in (('premier', 'Facture A'), ('second', 'Facture B'), ('troisieme', 'Facture C')):
            chemin = self.dossier / f'{nom}.docx'
            chemin.write_bytes(document(f'<w:r><w:t>{texte} {{{{NUMERO_FACTURE}}}} {{{{POIDS}}}} {{{{COLIS}}}} {{{{FOB}}}}</w:t></w:r>'))
            self.gabarits.append((chemin, F.importer(chemin, self.base)))

    def ids(self):
        return sorted(m['id'] for m in F.lister_modeles(self.base))

    def test_retirer_plusieurs_modeles(self):
        (_, a), (_, b), (_, c) = self.gabarits
        self.assertEqual(F.retirer_modeles([a, c], self.base), 2)
        self.assertEqual(self.ids(), [b])
        self.assertEqual(F.retirer_modeles([a], self.base), 0)  # déjà retiré : sans effet
        self.assertRaisesRegex(ValueError, 'introuvable : 999', F.retirer_modeles, [b, 999], self.base)
        self.assertEqual(self.ids(), [b])  # rien retiré si un identifiant est inconnu

    def test_factures_emises_conservees_et_modele_retire_refuse(self):
        _, a = self.gabarits[0]
        with patch('asydec.declarations.modeles_generes.detail', return_value=self.modele):
            facture = F.generer(42, a, 'test', self.base)
        self.assertEqual(F.factures_emises([a, self.gabarits[1][1]], self.base), {a: 1, self.gabarits[1][1]: 0})
        F.retirer_modeles([a], self.base)
        self.assertEqual(F.lire(facture['id'], self.base)['contenu'], facture['contenu'])
        self.assertEqual(len(F.lister_factures(42, self.base)), 1)
        with patch('asydec.declarations.modeles_generes.detail', return_value=self.modele):
            self.assertRaisesRegex(ValueError, 'retiré', F.generer, 43, a, 'test', self.base)

    def test_recharger_le_meme_word_le_remet_en_service(self):
        chemin, a = self.gabarits[0]
        F.retirer_modeles([a], self.base)
        self.assertNotIn(a, self.ids())
        self.assertEqual(F.importer(chemin, self.base), a)
        self.assertIn(a, self.ids())


class PageRetraitTest(TestCase):
    def test_selection_multiple_et_confirmation(self):
        from asydec.ui import factures as U
        racine = tk.Tk()
        racine.withdraw()
        self.addCleanup(racine.destroy)
        modeles = [dict(id=i, nom=f'modèle {i}', pret=True, articles=[], plaque_prevue=True, champs=[],
                        fournisseur='', destinataire='') for i in (3, 2, 1)]
        with patch.object(U.factures, 'lister_modeles', return_value=modeles):
            page = U.PageBibliothequeFactures(racine, SimpleNamespace(session_verrouillee=False))
            page.afficher()
        page.liste.selection_set(0)
        page.liste.selection_set(2)
        with patch.object(U.factures, 'factures_emises', return_value={3: 2, 1: 0}), \
                patch.object(U.factures, 'retirer_modeles') as retrait, \
                patch.object(U.factures, 'lister_modeles', return_value=modeles[1:2]), \
                patch.object(U, 'messagebox') as boites:
            boites.askyesno.return_value = True
            page.retirer()
        retrait.assert_called_once_with([3, 1])
        self.assertIn('2 facture(s) déjà émise(s)', boites.askyesno.call_args[0][1])
        self.assertEqual(page.liste.size(), 1)

    def test_annulation_ne_retire_rien(self):
        from asydec.ui import factures as U
        with patch.object(U.factures, 'factures_emises', return_value={1: 0}), \
                patch.object(U.factures, 'retirer_modeles') as retrait, patch.object(U, 'messagebox') as boites:
            boites.askyesno.return_value = False
            self.assertFalse(U.retirer(None, [{'id': 1, 'nom': 'modèle'}]))
        retrait.assert_not_called()


if __name__ == '__main__':
    main()
