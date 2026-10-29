"""Un modèle suit les articles et positions tarifaires du XML, sans limite à huit."""
import copy
from decimal import Decimal
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from asydec.calcul import moteur, variantes
from asydec.declarations import generer
from tests import test_modeles_generes as fixtures


class ModelesDynamiquesTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ModelesGeneresTest(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def source(self, n):
        arbre = moteur.charger(self.fixture.source)
        racine = arbre.getroot()
        prototype = copy.deepcopy(moteur.articles(racine)[0])
        for it in racine.findall('Item'):
            racine.remove(it)
        for k in range(n):
            it = copy.deepcopy(prototype)
            it.find('Tarification/HScode/Commodity_code').text = f'630{k:05d}'
            it.find('Goods_description/Description_of_goods').text = f'Marchandise {k+1}'
            racine.append(it)
        moteur.recalculer(arbre, [(150, 100)] * n, list(range(10, 10+n)))
        arbre.write(self.fixture.source)
        return self.fixture.source

    def test_generation_export_et_codes_pour_1_3_8_12_articles(self):
        for n in (1, 3, 8, 12):
            with self.subTest(n=n):
                source = self.source(n)
                original = source.read_bytes()
                profil = variantes.construire_profil(source, [], dynamique=True)
                self.assertEqual(variantes.articles_ajustables(profil), ())
                colis = sum(range(10, 10+n))
                proposition = variantes.generer(n*100, n*150.00, colis, profil['ratios'],
                                                 profil=profil, nombre=1, graine=12)[0]
                self.assertEqual(sum(proposition['poids']), n*100)
                self.assertEqual(sum(Decimal(str(f)) for f in proposition['fob']), Decimal('150.00')*n)
                self.assertEqual(sum(proposition['colis']), colis)
                with patch.object(generer, 'DEC', str(self.fixture.racine/'exports')):
                    resultat = generer.produire(source, proposition['poids'], profil['ratios'], [], {},
                        mode='SAISI', fob_saisis=proposition['fob'], colis_saisis=proposition['colis'],
                        fob_total=n*150.00, colis_total=colis, profil=profil)
                export = moteur.charger(resultat['chemin'])
                info = moteur.infos_dossier(export.getroot())
                self.assertEqual(len(info['fob_articles']), n)
                self.assertEqual(info['positions_tarifaires'], [f'630{k:05d}' for k in range(n)])
                self.assertEqual(source.read_bytes(), original)
                self.assertEqual(resultat['resume']['taxes_totales'],
                                 resultat['resume']['taxes_articles'] + resultat['resume']['taxes_globales'])

    def test_friperie_classique_huit_et_dynamique_douze(self):
        profil = variantes.construire_profil(self.source(8), [])
        self.assertFalse(profil['dynamique'])
        self.assertEqual(variantes.articles_ajustables(profil), moteur.ARTICLES_VARIABLES)
        profil = variantes.construire_profil(self.source(12), [])
        self.assertTrue(profil['dynamique'])
        self.assertEqual(variantes.articles_ajustables(profil), ())

    def test_ligne_manquante_refusee(self):
        profil = variantes.construire_profil(self.source(12), [])
        with self.assertRaises(ValueError):
            variantes.controler({'poids':[100]*11, 'fob':[150]*11, 'colis':[10]*11}, profil)

    def test_totaux_incompatibles_ne_modifient_jamais_les_ratios(self):
        for n in (3, 8, 12):
            with self.subTest(n=n):
                source = self.source(n)
                profil = variantes.construire_profil(source, [], dynamique=True)
                with self.assertRaises(ValueError):
                    variantes.generer(n*100, n*173.25, sum(range(10, 10+n)),
                                      profil['ratios'], profil=profil, nombre=1)
                with self.assertRaises(ValueError):
                    variantes.fob_controles([100]*n, profil, n*173.25)
                with self.assertRaises(ValueError):
                    generer.produire(source, [100]*n, profil['ratios'], [], {},
                        mode='SAISI', fob_saisis=[173.25]*n, colis_saisis=[10]*n,
                        enregistrer=False, profil=profil)

    def test_generation_ratios_differents_par_position(self):
        source = self.source(3)
        arbre = moteur.charger(source)
        moteur.recalculer(arbre, [(50,100), (100,100), (200,100)], [10,11,12])
        arbre.write(source)
        profil = variantes.construire_profil(source, [])
        propositions = variantes.generer(300, 350, 33, profil['ratios'],
                                          profil=profil, nombre=3, graine=12)
        self.assertTrue(propositions)
        for proposition in propositions:
            self.assertEqual(sum(proposition['poids']), 300)
            self.assertEqual(sum(proposition['fob']), 350)
            for p, f, ratio in zip(proposition['poids'], proposition['fob'], profil['ratios']):
                self.assertEqual(Decimal(str(f)), (Decimal(p)*Decimal(str(ratio))).quantize(Decimal('.01')))
