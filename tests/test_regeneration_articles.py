"""Étape Articles : « Générer une autre répartition » répétable, poids entiers, totaux conservés, rien d'exporté."""
import hashlib
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from asydec import chemins
from asydec.calcul import moteur
from asydec.calcul import variantes
import asydec.ui.etapes as E

BASE = next(iter(sorted(chemins.MODELES_XML.glob('*.xml'))), None)


@unittest.skipIf(BASE is None, 'aucun modèle XML local')
class RegenerationArticlesTest(unittest.TestCase):
    def setUp(self):
        self.empreinte = hashlib.sha256(BASE.read_bytes()).hexdigest()
        self.racine = tk.Tk()
        self.racine.withdraw()
        self.addCleanup(self.racine.destroy)
        info = moteur.infos_dossier(moteur.charger(str(BASE)).getroot())
        self.app = SimpleNamespace(base=str(BASE), reference=str(BASE), info=info, table_imp=[],
                                   profil=variantes.construire_profil(str(BASE)), session_verrouillee=False,
                                   page_active='articles', montrer=Mock(), plaque_saisie=lambda: '')
        # Jamais la vraie base des modèles : aucun bon modèle par défaut.
        bons = patch.object(E.PageArticles, 'bons_modeles', return_value=[])
        self.bons = bons.start()
        self.addCleanup(bons.stop)
        self.page = E.PageArticles(self.racine, self.app)
        self.page.nouvelle_base()
        self.page.reprendre_base()

    def tearDown(self):
        self.assertEqual(hashlib.sha256(BASE.read_bytes()).hexdigest(), self.empreinte)

    def test_trois_repartitions_distinctes_entieres_aux_memes_totaux(self):
        info = self.app.info
        vues = []
        with patch('asydec.ui.taux_change.confirmer', return_value=True), patch.object(E.messagebox, 'showinfo') as info_box, \
                patch.object(E.generer, 'lire_registre', return_value={}), \
                patch.object(E.moteur, 'enregistrer') as ecriture:
            for _ in range(3):
                self.page.regenerer()
                v = self.page.valeurs()
                vues.append((tuple(v['poids']), tuple(v['fob']), tuple(v['colis'])))
                self.assertTrue(all(p == int(p) for p in v['poids']))
                self.assertEqual(sum(v['poids']), info['poids'])
                self.assertAlmostEqual(sum(v['fob']), info['fob'], places=2)
                self.assertEqual(sum(v['colis']), info['colis'])
        info_box.assert_not_called()
        ecriture.assert_not_called()
        self.assertEqual(len(set(vues)), 3)
        self.assertIn('n° 3', self.page.message.titre.cget('text'))
        self.assertRegex(self.page.var_taxes.get(), r'Total taxes estimé : [\d ]+ CDF')

    def test_poids_total_decimal_refuse_sans_toucher_au_tableau(self):
        E.remplir(self.page.e_poids[0], 220.5)
        avant = self.page.valeurs()
        with patch.object(E.messagebox, 'showinfo') as info_box, patch('asydec.ui.taux_change.confirmer') as confirmer:
            self.page.regenerer()
        info_box.assert_called_once()
        confirmer.assert_not_called()
        self.assertEqual(self.page.valeurs(), avant)


@unittest.skipIf(BASE is None, 'aucun modèle XML local')
class TaxesEstimeesArticlesTest(RegenerationArticlesTest):
    test_trois_repartitions_distinctes_entieres_aux_memes_totaux = None
    test_poids_total_decimal_refuse_sans_toucher_au_tableau = None

    def test_total_identique_a_l_apercu_puis_tiret_si_incomplet(self):
        from asydec.declarations import generer
        self.page.actualiser()
        v = self.page.valeurs()
        attendu = generer.produire(str(BASE), v['poids'], self.app.profil['ratios'], [], {}, mode='SAISI',
            fob_saisis=v['fob'], colis_total=v['colis_total'], colis_saisis=v['colis'], enregistrer=False,
            profil=self.app.profil)['resume']['taxes_totales']
        self.assertIn(E.nombre(attendu) + ' CDF', self.page.var_taxes.get())
        self.assertEqual(self.page.cartes['taxes'].valeur.get(), E.nombre(attendu))
        self.assertEqual(self.page.cartes['poids'].valeur.get(), E.nombre(self.app.info['poids']))
        self.assertIn('articles', self.page.cartes['taxes'].detail.get())
        E.remplir(self.page.e_poids[0], None)
        self.page.actualiser()
        self.assertIn('—', self.page.var_taxes.get())
        self.assertEqual(self.page.cartes['taxes'].valeur.get(), '—')
        self.assertEqual(self.page.cartes['poids'].detail.get(), 'poids incomplets')

    def test_ecart_avec_la_repartition_precedente(self):
        self.page.actualiser()
        with patch('asydec.ui.taux_change.confirmer', return_value=True), patch.object(E.messagebox, 'showinfo'):
            for _ in range(4):
                avant = self.page.cartes['taxes'].valeur.get()
                self.page.regenerer()
                if self.page.cartes['taxes'].valeur.get() != avant:
                    break
        detail = self.page.cartes['taxes'].detail.get()
        self.assertRegex(detail, r'[▲▼] [\d ]+ CDF de (plus|moins) que la précédente')


@unittest.skipIf(BASE is None, 'aucun modèle XML local')
class GuideBonsModelesTest(RegenerationArticlesTest):
    test_trois_repartitions_distinctes_entieres_aux_memes_totaux = None
    test_poids_total_decimal_refuse_sans_toucher_au_tableau = None

    def test_repartition_la_plus_proche_du_bon_modele(self):
        v = self.page.valeurs()
        bon = {'id': 7, 'poids': v['poids'], 'fob': v['fob'], 'colis': v['colis']}
        self.bons.return_value = [bon]
        tirages = []
        vrai_generer = E.variantes.generer
        def generer(*args, **kwargs):
            tirages.append(kwargs)
            sortie = vrai_generer(*args, **kwargs)
            tirages[-1] = (kwargs, sortie)
            return sortie
        with patch('asydec.ui.taux_change.confirmer', return_value=True), patch.object(E.messagebox, 'showinfo') as alerte, \
                patch.object(E.variantes, 'generer', side_effect=generer):
            self.page.regenerer()
        alerte.assert_not_called()
        kwargs, propositions = tirages[0]
        self.assertEqual(kwargs['nombre'], 8)
        self.assertGreater(len(propositions), 1)
        self.assertIn('n° 7', self.page.message.lignes.cget('text'))
        retenue = self.page.valeurs()
        retenue = {'poids': retenue['poids'], 'fob': retenue['fob'], 'colis': retenue['colis']}
        # La retenue est la plus proche du bon modèle parmi tous les tirages valides.
        meilleure = min(E.variantes.distance_parts(p, bon) for p in propositions)
        self.assertAlmostEqual(E.variantes.distance_parts(retenue, bon), meilleure, places=9)


class PlaqueRegenerationTest(unittest.TestCase):
    def test_lecture_plaque_tolerante(self):
        self.assertEqual(E.plaque_saisie(SimpleNamespace()), '')
        self.assertEqual(E.plaque_saisie(SimpleNamespace(plaque_saisie=lambda: 'T1')), 'T1')


if __name__ == '__main__':
    unittest.main()
