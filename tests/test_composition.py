"""Nombre choisi, variantes de taxes/ratios intactes et XML original conservé."""
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from asydec.calcul import composition as C, moteur, variantes
from asydec.ui.app import AsyDec
from tests import test_modeles_dynamiques as fixtures


class CompositionTest(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ModelesDynamiquesTest(methodName='runTest')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.base=self.f.source(8)
        self.racine=self.f.fixture.racine
        self.autre=self.racine/'autre.xml'
        arbre=moteur.charger(self.base)
        item=moteur.articles(arbre.getroot())[0]
        item.find('Taxation/Taxation_line/Duty_tax_rate').text='20'
        moteur.recalculer(arbre,[(50,100)]+[(150,100)]*7,list(range(10,18)))
        arbre.write(self.autre)
        self.entrees=C.catalogue([self.base,self.autre])

    def test_variations_ne_sont_pas_fusionnees(self):
        variantes_article=[e for e in self.entrees.values() if e['code']=='63000000']
        self.assertEqual({e['ratio'] for e in variantes_article},{.5,1.5})
        self.assertEqual({e['taxes']['DDI'] for e in variantes_article},{10,20})

    def test_selection_auto_nombre_exact_et_aucun_article_en_double(self):
        for n in (1,3,8):
            choix=C.choisir_automatiquement(self.entrees,n,graine=9)
            self.assertEqual(len(choix),n)
            self.assertEqual(len({e['article'] for e in choix}),n)
        for n in (0,-1,9,1.5):
            with self.assertRaises(ValueError):
                C.choisir_automatiquement(self.entrees,n)

    def test_composition_conserve_taxes_ratios_et_dossier(self):
        original=self.base.read_bytes()
        choix=[next(e for e in self.entrees.values() if e['ratio']==.5)]
        choix += [e for e in C.choisir_automatiquement(self.entrees,8,graine=4) if e['article']!=choix[0]['article']][:2]
        chemin=C.composer(self.base,choix,3,self.racine/'compositions')
        info=moteur.infos_dossier(moteur.charger(chemin).getroot())
        self.assertEqual(len(info['fob_articles']),3)
        self.assertEqual(info['importateur'],'IMPORT A')
        self.assertEqual([f/p for f,p in zip(info['fob_articles'],info['poids_articles'])],[e['ratio'] for e in choix])
        self.assertEqual(moteur.articles(moteur.charger(chemin).getroot())[0].findtext('Taxation/Taxation_line/Duty_tax_rate'),'20')
        profil=variantes.construire_profil(chemin,[chemin],dynamique=True)
        self.assertEqual(profil['ajustables'],())
        self.assertEqual(profil['bornes'],[(e['ratio'],e['ratio']) for e in choix])
        self.assertEqual(self.base.read_bytes(),original)

    def test_mauvais_nombre_et_variantes_dupliquees_refuses(self):
        choix=list(self.entrees.values())[:3]
        with self.assertRaises(ValueError):
            C.composer(self.base,choix,2,self.racine/'compositions')
        meme=[e for e in self.entrees.values() if e['code']=='63000000']
        with self.assertRaises(ValueError):
            C.composer(self.base,meme,2,self.racine/'compositions')

    def test_application_et_retour_base_classique(self):
        page=SimpleNamespace(nouvelle_base=Mock(),reprendre_base=Mock())
        app=SimpleNamespace(session_verrouillee=False,module_travail='friperie',base_dossier=str(self.base),base=str(self.base),
            chemins_xml_disponibles=lambda generation=False:[str(self.base)],pages={'articles':page},montrer=Mock(),
            confiance_generation=lambda chemin:None)
        app.profil_generation=lambda chemin,**options:AsyDec.profil_generation(app,chemin,**options)
        with patch('asydec.ui.app.chemins.DONNEES',self.racine):
            AsyDec.appliquer_composition(app,C.choisir_automatiquement(self.entrees,3,graine=3),3)
            self.assertEqual(len(app.profil['ratios']),3)
            self.assertTrue(app.profil['composition_fixe'])
            self.assertEqual(app.profil['ajustables'],())
            AsyDec.appliquer_composition(app,None,None)
            self.assertEqual(app.base,str(self.base))
            self.assertEqual(len(app.profil['ratios']),8)
            self.assertFalse(app.profil['composition_fixe'])

    def test_dix_articles_si_le_catalogue_en_contient_assez(self):
        arbre=moteur.charger(self.autre)
        for k,item in enumerate(moteur.articles(arbre.getroot())[-2:]):
            item.find('Tarification/HScode/Commodity_code').text=f'9999000{k}'
        arbre.write(self.autre)
        entrees=C.catalogue([self.base,self.autre])
        choix=C.choisir_automatiquement(entrees,10,graine=8)
        chemin=C.composer(self.base,choix,10,self.racine/'compositions')
        self.assertEqual(len(moteur.articles(moteur.charger(chemin).getroot())),10)
        self.assertEqual(len({e['article'] for e in choix}),10)
