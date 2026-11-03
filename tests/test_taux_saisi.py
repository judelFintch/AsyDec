"""Taux de change saisi : il remplace celui du XML de base dans les calculs, l'aperçu et le modèle conservé."""
import hashlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from asydec import chemins
from asydec.calcul import moteur
from asydec.calcul import variantes
from asydec.declarations import generer
from asydec.declarations import modeles_generes as M
from asydec.ui import taux_change

BASE = next(iter(sorted(chemins.MODELES_XML.glob('*.xml'))), None)


class TauxChoisiTest(unittest.TestCase):
    def app(self, texte):
        return SimpleNamespace(var_taux=SimpleNamespace(get=lambda: texte), session_verrouillee=False)

    def test_lecture_du_champ(self):
        self.assertIsNone(taux_change.taux_choisi(SimpleNamespace()))
        self.assertIsNone(taux_change.taux_choisi(self.app('  ')))
        self.assertEqual(taux_change.taux_choisi(self.app('2 500,5')), 2500.5)
        for texte in ('abc', '0', '-3', 'nan'):
            with self.assertRaises(ValueError):
                taux_change.taux_choisi(self.app(texte))

    @unittest.skipIf(BASE is None, 'aucun modèle XML local')
    def test_taux_saisi_rien_a_confirmer(self):
        with patch.object(taux_change.messagebox, 'askyesno') as question:
            self.assertTrue(taux_change.confirmer(self.app('2500'), [str(BASE)]))
        question.assert_not_called()


@unittest.skipIf(BASE is None, 'aucun modèle XML local')
class TauxDansLeCalculTest(unittest.TestCase):
    def setUp(self):
        self.empreinte = hashlib.sha256(BASE.read_bytes()).hexdigest()
        self.info = moteur.infos_dossier(moteur.charger(str(BASE)).getroot())
        self.profil = variantes.construire_profil(str(BASE))

    def tearDown(self):
        self.assertEqual(hashlib.sha256(BASE.read_bytes()).hexdigest(), self.empreinte)

    def produire(self, taux=None):
        i = self.info
        return generer.produire(str(BASE), i['poids_articles'], self.profil['ratios'], [], {}, mode='SAISI',
            fob_total=i['fob'], fob_saisis=i['fob_articles'], colis_saisis=i['colis_articles'],
            enregistrer=False, profil=self.profil, taux=taux)

    def test_ecrire_taux_remplace_les_taux_positifs_et_reconvertit_rls(self):
        racine = moteur.charger(str(BASE)).getroot()
        avant = [n.text for n in racine.iter('Currency_rate')]
        rls = [float(moteur._txt(l, 'Duty_tax_Base')) for l in racine.iter('Taxation_line')
               if moteur._txt(l, 'Duty_tax_code') == 'RLS']
        ancien = moteur.ecrire_taux(racine, 2500)
        self.assertEqual(ancien, self.info['taux'])
        apres = [n.text for n in racine.iter('Currency_rate')]
        self.assertEqual(apres, ['2500' if float(a or 0) > 0 else a for a in avant])
        nouveaux = [float(moteur._txt(l, 'Duty_tax_Base')) for l in racine.iter('Taxation_line')
                    if moteur._txt(l, 'Duty_tax_code') == 'RLS']
        self.assertEqual(nouveaux, [round(b / ancien) * 2500 for b in rls])
        with self.assertRaises(ValueError):
            moteur.ecrire_taux(racine, 0)

    def test_sans_taux_ou_meme_taux_rien_ne_change(self):
        normal = self.produire()
        self.assertIsNone(normal['taux_choisi'])
        meme = self.produire(self.info['taux'])
        self.assertIsNone(meme['taux_choisi'])
        self.assertEqual(meme['resume'], normal['resume'])

    def test_taux_saisi_applique_aux_montants_et_signale(self):
        normal, saisi = self.produire(), self.produire(self.info['taux'] * 1.1)
        self.assertAlmostEqual(saisi['resume']['taux'], self.info['taux'] * 1.1)
        self.assertEqual(saisi['taux_choisi'], saisi['resume']['taux'])
        self.assertEqual(saisi['taux_xml'], self.info['taux'])
        self.assertGreater(saisi['resume']['cif'], normal['resume']['cif'])
        self.assertGreater(saisi['resume']['taxes_articles'], normal['resume']['taxes_articles'])
        self.assertEqual(saisi['resume']['taxes_globales'], normal['resume']['taxes_globales'])
        self.assertTrue(any(a.startswith('Taux appliqué') for a in saisi['alertes']))

    def test_modele_conserve_porte_le_taux_et_sa_propre_empreinte(self):
        saisi = self.produire(2500)
        source = BASE.read_bytes()
        lignes = [(a['fob'], a['poids']) for a in saisi['resume']['articles']]
        xml = ET.fromstring(M._snapshot(source, saisi, lignes))
        self.assertEqual(moteur._txt(xml, 'Valuation/Gs_Invoice/Currency_rate'), '2500')
        self.assertNotEqual(M._empreinte(source, lignes, saisi['colis'], None, None, 2500),
                            M._empreinte(source, lignes, saisi['colis'], None, None, None))


if __name__ == '__main__':
    unittest.main()
