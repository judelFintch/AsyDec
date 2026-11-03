"""Base des importateurs tirée des XML, et choix de l'importateur à l'ouverture ou à la répartition."""
import hashlib
from pathlib import Path
import tempfile
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import xml.etree.ElementTree as ET

from asydec import chemins
from asydec.calcul import moteur
from asydec.calcul import variantes
from asydec.declarations import correction_modele as C
from asydec.declarations import generer
from asydec.declarations import modeles_generes as M
from asydec.references import base_references as B
from asydec.references import import_references as IR
from asydec.references import importateurs as I
from asydec.references import service_references as S
from asydec.references.import_references import extraire
from asydec.ui.app import AsyDec
from asydec.ui.importateurs import IMPORTATEUR_XML
from tests.test_references import declaration, item

BASE = next(iter(sorted(chemins.MODELES_XML.glob('*.xml'))), None)
CHOISI = {'code': 'B123', 'nom': 'NOUVEL IMPORT', 'bloc': 'NOUVEL IMPORT\n AV TEST N°1\n LUBUMBASHI'}


def xml_importateur(code, bloc, reference='R1'):
    contenu = declaration([item()], reference=reference).decode()
    return contenu.replace('<Consignee_name>IMPORT A\nADRESSE</Consignee_name>',
                           f'<Consignee_code>{code}</Consignee_code><Consignee_name>{bloc}</Consignee_name>').encode()


class BaseImportateursTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dossier = Path(self.tmp.name)
        self.conn = B.ouvrir(self.dossier / 'base' / 'asydec.db')
        self.addCleanup(self.conn.close)

    def importer(self, nom, contenu):
        chemin = self.dossier / nom
        chemin.write_bytes(contenu)
        return IR.importer_fichier(self.conn, chemin)[1]

    def test_un_importateur_par_code_avec_nom_et_adresse(self):
        self.importer('a.xml', xml_importateur('A1', 'ZEBRE SARL\n AV 1'))
        self.importer('b.xml', xml_importateur('A1', 'ZEBRE SARL\n AV 1', 'R2'))
        self.importer('c.xml', xml_importateur('A2', 'ALPHA SA\n AV 2'))
        liste = I.lister(self.conn)
        self.assertEqual([(i['code'], i['nom']) for i in liste], [('A2', 'ALPHA SA'), ('A1', 'ZEBRE SARL')])
        self.assertEqual(liste[1]['bloc'], 'ZEBRE SARL\n AV 1')

    def test_adresse_rafraichie_par_un_xml_plus_recent(self):
        self.importer('a.xml', xml_importateur('A1', 'ZEBRE\n ANCIENNE'))
        I.lister(self.conn)
        self.importer('b.xml', xml_importateur('A1', 'ZEBRE\n NOUVELLE', 'R2'))
        self.assertEqual(I.lister(self.conn)[0]['bloc'], 'ZEBRE\n NOUVELLE')

    def test_xml_rejete_et_xml_sans_code_ignores(self):
        rejete = self.importer('a.xml', xml_importateur('A1', 'ZEBRE'))
        S.enregistrer_statut(self.conn, rejete, 'rejete', commentaire='erreur')
        self.importer('b.xml', xml_importateur('', 'SANS CODE', 'R2'))
        self.assertEqual(I.lister(self.conn), [])

    def test_archive_absente_ne_bloque_pas_la_liste(self):
        document = self.importer('a.xml', xml_importateur('A1', 'ZEBRE'))
        self.importer('b.xml', xml_importateur('A2', 'ALPHA'))
        Path(self.conn.execute('SELECT archive FROM documents WHERE id=?', (document,)).fetchone()[0]).unlink()
        self.assertEqual([i['code'] for i in I.lister(self.conn)], ['A2'])


