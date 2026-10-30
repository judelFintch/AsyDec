"""Gestion dynamique des articles : choix par position tarifaire ou nom, retrait et ajout de lignes."""
import copy
from decimal import Decimal
import tempfile
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from asydec import chemins
from asydec.calcul import articles as A
from asydec.calcul import moteur, variantes
from asydec.declarations import generer
from asydec.ui.articles_dynamiques import PanneauArticles
from asydec.ui.etapes import PageArticles
from tests import test_modeles_dynamiques as fixtures

COUVRE_LITS = ('63041900', 'autres couvre-lits')


def ddi(item):
    return next(t for t in item.findall('Taxation/Taxation_line') if moteur._txt(t, 'Duty_tax_code') == 'DDI')


class CatalogueCompositionTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ModelesDynamiquesTest(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.racine = self.fixture.fixture.racine
        self.base = self.fixture.source(8)
        # Un autre dossier porte, en ligne 2, un article absent du dossier avec son propre DDI (20 %).
        self.autre = self.racine / 'autre.xml'
        arbre = moteur.charger(self.base)
        item = moteur.articles(arbre.getroot())[1]
        item.find('Tarification/HScode/Commodity_code').text = COUVRE_LITS[0]
        item.find('Goods_description/Description_of_goods').text = 'Autres Couvre-lits'
        ddi(item).find('Duty_tax_rate').text = '20'
        moteur.recalculer(arbre, [(150, 100), (25, 100)] + [(150, 100)] * 6, list(range(10, 18)))
        arbre.write(self.autre)
        self.catalogue = A.construire_catalogue([self.base, self.autre])
        self.dossier = A.articles_du_xml(self.base)
        self.compositions = self.racine / 'compositions'

    def composer(self, cles):
        return A.composer(self.base, cles, self.catalogue, self.compositions)

    def test_catalogue_reunit_les_informations_de_chaque_article(self):
        self.assertEqual(len(self.catalogue), 9)
        entree = self.catalogue[COUVRE_LITS]
        self.assertEqual((entree['ratio'], entree['taxes']['DDI'], entree['positions']), (0.25, 20.0, {1}))
        self.assertFalse(entree['ajustable'])
        ajustables = {e['code'] for e in self.catalogue.values() if e['ajustable']}
        self.assertEqual(ajustables, {self.dossier[k][0] for k in moteur.ARTICLES_VARIABLES})
        self.assertIn('DDI 20 %', A.resume(entree))

    def test_recherche_par_position_tarifaire_ou_par_nom(self):
        for texte in ('6304', '6304 19', 'COUVRE lits', 'couvré-lits'):
            with self.subTest(texte=texte):
                self.assertEqual([e['cle'] for e in A.rechercher(self.catalogue, texte)], [COUVRE_LITS])
        self.assertEqual(len(A.rechercher(self.catalogue, '')), 9)
        self.assertEqual(len(A.rechercher(self.catalogue, 'Marchandise')), 8)

    def test_remplacement_reprend_l_article_et_garde_le_dossier(self):
        original = self.base.read_bytes()
        cles = self.dossier[:1] + [COUVRE_LITS] + self.dossier[2:]
        chemin = Path(self.composer(cles))
        self.assertEqual(chemin.parent, self.compositions)
        self.assertEqual(self.base.read_bytes(), original)
        item = moteur.articles(moteur.charger(chemin).getroot())[1]
        self.assertEqual(A.cle_item(item), COUVRE_LITS)
        self.assertEqual(moteur._txt(ddi(item), 'Duty_tax_rate'), '20')
        self.assertEqual(moteur._txt(item, 'Tarification/Item_price'), '25')  # 100 kg x ratio 0,25
        self.assertEqual(self.composer(cles), str(chemin))
        self.assertEqual(self.composer(self.dossier), str(self.base))

    def test_retrait_et_ajout_de_lignes(self):
        cinq = [self.dossier[k] for k in (0, 1, 3, 6, 7)]
        chemin = self.composer(cinq)
        self.assertEqual(A.articles_du_xml(chemin), cinq)
        neuf = self.dossier + [COUVRE_LITS]
        self.assertEqual(A.articles_du_xml(self.composer(neuf)), neuf)
        # Un article du dossier garde sa ligne, même déplacé.
        ordre = list(reversed(self.dossier))
        items = moteur.articles(moteur.charger(self.composer(ordre)).getroot())
        self.assertEqual(moteur._txt(items[0], 'Packages/Number_of_packages'), '17')

    def test_choix_incoherents_refuses(self):
        for cles, motif in (([], 'au moins un article'),
                            ([self.dossier[0]] * 2 + self.dossier[2:], 'une ligne'),
                            (self.dossier[:1] + [('0000', 'inconnu')] + self.dossier[2:], 'absent du catalogue'),
                            ([self.dossier[k] for k in (0, 1, 2)], 'ajustable')):
            with self.subTest(motif=motif), self.assertRaisesRegex(ValueError, motif):
                self.composer(cles)
        self.assertFalse(self.compositions.exists())

    def profil(self, chemin):
        return variantes.construire_profil(chemin, [self.base, self.autre], dynamique=False, catalogue=self.catalogue)

    def test_generation_suit_l_article_choisi(self):
        chemin = self.composer(self.dossier[:1] + [COUVRE_LITS] + self.dossier[2:])
        profil = self.profil(chemin)
        self.assertEqual(variantes.articles_ajustables(profil), moteur.ARTICLES_VARIABLES)
        self.assertEqual(profil['bornes'][1], (0.25, 0.25))
        poids = [100] * 8
        fob = variantes.fob_controles(poids, profil, 1075)
        self.assertEqual(fob[1], 25)
        with patch.object(generer, 'DEC', str(self.racine / 'exports')):
            resultat = generer.produire(chemin, poids, profil['ratios'], [], {}, mode='SAISI', fob_saisis=fob,
                                        fob_total=1075, colis_saisis=list(range(10, 18)), colis_total=108,
                                        profil=profil)
        item = moteur.articles(moteur.charger(resultat['chemin']).getroot())[1]
        self.assertEqual(moteur._txt(item, 'Tarification/HScode/Commodity_code'), COUVRE_LITS[0])
        cif = int(moteur._txt(item, 'Valuation_item/Total_CIF_itm'))
        self.assertEqual(int(moteur._txt(ddi(item), 'Duty_tax_amount')), cif * 20 // 100)

    def test_modele_a_cinq_articles_meme_ratios_et_totaux(self):
        cinq = [self.dossier[k] for k in (0, 1, 3, 6, 7)]
        chemin = self.composer(cinq)
        profil = self.profil(chemin)
        self.assertFalse(profil['dynamique'])
        self.assertEqual(variantes.articles_ajustables(profil), (2, 3, 4))  # lignes 4, 7 et 8 du dossier
        propositions = variantes.generer(1000, 1500, 100, profil['ratios'], profil=profil, nombre=3, graine=4)
        for v in propositions:
            self.assertEqual((len(v['poids']), sum(v['poids']), sum(v['colis'])), (5, 1000, 100))
            self.assertEqual(round(sum(v['fob']), 2), 1500)
            for k in (0, 1):  # articles bornés : ratio du dossier conservé
                self.assertEqual(Decimal(str(v['fob'][k])),
                                 (Decimal(v['poids'][k]) * Decimal('1.5')).quantize(Decimal('.01')))


class DiversDynamiqueTest(unittest.TestCase):
    """Divers : aucun lien avec les 8 articles, chaque article garde son ratio."""

    def setUp(self):
        self.fixture = fixtures.ModelesDynamiquesTest(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.racine = self.fixture.fixture.racine
        self.trois = self.racine / 'trois.xml'
        self.trois.write_bytes(self.fixture.source(3).read_bytes())
        # Un XML à 5 articles dont les positions sont autres, au ratio 3.
        cinq = self.fixture.source(5)
        arbre = moteur.charger(cinq)
        for k, item in enumerate(moteur.articles(arbre.getroot())):
            item.find('Tarification/HScode/Commodity_code').text = f'8471{k:04d}'
            item.find('Goods_description/Description_of_goods').text = f'Ordinateur {k+1}'
        moteur.recalculer(arbre, [(300, 100)] * 5, list(range(10, 15)))
        self.cinq = self.racine / 'cinq.xml'
        arbre.write(self.cinq)
        self.catalogue = A.construire_catalogue([self.trois, self.cinq], nombre=None)

    def test_catalogue_de_tous_les_xml_sans_role_ajustable(self):
        self.assertEqual(len(self.catalogue), 8)
        self.assertFalse(any(e['ajustable'] for e in self.catalogue.values()))
        self.assertEqual(A.construire_catalogue([self.trois, self.cinq]), {})  # friperie : 8 articles exigés

    def test_composition_libre_et_generation_aux_ratios_de_chaque_article(self):
        ordinateurs = [e['cle'] for e in A.rechercher(self.catalogue, '8471')]
        cles = A.articles_du_xml(self.trois)[:1] + ordinateurs[:3]
        with self.assertRaisesRegex(ValueError, 'ajustable'):
            A.composer(self.trois, cles, self.catalogue, self.racine / 'compositions')
        chemin = A.composer(self.trois, cles, self.catalogue, self.racine / 'compositions', exiger_ajustable=False)
        self.assertEqual(A.articles_du_xml(chemin), cles)
        profil = variantes.construire_profil(chemin, [], dynamique=True, catalogue=self.catalogue)
        self.assertEqual(profil['ratios'], [1.5, 3, 3, 3])
        self.assertEqual(variantes.articles_ajustables(profil), ())
        v = variantes.generer(400, 1050, 46, profil['ratios'], profil=profil, nombre=1, graine=3)[0]
        self.assertEqual((sum(v['poids']), round(sum(v['fob']), 2), sum(v['colis'])), (400, 1050, 46))
        for p, f, ratio in zip(v['poids'], v['fob'], profil['ratios']):
            self.assertEqual(Decimal(str(f)), (Decimal(p) * Decimal(str(ratio))).quantize(Decimal('.01')))

    def test_section_disponible_en_divers_quel_que_soit_le_nombre(self):
        racine = tk.Tk()
        racine.withdraw()
        self.addCleanup(racine.destroy)
        app = SimpleNamespace(base_dossier=self.trois, module_travail='divers', catalogue_articles=lambda: self.catalogue,
                              profil=variantes.construire_profil(self.trois, [], dynamique=True))
        panneau = PanneauArticles(racine, app, Mock())
        panneau.preparer()
        self.assertTrue(panneau.disponible())
        app.module_travail = 'friperie'
        self.assertFalse(panneau.disponible())


@unittest.skipUnless(list(chemins.MODELES_XML.glob('*.xml')), 'aucun modèle XML local')
class DonneesReellesTest(unittest.TestCase):
    """Lecture seule des modèles locaux."""

    def setUp(self):
        self.modeles = sorted(chemins.MODELES_XML.glob('*.xml'))
        self.catalogue = A.construire_catalogue(self.modeles)
        self.base = self.modeles[0]
        self.original = self.base.read_bytes()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def tearDown(self):
        self.assertEqual(self.base.read_bytes(), self.original)

    def test_catalogue_des_huit_articles(self):
        self.assertEqual(len(self.catalogue), 8)
        self.assertEqual({e['code'] for e in self.catalogue.values() if e['ajustable']},
                         {'63042000', '95079010', '73239100'})

    def test_permutation_emporte_les_taxes(self):
        cles = A.articles_du_xml(self.base)
        cles[4], cles[5] = cles[5], cles[4]
        item = moteur.articles(moteur.charger(A.composer(self.base, cles, self.catalogue, self.temp.name)).getroot())[4]
        self.assertEqual(A.cle_item(item), cles[4])
        self.assertEqual(Decimal(moteur._txt(ddi(item), 'Duty_tax_rate')),
                         Decimal(str(self.catalogue[cles[4]]['taxes']['DDI'])))

    def test_modele_a_cinq_articles_du_dossier(self):
        cles = [A.articles_du_xml(self.base)[k] for k in (0, 1, 3, 6, 7)]
        chemin = A.composer(self.base, cles, self.catalogue, self.temp.name)
        racine = moteur.charger(chemin).getroot()
        self.assertEqual(moteur._txt(racine, 'Property/Nbers/Total_number_of_items'), '5')
        profil = variantes.construire_profil(chemin, self.modeles, dynamique=False, catalogue=self.catalogue)
        info = moteur.infos_dossier(racine)
        v = variantes.generer(int(info['poids']), info['fob'], info['colis'], profil['ratios'],
                              profil=profil, nombre=1, graine=1)[0]
        self.assertEqual((len(v['poids']), sum(v['poids']), round(sum(v['fob']), 2)),
                         (5, int(info['poids']), info['fob']))


class InterfaceTest(unittest.TestCase):
    def setUp(self):
        self.cas = CatalogueCompositionTest(methodName='test_catalogue_reunit_les_informations_de_chaque_article')
        self.cas.setUp()
        self.addCleanup(self.cas.doCleanups)
        self.racine = tk.Tk()
        self.racine.withdraw()
        self.addCleanup(self.racine.destroy)

    def app(self):
        cas = self.cas
        app = SimpleNamespace(base_dossier=cas.base, session_verrouillee=False, table_imp=[], montrer=Mock(),
                              catalogue_articles=lambda: cas.catalogue)

        def composer(cles):
            chemin = cas.composer(cles)
            app.info = moteur.infos_dossier(moteur.charger(chemin).getroot())
            app.base, app.profil = chemin, cas.profil(chemin)
            return True
        app.composer_articles = Mock(side_effect=composer)
        app.base, app.profil = cas.base, variantes.construire_profil(cas.base, [])
        app.info = moteur.infos_dossier(moteur.charger(cas.base).getroot())
        return app

    def page(self):
        app = self.app()
        with patch.object(generer, 'DEC', str(self.cas.racine / 'exports')):
            page = PageArticles(self.racine, app)
            page.nouvelle_base()
        return app, page

    def test_edition_dans_le_tableau(self):
        app, page = self.page()
        panneau = page.panneau
        self.assertFalse(panneau.choix[0].winfo_ismapped() or panneau.edition)
        panneau.basculer_edition()
        self.assertTrue(panneau.edition)
        self.assertIn('Marchandise 2', panneau.choix[1].get())
        panneau.choix[1].set('630419')
        panneau.filtrer(panneau.choix[1], SimpleNamespace(keysym='9'))
        self.assertEqual(list(panneau.choix[1]['values']), [A.libelle(self.cas.catalogue[COUVRE_LITS])])
        panneau.choisir(1, saisie=True)
        self.assertEqual(app.composer_articles.call_args.args[0][1], COUVRE_LITS)
        self.assertIn('63041900', page.noms[1].cget('text'))
        self.assertEqual(panneau.bouton_dossier.winfo_manager(), 'pack')  # « Revenir aux articles du dossier »
        panneau.basculer_edition()
        self.assertIn('composition modifiée', panneau.var_etat.get())

    def test_retrait_conserve_les_saisies_de_chaque_article(self):
        app, page = self.page()
        for k, e in enumerate(page.e_poids):
            e.insert(0, str(100 + k))
        page.panneau.edition = True
        page.panneau.retirer(2)
        self.assertEqual(len(page.e_poids), 7)
        self.assertEqual([e.get() for e in page.e_poids], ['100', '101', '103', '104', '105', '106', '107'])
        self.assertEqual(len(page.panneau.choix), 7)
        page.panneau.ajout.set(A.libelle(self.cas.catalogue[COUVRE_LITS]))
        page.panneau.ajouter()
        self.assertEqual(len(page.e_poids), 8)
        self.assertEqual(page.e_poids[-1].get(), '')
        self.assertIn('63041900', page.noms[-1].cget('text'))
        page.panneau.revenir_au_dossier()
        self.assertEqual([e.get() for e in page.e_poids][:2], ['100', '101'])
        self.assertEqual(page.e_poids[2].get(), '')  # ligne retirée puis remise : vide

    def test_refus_garde_la_composition(self):
        app, page = self.page()
        app.composer_articles = Mock(return_value=False)
        page.panneau.edition = True
        page.panneau.retirer(0)
        self.assertEqual(len(page.e_poids), 8)

    def test_indisponible_hors_friperie_a_huit_articles(self):
        app, page = self.page()
        app.profil = dict(app.profil, dynamique=True)
        page.panneau.preparer()
        self.assertEqual(str(page.panneau.bouton_edition.cget('state')), 'disabled')


if __name__ == '__main__':
    unittest.main()
