"""Correction atomique et versionnée d'un modèle déjà validé."""
from dataclasses import replace
import json
import unittest
import xml.etree.ElementTree as ET

from asydec.calcul import moteur
from asydec.declarations import correction_modele as C, modeles_generes as M
from tests import test_modeles_generes as fixtures


class CorrectionModeleTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ModelesGeneresTest(methodName='runTest')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.identifiant = self.f.enregistrer()
        M.changer_statut(self.identifiant, 'valide', 'alice', base=self.f.base)
        self.avant = M.detail(self.identifiant, self.f.base)
        donneur = ET.fromstring(self.f.source.read_bytes())
        donneur.find('Traders/Consignee/Consignee_name').text = 'IMPORT B\nNOUVELLE ADRESSE'
        ET.SubElement(donneur.find('Traders/Consignee'), 'Consignee_code').text = 'B123'
        donneur.find('Declarant/Reference/Number').text = 'DOSSIER-B'
        donneur.find('Valuation/Gs_Invoice/Currency_rate').text = '3000'
        donneur.find('Financial/Amounts/Global_taxes').text = '999'
        self.donneur = ET.tostring(donneur)

    def preparer(self, mode='importateur', donneur=None):
        return C.preparer(self.identifiant, donneur or self.donneur, mode, self.f.base)

    def test_importateur_uniquement_preserve_repartition_ratios_et_taxes(self):
        apercu = self.preparer()
        self.assertEqual(len(M.lister(base=self.f.base)), 1)  # l'aperçu n'écrit aucun modèle
        self.assertEqual(apercu.resultat['info']['importateur'], 'IMPORT B')
        self.assertEqual(apercu.resultat['info']['code'], 'B123')
        self.assertEqual(apercu.resultat['resume'], self.avant['resultat']['resume'])
        self.assertEqual(apercu.resultat['info']['reference'], 'R1')
        self.assertEqual(apercu.resultat['info']['taux'], 2265.5)
        nouveau = C.enregistrer(apercu, 'bob', 'Mauvais importateur choisi', self.f.base)
        self.assertNotEqual(nouveau, self.identifiant)
        d = M.detail(nouveau, self.f.base)
        self.assertEqual(d['statut'], 'en_attente')
        self.assertEqual(d['auteur'], 'bob')
        self.assertFalse(d['bon'])
        self.assertFalse(any(e['action'] == M.EXPORT for e in d['evenements']))
        self.assertEqual(d['resultat']['correction']['modele_initial'], self.identifiant)
        self.assertEqual(d['resultat']['fob'], self.avant['resultat']['fob'])
        self.assertEqual(d['resultat']['colis'], self.avant['resultat']['colis'])
        original = M.detail(self.identifiant, self.f.base)
        for cle in ('base_xml','modele_xml','resultat','statut','importateur'):
            self.assertEqual(original[cle], self.avant[cle])
        self.assertEqual(original['evenements'][-1]['action'], 'version_corrigee')
        self.assertIn(str(nouveau), M.resume_evenement(original['evenements'][-1]))
        self.assertEqual(self.f.source.read_bytes(), self.avant['base_xml'])

    def test_base_complete_recalcule_les_taxes_et_conserve_les_ratios(self):
        apercu = self.preparer('base')
        self.assertEqual(apercu.resultat['info']['reference'], 'DOSSIER-B')
        self.assertEqual(apercu.resultat['info']['taux'], 3000)
        self.assertEqual(apercu.resultat['resume']['taxes_globales'], 999)
        self.assertNotEqual(apercu.resultat['resume']['taxes_totales'], self.avant['resultat']['resume']['taxes_totales'])
        self.assertEqual(apercu.resultat['fob'], self.avant['resultat']['fob'])
        self.assertEqual([a['poids'] for a in apercu.resultat['resume']['articles']],
                         [a['poids'] for a in self.avant['resultat']['resume']['articles']])
        nouveau = C.enregistrer(apercu, 'alice', 'Bonne base du dossier', self.f.base)
        d = M.detail(nouveau, self.f.base)
        self.assertEqual(d['statut'], 'en_attente')
        self.assertEqual(moteur.infos_dossier(ET.fromstring(d['modele_xml']))['code'], 'B123')
        self.assertEqual(d['resultat']['reference']['sha256'], M._sha(self.avant['base_xml']))

    def test_base_incompatible_refusee_mais_importateur_seul_autorise(self):
        for chemin, valeur in [('Item/Tarification/HScode/Commodity_code','9999'),
                              ('Item/Goods_description/Description_of_goods','Autre'),
                              ('Valuation/Gs_Invoice/Currency_code','EUR')]:
            with self.subTest(chemin=chemin):
                racine = ET.fromstring(self.donneur)
                racine.find(chemin).text = valeur
                with self.assertRaisesRegex(ValueError, 'incompatible'):
                    self.preparer('base', ET.tostring(racine))
                self.assertEqual(self.preparer('importateur', ET.tostring(racine)).resultat['info']['importateur'], 'IMPORT B')
        self.assertEqual(len(M.lister(base=self.f.base)), 1)

    def test_motif_session_et_modele_supprime_exiges(self):
        apercu = self.preparer()
        for auteur, motif in [('', 'raison'), ('alice',' ')]:
            with self.assertRaises(ValueError):
                C.enregistrer(apercu, auteur, motif, self.f.base)
        M.supprimer(self.identifiant, 'alice', base=self.f.base)
        with self.assertRaises(ValueError):
            self.preparer()
        self.assertEqual(len(M.lister(base=self.f.base, supprimes=True)), 1)

    def test_modification_apres_apercu_exige_une_nouvelle_verification(self):
        apercu = self.preparer()
        M.changer_statut(self.identifiant, 'en_attente', 'alice', base=self.f.base)
        with self.assertRaisesRegex(ValueError, 'actualisez'):
            C.enregistrer(apercu, 'alice', 'raison', self.f.base)
        self.assertEqual(len(M.lister(base=self.f.base)), 1)

    def test_apercu_modifie_ne_peut_pas_modifier_le_resultat(self):
        apercu = self.preparer()
        apercu.resultat['resume']['taxes_totales'] = 1
        with self.assertRaisesRegex(ValueError, 'actualisez'):
            C.enregistrer(apercu, 'alice', 'raison', self.f.base)
        self.assertEqual(len(M.lister(base=self.f.base)), 1)