class EcritureImportateurTest(unittest.TestCase):
    def racine(self, financier):
        return ET.fromstring(f'<ASYCUDA><Traders><Consignee><Consignee_code>A1</Consignee_code>'
                             f'<Consignee_name>ANCIEN</Consignee_name></Consignee><Financial>'
                             f'<Financial_code>{financier}</Financial_code><Financial_name>X</Financial_name>'
                             f'</Financial></Traders></ASYCUDA>')

    def test_payeur_identique_suit_l_importateur(self):
        racine = self.racine('A1')
        moteur.ecrire_importateur(racine, 'B1', 'NOUVEAU\n ADRESSE')
        self.assertEqual(racine.findtext('Traders/Consignee/Consignee_code'), 'B1')
        self.assertEqual(racine.findtext('Traders/Financial/Financial_code'), 'B1')
        self.assertEqual(racine.findtext('Traders/Financial/Financial_name'), 'NOUVEAU\n ADRESSE')

    def test_payeur_tiers_conserve(self):
        racine = self.racine('T9')
        moteur.ecrire_importateur(racine, 'B1', 'NOUVEAU')
        self.assertEqual(racine.findtext('Traders/Financial/Financial_code'), 'T9')

    def test_champ_absent_refuse(self):
        with self.assertRaises(ValueError):
            moteur.ecrire_importateur(ET.fromstring('<ASYCUDA><Traders/></ASYCUDA>'), 'B1', 'NOUVEAU')


@unittest.skipIf(BASE is None, 'aucun modèle XML local')
class GenerationAvecImportateurTest(unittest.TestCase):
    def setUp(self):
        self.empreinte = hashlib.sha256(BASE.read_bytes()).hexdigest()
        articles = [a for a in extraire(BASE.read_bytes())['articles'] if a['fob']]
        self.poids = [float(a['poids_brut']) for a in articles]
        self.fob = [float(a['fob']) for a in articles]
        self.colis = [int(float(a['colis'])) for a in articles]
        self.profil = variantes.construire_profil(str(BASE))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'modeles.db'

    def tearDown(self):
        self.assertEqual(hashlib.sha256(BASE.read_bytes()).hexdigest(), self.empreinte)

    def produire(self, importateur=None):
        return generer.produire(str(BASE), self.poids, self.profil['ratios'], [], {}, mode='SAISI',
                                fob_saisis=self.fob, colis_saisis=self.colis, enregistrer=False,
                                profil=self.profil, importateur=importateur)

    def test_sans_choix_comportement_inchange(self):
        res = self.produire()
        self.assertIsNone(res['importateur_choisi'])
        self.assertFalse(any('Importateur inscrit' in a for a in res['alertes']))

    def test_choisir_l_importateur_du_xml_ne_change_rien(self):
        info = moteur.infos_dossier(moteur.charger(BASE).getroot())
        res = self.produire({'code': info['code'], 'nom': info['importateur'], 'bloc': 'AUTRE'})
        self.assertIsNone(res['importateur_choisi'])

    def test_choix_applique_info_nom_de_fichier_taxes_et_alerte(self):
        sans, avec = self.produire(), self.produire(CHOISI)
        self.assertEqual((avec['info']['importateur'], avec['info']['code']), ('NOUVEL IMPORT', 'B123'))
        self.assertTrue(avec['nom'].startswith('NOUVEL IMPORT '))
        self.assertIn('NOUVEL IMPORT', avec['chemin'])
        self.assertEqual(sans['resume']['taxes_totales'], avec['resume']['taxes_totales'])
        self.assertTrue(any('Importateur inscrit dans le XML : NOUVEL IMPORT' in a for a in avec['alertes']))

    def test_modele_archive_garde_l_importateur_choisi(self):
        identifiant = M.enregistrer(self.produire(CHOISI), BASE, 'alice', base=self.db)
        d = M.detail(identifiant, base=self.db)
        racine = ET.fromstring(bytes(d['modele_xml']))
        self.assertEqual(racine.findtext('Traders/Consignee/Consignee_code'), 'B123')
        self.assertEqual(racine.findtext('Traders/Consignee/Consignee_name'), CHOISI['bloc'])
        self.assertEqual(d['importateur'], 'NOUVEL IMPORT')
        self.assertEqual(d['resultat']['importateur_choisi']['code'], 'B123')

    def test_meme_repartition_pour_deux_importateurs_donne_deux_modeles(self):
        un = M.enregistrer(self.produire(), BASE, 'alice', base=self.db)
        deux = M.enregistrer(self.produire(CHOISI), BASE, 'alice', base=self.db)
        self.assertNotEqual(un, deux)
        self.assertEqual(M.enregistrer(self.produire(CHOISI), BASE, 'alice', base=self.db), deux)

    def test_empreinte_sans_choix_inchangee_pour_les_anciens_modeles(self):
        self.assertEqual(M._empreinte(b'x', [(1, 2)], [3], None), M._empreinte(b'x', [(1, 2)], [3], None, None))

    def test_correction_part_de_l_importateur_choisi(self):
        identifiant = M.enregistrer(self.produire(CHOISI), BASE, 'alice', base=self.db)
        racine = moteur.charger(BASE).getroot()
        moteur.ecrire_importateur(racine, CHOISI['code'], CHOISI['bloc'])
        with self.assertRaisesRegex(ValueError, 'déjà celui du modèle'):
            C.preparer(identifiant, ET.tostring(racine), base=self.db)


