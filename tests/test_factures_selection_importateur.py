from unittest import TestCase
from asydec.declarations import factures as F


class SelectionImportateurTest(TestCase):
    def dossier(self, nom='SHABANI SUMAILI CHARLY'):
        return {'importateur': nom, 'resultat': {'resume': {'articles': [{}]},
                                               'info': {'designations': ['USED CLOTHINGS']}}}

    def gabarit(self, identifiant, nom, **kw):
        return dict(id=identifiant, nom=str(identifiant), destinataire=nom,
                    articles=kw.pop('articles', ['USED CLOTHINGS']),
                    plaque_prevue=True, pret=kw.pop('pret', True), **kw)

    def test_client_du_dossier_prioritaire_et_selectionne(self):
        dossier = self.dossier()
        modeles = F.classer_gabarits([self.gabarit(1, 'ETS JAQ'),
                                     self.gabarit(2, 'SHABANI SUMAILI CHARLY')], dossier)
        self.assertEqual(modeles[0]['id'], 2)
        self.assertEqual(F.selection_par_defaut(modeles, dossier), 0)

    def test_aucun_modele_du_client_aucune_selection(self):
        modeles = [self.gabarit(1, 'ETS ALPHA'), self.gabarit(2, 'STE KD META')]
        self.assertIsNone(F.selection_par_defaut(modeles, self.dossier()))
        self.assertIsNone(F.selection_par_defaut([], self.dossier()))

    def test_selection_etrangere_non_conservee(self):
        modeles = [self.gabarit(1, 'STE KD META'), self.gabarit(2, 'SHABANI SUMAILI CHARLY')]
        self.assertEqual(F.selection_par_defaut(modeles, self.dossier(), 1), 1)
        self.assertIsNone(F.selection_par_defaut(modeles, self.dossier('AUTRE'), 2))

    def test_selection_manuelle_du_meme_client_conservee(self):
        modeles = [self.gabarit(1, 'ETS ALPHA'), self.gabarit(2, 'ALPHA')]
        self.assertEqual(F.selection_par_defaut(modeles, self.dossier('ETS ALPHA'), 2), 1)

    def test_exception_jaq_shabani_selection_et_recommandation(self):
        for nom in ('ETS JAQ', 'ETS JACQ', 'CHABANI', 'CHABANI SUMAILI CHARLY'):
            modeles = F.classer_gabarits([self.gabarit(1, 'STE KD META'), self.gabarit(2, nom)], self.dossier())
            self.assertTrue(F.correspond_importateur(modeles[0], self.dossier()))
            self.assertEqual(modeles[0]['id'], 2)
            self.assertTrue(modeles[0]['propose'])
            self.assertNotIn('destinataire différent', modeles[0]['raison'])
            self.assertEqual(F.selection_par_defaut(modeles, self.dossier()), 0)
        self.assertTrue(F.correspond_importateur(self.gabarit(1, 'SHABANI SUMAILI CHARLY'), self.dossier('ETS JAQ')))
        self.assertFalse(F.correspond_importateur(self.gabarit(1, 'ETS JAQ AUTRE'), self.dossier()))

    def test_articles_incompatibles_ou_modele_incomplet_non_selectionnes(self):
        modeles = [self.gabarit(1, 'SHABANI SUMAILI CHARLY', articles=['A', 'B']),
                   self.gabarit(2, 'SHABANI SUMAILI CHARLY', pret=False)]
        self.assertIsNone(F.selection_par_defaut(modeles, self.dossier()))

    def test_destinataire_dynamique_et_normalisation(self):
        self.assertTrue(F.correspond_importateur(self.gabarit(1, '{{IMPORTATEUR}}'), self.dossier()))
        self.assertTrue(F.correspond_importateur(self.gabarit(1, ' ÉTS  Alpha '), self.dossier('ALPHA')))
        self.assertFalse(F.correspond_importateur(self.gabarit(1, ''), self.dossier()))
