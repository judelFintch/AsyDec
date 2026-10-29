import unittest
from unittest.mock import patch, Mock
from types import SimpleNamespace

from asydec.calcul import variantes
from asydec.declarations import generer


class ReglesCommunesTest(unittest.TestCase):
    def profil(self):
        return {'signature':[], 'ratios':[1.0]*8,
                'bornes':[(.9,1.1) if i not in (3,6,7) else (1.,1.) for i in range(8)]}

    def test_repartition_bornee_ne_change_pas_les_ratios_fixes(self):
        profil=self.profil()
        fob=variantes.fob_controles([100]*8,profil,820)
        self.assertEqual(sum(fob),820)
        for i in (3,6,7):
            self.assertEqual(fob[i],100)
        with self.assertRaises(ValueError):
            variantes.fob_controles([100]*8,profil,900)

    def test_export_refuse_les_memes_ecarts_que_apercu(self):
        profil=self.profil()
        info={'fob_articles':[100]*8,'fob':800,'poids':800,'colis':80,'camion':'','manifeste':''}
        with patch.object(generer.moteur,'charger',return_value=SimpleNamespace(getroot=lambda:None)), \
             patch.object(generer.moteur,'infos_dossier',return_value=info), \
             patch.object(variantes,'signature',return_value=[]), \
             patch.object(generer.moteur,'recalculer') as calcul, \
             patch.object(generer.moteur,'enregistrer') as ecriture:
            for enregistrer in (False,True):
                for mauvais in ('ratio','colis','total'):
                    fob=[100]*8
                    colis=[10]*8
                    if mauvais=='ratio': fob[3]=101
                    if mauvais=='colis': colis[0]=10.5
                    with self.assertRaises(ValueError):
                        generer.produire('base.xml',[100]*8,[1]*8,[],{},mode='SAISI',
                            fob_total=801 if mauvais=='total' else sum(fob),fob_saisis=fob,
                            colis_saisis=colis,colis_total=sum(colis),profil=profil,enregistrer=enregistrer)
            calcul.assert_not_called()
            ecriture.assert_not_called()


class PoidsEntiersTest(unittest.TestCase):
    def test_saisie_decimale_refusee(self):
        profil=ReglesCommunesTest().profil()
        poids=[100]*8
        poids[0]=100.5
        with self.assertRaisesRegex(ValueError,'entiers'):
            variantes.fob_controles(poids,profil,800)
        with self.assertRaisesRegex(ValueError,'entiers'):
            variantes.controler({'poids':poids,'fob':[100]*8,'colis':[10]*8},profil)