class ChoixDansApplicationTest(unittest.TestCase):
    """L'importateur partagé entre Dossier et Répartitions, sans fenêtre."""

    def setUp(self):
        try:
            self.racine = tk.Tcl()
        except tk.TclError:
            self.skipTest('Tcl indisponible')
        self.var = tk.StringVar(self.racine, value=IMPORTATEUR_XML)
        self.app = SimpleNamespace(var_importateur=self.var, _importateurs={}, info=None, pages={'dossier': Mock()})
        self.app.importateur_choisi = lambda: AsyDec.importateur_choisi(self.app)
        self.app.changer_importateur = lambda: AsyDec.changer_importateur(self.app)
        self.app.afficher_bandeau = Mock()

    def test_par_defaut_celui_du_xml(self):
        self.assertIsNone(AsyDec.importateur_choisi(self.app))

    def test_reprise_retablit_puis_efface_le_choix(self):
        AsyDec.fixer_importateur(self.app, CHOISI)
        self.assertEqual(AsyDec.importateur_choisi(self.app), CHOISI)
        self.assertEqual(self.var.get(), I.libelle(CHOISI))
        AsyDec.fixer_importateur(self.app, None)
        self.assertIsNone(AsyDec.importateur_choisi(self.app))

    def test_choix_conserve_a_l_actualisation_meme_absent_de_la_base(self):
        AsyDec.fixer_importateur(self.app, CHOISI)
        with tempfile.TemporaryDirectory() as dossier:
            conn = B.ouvrir(Path(dossier) / 'asydec.db')
            self.app.base_refs = lambda: conn
            self.assertEqual(AsyDec.importateurs_proposes(self.app), [IMPORTATEUR_XML, I.libelle(CHOISI)])
            conn.close()
        self.assertEqual(AsyDec.importateur_choisi(self.app), CHOISI)

    def _ouvrir(self, base):
        pages = {'articles': Mock()}
        app = SimpleNamespace(session_verrouillee=False, base=base, var_importateur=self.var, _importateurs={},
                              partager_xml=lambda _c: [], chemins_xml_disponibles=lambda generation: [], prefs={},
                              reglages={'memoriser_recents': False}, _ecrire_prefs=Mock(), pages=pages,
                              var_bandeau=Mock(), module_travail='friperie', confiance_generation=lambda chemin: None)
        app.profil_generation = lambda chemin, **options: AsyDec.profil_generation(app, chemin, **options)
        AsyDec.ouvrir_base(app, str(BASE))

    @unittest.skipIf(BASE is None, 'aucun modèle XML local')
    def test_choix_fait_avant_l_ouverture_vaut_pour_ce_dossier(self):
        self.var.set(I.libelle(CHOISI))
        self._ouvrir(None)
        self.assertEqual(self.var.get(), I.libelle(CHOISI))

    @unittest.skipIf(BASE is None, 'aucun modèle XML local')
    def test_autre_dossier_ne_recoit_pas_le_choix_du_precedent(self):
        self.var.set(I.libelle(CHOISI))
        self._ouvrir('ancien.xml')
        self.assertEqual(self.var.get(), IMPORTATEUR_XML)


if __name__ == '__main__':
    unittest.main()
