"""Note de 1 à 5 sur les modèles générés : enregistrement, historique et effet sur les générations suivantes."""
from types import SimpleNamespace
import unittest

from asydec.calcul import anomalies as A
from asydec.declarations import modeles_generes as M
from asydec.ui.notation import etoiles
from tests import test_modeles_generes as TM


class NotationTest(unittest.TestCase):
    def setUp(self):
        TM.ModelesGeneresTest.setUp(self)
        self.identifiant = M.enregistrer(self.resultat, self.source, 'alice', base=self.base)

    def test_note_validee_derniere_fait_foi_et_tracee(self):
        for invalide in (0, 6, 2.5, '4', True, None):
            self.assertRaises(ValueError, M.noter, self.identifiant, invalide, 'alice', base=self.base)
        self.assertRaises(ValueError, M.noter, 999, 3, 'alice', base=self.base)
        self.assertIsNone(M.detail(self.identifiant, base=self.base)['note'])
        M.noter(self.identifiant, 2, 'alice', '  ratios   trop bas ', base=self.base)
        M.noter(self.identifiant, 5, 'bob', base=self.base)
        d = M.detail(self.identifiant, base=self.base)
        self.assertEqual((d['note'], d['note_commentaire']), (5, ''))
        self.assertEqual(M.lister(base=self.base)[0]['note'], 5)
        notes = [M.resume_evenement(e) for e in d['evenements'] if e['action'] == M.NOTE]
        self.assertEqual(notes, ['Noté 2/5 (Douteux) · ratios trop bas', 'Noté 5/5 (Excellent)'])
        self.assertEqual(d['statut'], 'en_attente')  # une note ne valide rien

    def test_modele_supprime_non_notable(self):
        M.supprimer(self.identifiant, 'alice', base=self.base)
        self.assertRaisesRegex(ValueError, 'Restaurez', M.noter, self.identifiant, 4, 'alice', base=self.base)

    def test_bien_note_sert_d_exemple(self):
        signature = M._signature_modele(self.identifiant, self.base)
        self.assertEqual(M.bons_modeles(signature, base=self.base), [])
        M.noter(self.identifiant, 3, 'alice', base=self.base)
        self.assertEqual(M.bons_modeles(signature, base=self.base), [])
        M.noter(self.identifiant, 4, 'alice', base=self.base)
        self.assertEqual([b['id'] for b in M.bons_modeles(signature, base=self.base)], [self.identifiant])

    def test_note_transmise_a_l_analyse(self):
        M.noter(self.identifiant, 1, 'alice', 'colis faux', base=self.base)
        donnees = {m['id']: m for m in M.donnees_analyse(base=self.base)}
        self.assertEqual((donnees[self.identifiant]['note'], donnees[self.identifiant]['note_commentaire']),
                         (1, 'colis faux'))

    def test_etoiles(self):
        self.assertEqual(etoiles(4), '★★★★☆')
        self.assertEqual(etoiles(None), '—')


class MalNoteEviteTest(unittest.TestCase):
    G = ('USD', '6309', 'friperie')

    def modele(self, identifiant, poids=100, note=None, commentaire=''):
        return {'id': identifiant, 'statut': 'en_attente', 'ecart_comparaison_pct': None, 'note': note,
                'note_commentaire': commentaire,
                'articles': [{'position': 1, 'code': '6309', 'groupe': self.G, 'poids': poids, 'fob': poids, 'colis': 10},
                             {'position': 2, 'code': '6309', 'groupe': ('USD', '6304', 'x'), 'poids': 50, 'fob': 10, 'colis': 12}]}

    def test_proche_d_un_modele_mal_note_signale(self):
        proposition = self.modele(None, poids=101)
        for note, attendu in ((1, 'moyen'), (2, 'moyen'), (3, None), (None, None)):
            alertes = A.analyser(proposition, {}, [self.modele(7, note=note, commentaire='poids douteux')])
            self.assertEqual(A.niveau(alertes), attendu, note)
        messages = [a['message'] for a in A.analyser(proposition, {}, [self.modele(7, note=2, commentaire='poids douteux')])]
        self.assertTrue(any('n° 7, que vous avez noté 2/5 (poids douteux)' in m for m in messages))
        loin = self.modele(None, poids=400)
        self.assertIsNone(A.niveau(A.analyser(loin, {}, [self.modele(7, note=1)])))


if __name__ == '__main__':
    unittest.main()
