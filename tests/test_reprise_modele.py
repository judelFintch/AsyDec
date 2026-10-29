"""Reprendre dans une archive persistante sans toucher à la source ou à sa validation."""
import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

from asydec.calcul import moteur
from asydec.declarations import modeles_generes as M
from asydec.references import base_references as B
from asydec.references import catalogue_xml as C
from asydec.systeme import gestion_locale as L
from asydec.ui.modeles_generes import PageModelesGeneres
from asydec.ui.outils import PageHistorique
from asydec.ui.reprise_modele import reprendre
from tests import test_modeles_generes as fixtures


class RepriseModeleTest(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ModelesGeneresTest(methodName='runTest')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        arbre=ET.parse(self.f.source)
        racine=arbre.getroot()
        prototype=copy.deepcopy(moteur.articles(racine)[0])
        for it in racine.findall('Item'):
            racine.remove(it)
        for k in range(8):
            it=copy.deepcopy(prototype)
            it.find('Tarification/HScode/Commodity_code').text=str(6300+k)
            racine.append(it)
        racine.find('Valuation/Total/Total_invoice').text='1200'
        racine.find('Valuation/Total/Total_weight').text='800'
        racine.find('Property/Nbers/Total_number_of_packages').text='108'
        arbre.write(self.f.source)
        self.contenu=self.f.source.read_bytes()
        self.repartition={'poids':[90,110]+[100]*6,'fob':[135,165]+[150]*6,'colis':list(range(10,18))}
        resume=moteur.recalculer(arbre,list(zip(self.repartition['fob'],self.repartition['poids'])),self.repartition['colis'])
        self.resultat={'resume':resume,'fob':self.repartition['fob'],'colis':self.repartition['colis'],
            'nom':'conserve.xml','chemin':str(self.f.racine/'export.xml'),
            'info':moteur.infos_dossier(arbre.getroot()),'alertes':[],'mode':'SAISI'}
        self.conn=B.ouvrir(self.f.racine/'references/asydec.db')
        self.addCleanup(self.conn.close)
        config=patch.object(L,'CONFIGURATION',self.f.racine/'CONFIG_LOCAL')
        config.start()
        self.addCleanup(config.stop)
        self.app=SimpleNamespace(session_verrouillee=False,base='dossier-actif.xml',
            pages={'articles':SimpleNamespace(remplir=Mock())},montrer=Mock())
        self.app.partager_xml=lambda chemins:C.partager(self.conn,chemins)[1]
        self.app.xml_disponibles=lambda generation=False:C.lister(self.conn,generation=generation)
        def ouvrir(chemin):
            self.app.base=chemin
            return True
        self.app.ouvrir_base=Mock(side_effect=ouvrir)
        self.oui=patch('asydec.ui.reprise_modele.messagebox.askyesno',return_value=True)
        self.oui.start()
        self.addCleanup(self.oui.stop)
        self.erreur=patch('asydec.ui.reprise_modele.messagebox.showerror')
        self.erreur_mock=self.erreur.start()
        self.addCleanup(self.erreur.stop)

    def test_historique_archive_persistante_et_valeurs_exactes(self):
        self.assertTrue(reprendre(self.app,self.contenu,'historique.xml'))
        archive=Path(self.app.base)
        self.assertTrue(archive.is_file())
        self.assertEqual(archive.read_bytes(),self.contenu)
        self.assertNotEqual(archive,self.f.source)
        self.assertNotIn('asydec-reprise-',str(archive))
        self.app.pages['articles'].remplir.assert_called_once_with([100]*8,[150.]*8,[10]*8,mode='SAISI')
        self.app.montrer.assert_called_once_with('articles')
        self.assertEqual(self.f.source.read_bytes(),self.contenu)

    def test_snapshot_sans_origine_statut_et_evenements_intacts(self):
        identifiant=M.enregistrer(self.resultat,self.f.source,'alice',base=self.f.base)
        M.changer_statut(identifiant,'valide','alice',base=self.f.base)
        avant=M.detail(identifiant,base=self.f.base)
        self.f.source.unlink()
        with patch('asydec.ui.modeles_generes.service.detail',return_value=avant):
            page=SimpleNamespace(app=self.app,selection=lambda:identifiant)
            PageModelesGeneres.reprendre(page)
        self.app.pages['articles'].remplir.assert_called_once_with(self.repartition['poids'],self.repartition['fob'],self.repartition['colis'],mode='SAISI')
        apres=M.detail(identifiant,base=self.f.base)
        self.assertEqual(apres,avant)
        # Reprise inchangée retrouve la même identité ; une modification crée une autre proposition.
        meme=M.enregistrer(self.resultat,self.app.base,'alice',base=self.f.base)
        self.assertEqual(meme,identifiant)
        nouveau=copy.deepcopy(self.resultat)
        arbre=ET.parse(self.app.base)
        nouveau['resume']=moteur.recalculer(arbre,[(150,100)]*8,self.repartition['colis'])
        nouveau['fob']=[150]*8
        autre=M.enregistrer(nouveau,self.app.base,'alice',base=self.f.base)
        self.assertNotEqual(autre,identifiant)
        self.assertEqual(M.detail(identifiant,base=self.f.base)['statut'],'valide')

    def test_annulation_et_verrouillage_preservent_dossier(self):
        with patch('asydec.ui.reprise_modele.messagebox.askyesno',return_value=False):
            self.assertFalse(reprendre(self.app,self.contenu))
        self.app.session_verrouillee=True
        self.assertFalse(reprendre(self.app,self.contenu))
        self.app.ouvrir_base.assert_not_called()
        self.assertEqual(self.app.base,'dossier-actif.xml')
        self.assertEqual(C.lister(self.conn),[])

    def test_positions_incompletes_et_poids_decimal_refuses_avant_remplacement(self):
        racine=ET.fromstring(self.contenu)
        racine.findall('Item')[3].find('Tarification/Item_price').text = '0'
        self.assertFalse(reprendre(self.app,ET.tostring(racine)))
        racine=ET.fromstring(self.contenu)
        racine.find('Item/Valuation_item/Weight_itm/Gross_weight_itm').text='99.5'
        self.assertFalse(reprendre(self.app,ET.tostring(racine)))
        self.assertIn('Aucun poids décimal',self.erreur_mock.call_args.args[1])
        self.app.ouvrir_base.assert_not_called()
        self.assertEqual(C.lister(self.conn),[])

    def test_xml_eight_actifs_aux_mauvaises_positions_refuse(self):
        racine=ET.fromstring(self.contenu)
        racine.insert(list(racine).index(racine.find('Item')),ET.Element('Item'))
        self.assertFalse(reprendre(self.app,ET.tostring(racine)))
        self.app.ouvrir_base.assert_not_called()

    def test_echec_ouverture_ne_remplit_pas_articles(self):
        self.app.ouvrir_base.side_effect=None
        self.app.ouvrir_base.return_value=False
        self.assertFalse(reprendre(self.app,self.contenu))
        self.app.pages['articles'].remplir.assert_not_called()

    def test_historique_fichier_manquant_renvoie_vers_snapshots(self):
        page=SimpleNamespace(app=self.app,liste=Mock(selection=Mock(return_value=['absent.xml'])))
        with patch('asydec.ui.outils.messagebox.showinfo') as info:
            PageHistorique.reprendre(page)
        self.assertIn('Modèles générés',info.call_args.args[1])
        self.app.ouvrir_base.assert_not_called()


if __name__=='__main__':
    unittest.main()
