"""Détection des déclarations SYDONIA réelles dans les dossiers et rattachement à leur modèle."""
from pathlib import Path
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from asydec.declarations import detection_reelles as D
from asydec.declarations import modeles_generes as M
from tests import test_modeles_generes as TM


def assurer(racine, chemin):
    noeud = racine
    for nom in chemin.split('/'):
        enfant = noeud.find(nom)
        noeud = enfant if enfant is not None else ET.SubElement(noeud, nom)
    return noeud


def variante(xml, numero, camion=None, poids=None, date='12/31/30'):
    """Copie du XML avec un autre numéro d'enregistrement, postérieure aux modèles par défaut
    (et, au besoin, plaque ou poids d'un article)."""
    racine = ET.fromstring(xml)
    racine.find('Identification/Registration/Number').text = str(numero)
    racine.find('Identification/Registration/Date').text = date
    if camion:
        assurer(racine, 'Transport/Means_of_transport/Departure_arrival_information/Identity').text = camion
    if poids:
        racine.find('Item/Valuation_item/Weight_itm/Gross_weight_itm').text = str(poids)
    return ET.tostring(racine)


class DetectionTest(unittest.TestCase):
    def setUp(self):
        TM.ModelesGeneresTest.setUp(self)
        self.dossiers = self.racine / 'DEC'
        historique = self.dossiers / 'KDMETA' / '1 - HISTORIQUE'
        historique.mkdir(parents=True)
        self.export = historique / 'KDMETA export.xml'
        self.export.write_bytes(self.xml)
        self.modele = M.enregistrer(self.resultat, self.source, 'alice', export=self.export, base=self.base)
        M.definir_plaque(self.modele, 'T1 / T9', 'alice', base=self.base)
        self.comparaison = self.dossiers / 'COMPARAISON'
        self.comparaison.mkdir()

    def ecrire(self, nom, contenu):
        chemin = self.comparaison / nom
        chemin.write_bytes(contenu)
        return chemin

    def detecter(self):
        return D.detecter(racine=self.dossiers, base=self.base)

    def test_declaration_reelle_rattachee_par_la_plaque(self):
        self.ecrire('T1.xml', variante(self.xml, 500, camion='T1/T2', poids=91))
        [c] = self.detecter()
        self.assertEqual((c['nom'], c['modele'], c['modeles']), ('T1.xml', self.modele, [self.modele]))
        self.assertEqual(c['enregistrement'], 'E 500')
        self.assertEqual(c['avertissements'], [])

    def test_enregistree_avant_le_modele_signalee(self):
        self.ecrire('T1.xml', variante(self.xml, 500, camion='T1/T2', date='1/2/20'))
        [c] = self.detecter()
        self.assertTrue(any(a.startswith('Enregistrée le 02/01/2020') for a in c['avertissements']))

    def test_sans_modele_correspondant(self):
        self.ecrire('T7.xml', variante(self.xml, 501, camion='T7/T8'))
        [c] = self.detecter()
        self.assertIsNone(c['modele'])

    def test_exports_gabarits_et_copies_ecartes(self):
        # Export AsyDec (déjà dans HISTORIQUE), copie du XML de base, et deux contenus au même numéro.
        self.ecrire('base copiee.xml', variante(self.xml, 12, poids=99, date='10/1/26'))
        self.ecrire('copie A.xml', variante(self.xml, 600, poids=80))
        self.ecrire('copie B.xml', variante(self.xml, 600, poids=81))
        self.assertEqual(self.detecter(), [])

    def test_confirmation_compare_puis_plus_detectee(self):
        reelle = self.ecrire('T1.xml', variante(self.xml, 500, camion='T1/T2', poids=91))
        orpheline = self.ecrire('T7.xml', variante(self.xml, 501, camion='T7/T8'))
        candidats = self.detecter()
        comparees, retenues, erreurs = D.enregistrer(candidats, 'alice', base=self.base)
        self.assertEqual((comparees, retenues, erreurs), (1, 1, []))
        self.assertEqual(M.lister(base=self.base)[0]['comparaisons'], 1)
        noms = {d['nom']: d['modele'] for d in M.declarations_reelles(base=self.base)}
        self.assertEqual(noms, {'T1.xml': self.modele, 'T7.xml': None})
        self.assertEqual(self.detecter(), [])
        # Les deux nourrissent désormais la génération.
        confiance = M.confiance_generation('x', base=self.base)
        self.assertEqual({Path(c).name for c in confiance['reelles']}, {reelle.name, orpheline.name})

    def test_modele_deja_compare_et_articles_differents_signales(self):
        self.ecrire('T1.xml', variante(self.xml, 500, camion='T1/T2'))
        candidats = self.detecter()
        D.enregistrer(candidats, 'alice', base=self.base)
        racine = ET.fromstring(variante(self.xml, 502, camion='T1/T3'))
        racine.find('Item/Goods_description/Description_of_goods').text = 'AUTRE MARCHANDISE'
        self.ecrire('T1 bis.xml', ET.tostring(racine))
        [c] = self.detecter()
        self.assertTrue(any(a.startswith('Articles différents') for a in c['avertissements']))
        self.assertTrue(any('déjà 1 comparaison' in a for a in c['avertissements']))

    def test_declaration_retenue_immuable_et_verifiee(self):
        chemin = self.ecrire('T7.xml', variante(self.xml, 501, camion='T7/T8'))
        M.ajouter_declaration_reelle(chemin, 'alice', base=self.base)
        M.ajouter_declaration_reelle(chemin, 'bob', base=self.base)  # sans doublon
        self.assertEqual(len(M.declarations_reelles(base=self.base)), 1)
        chemin.write_bytes(variante(self.xml, 501, camion='T7/T8', poids=70))
        self.assertEqual(M.declarations_reelles(base=self.base), [])  # modifiée : plus fiable
        self.assertRaises(ValueError, M.ajouter_declaration_reelle, chemin, 'alice', module='autre', base=self.base)


class FenetreTest(unittest.TestCase):
    def test_lignes_a_verifier_non_preselectionnees(self):
        from asydec.ui.rapport_comparaisons import AUCUN, FenetreDetection
        candidats = [dict(nom='A.xml', camion='T1', importateur='K', enregistrement='E 1', date=None, liquidee=True,
                          modeles=[3], modele=3, avertissements=[]),
                     dict(nom='B.xml', camion='T2', importateur='K', enregistrement='E 2', date=None, liquidee=False,
                          modeles=[4], modele=4, avertissements=['Articles différents du modèle : à vérifier.'])]
        racine = tk.Tk()
        racine.withdraw()
        self.addCleanup(racine.destroy)
        page = tk.Frame(racine)
        page.app = SimpleNamespace(utilisateur='alice', module_travail='friperie')
        fenetre = FenetreDetection(page, candidats)
        self.assertEqual(fenetre.table.selection(), ('0',))
        fenetre.table.selection_set('1')
        fenetre.actualiser()
        fenetre.modele.set(AUCUN)
        fenetre.changer_modele()
        self.assertIsNone(fenetre.candidats['1']['modele'])
        self.assertEqual(fenetre.table.item('1')['values'][6], 'Retenir comme déclaration réelle')
        with patch.object(D, 'enregistrer', return_value=(0, 1, [])) as enregistrer, \
                patch('asydec.ui.rapport_comparaisons.messagebox') as boites:
            boites.askyesno.return_value = True
            fenetre.enregistrer()
        self.assertEqual([c['nom'] for c in enregistrer.call_args[0][0]], ['B.xml'])
        self.assertTrue(fenetre.enregistre)


if __name__ == '__main__':
    unittest.main()
