"""Taxes globales recalculées d'après la règle apprise sur les déclarations réelles comparées."""
from decimal import Decimal
import copy
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from asydec import chemins
from asydec.calcul import moteur
from asydec.calcul import variantes as V
from asydec.declarations import comparaison_prediction as C
from asydec.declarations import generer as G
from asydec.declarations import modeles_generes as M
from tests import test_modeles_generes as TM

MODELES = sorted(chemins.MODELES_XML.glob('*.xml'))
TAUX = Decimal('0.14810')


def avec_globales(contenu, cif, globales):
    racine = ET.fromstring(contenu)
    racine.find('Valuation/Total_CIF').text = str(cif)
    racine.find('Financial/Amounts/Global_taxes').text = str(globales)
    return ET.tostring(racine)


class MoteurTest(unittest.TestCase):
    def setUp(self):
        TM.ModelesGeneresTest.setUp(self)
        self.lignes = [(140, 90), (35, 60)]

    def recalculer(self, **options):
        arbre = ET.parse(self.source)
        return arbre, moteur.recalculer(arbre, self.lignes, [10, 11], **options)

    def test_sans_regle_montant_du_xml_repris(self):
        arbre, resume = self.recalculer()
        self.assertEqual(resume['taxes_globales'], int(float(arbre.getroot().findtext('Financial/Amounts/Global_taxes'))))

    def test_avec_regle_part_du_cif(self):
        arbre, resume = self.recalculer(taux_globales=TAUX)
        self.assertEqual(resume['taxes_globales'], moteur.arrondi(resume['cif'] * float(TAUX)))
        self.assertEqual(resume['taxes_totales'], resume['taxes_articles'] + resume['taxes_globales'])
        racine = arbre.getroot()
        self.assertEqual(racine.findtext('Financial/Amounts/Global_taxes'), str(resume['taxes_globales']))
        self.assertEqual(racine.findtext('Financial/Amounts/Totals_taxes'), str(resume['taxes_totales']))

    def test_modele_conserve_avec_sa_regle(self):
        # Le XML conservé est recalculé avec la même règle : sinon sa vérification échouerait.
        arbre, resume = self.recalculer(taux_globales=TAUX)
        resultat = dict(self.resultat, resume=resume, taux_globales=str(TAUX))
        identifiant = M.enregistrer(resultat, self.source, 'alice', base=self.base)
        xml = ET.fromstring(M.detail(identifiant, base=self.base)['modele_xml'])
        self.assertEqual(xml.findtext('Financial/Amounts/Global_taxes'), str(resume['taxes_globales']))
        sans_regle = dict(self.resultat, resume=resume)
        self.assertRaisesRegex(ValueError, 'ne correspond plus', M.enregistrer, sans_regle, self.source, 'bob',
                               base=self.base)


class ApprentissageTest(unittest.TestCase):
    def setUp(self):
        TM.ModelesGeneresTest.setUp(self)
        self.export = self.racine / 'export.xml'
        self.export.write_bytes(self.xml)
        self.identifiant = M.enregistrer(self.resultat, self.source, 'alice', export=self.export, base=self.base)

    def reelle(self, nom, cif, globales):
        chemin = self.racine / nom
        chemin.write_bytes(avec_globales(self.xml, cif, globales))
        M.noter_comparaison(self.identifiant, chemin, C.comparer_xmls(self.export, chemin), 'alice', base=self.base)

    def test_une_seule_declaration_ne_suffit_pas(self):
        self.reelle('a.xml', 28721812, 4253639)
        self.assertIsNone(M.taux_taxes_globales(base=self.base))

    def test_declarations_concordantes(self):
        self.reelle('a.xml', 28721812, 4253639)
        self.reelle('b.xml', 28270000, 4186807)
        regle = M.taux_taxes_globales(base=self.base)
        self.assertEqual(regle['n'], 2)
        self.assertEqual(regle['taux'], Decimal(4253639 + 4186807) / Decimal(28721812 + 28270000))
        self.assertLess(regle['ecart_max'], 100)
        self.assertEqual(M.confiance_generation('x', base=self.base)['taxes_globales'], regle)

    def test_declarations_discordantes_pas_de_regle_devinee(self):
        self.reelle('a.xml', 28721812, 4253639)   # 14,810 %
        self.reelle('b.xml', 28721812, 4322000)   # 15,048 %
        self.assertIsNone(M.taux_taxes_globales(base=self.base))


@unittest.skipIf(not MODELES, 'aucun modèle XML local')
class ProductionTest(unittest.TestCase):
    def produire(self, profil):
        info = moteur.infos_dossier(moteur.charger(str(MODELES[0])).getroot())
        return G.produire(str(MODELES[0]), info['poids_articles'], profil['ratios'], G.charger_reglages()[1], {},
                          mode='SAISI', fob_saisis=info['fob_articles'], colis_saisis=info['colis_articles'],
                          enregistrer=False, profil=profil)

    def test_regle_appliquee_et_expliquee(self):
        profil = V.construire_profil(str(MODELES[0]), [str(MODELES[0])])
        sans = self.produire(profil)
        self.assertIsNone(sans['taux_globales'])
        regle = {'taux': Decimal('0.2'), 'n': 3, 'min': Decimal('0.2'), 'max': Decimal('0.2'), 'ecart_max': Decimal(4)}
        avec = self.produire(dict(copy.deepcopy(profil), taxes_globales=regle))
        self.assertEqual(avec['resume']['taxes_globales'], moteur.arrondi(avec['resume']['cif'] * 0.2))
        self.assertEqual(avec['taux_globales'], '0.2')
        self.assertTrue(any(a.startswith('Taxes globales recalculées : 20,000 % du CIF') for a in avec['alertes']))
        # Le XML de base n'est pas à 20 % : il est signalé.
        self.assertTrue(any('XML de base' in a and 'au lieu de 20,000 %' in a for a in avec['alertes']))


if __name__ == '__main__':
    unittest.main()
