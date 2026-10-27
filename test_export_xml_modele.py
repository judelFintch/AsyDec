"""Téléchargement exact d'un modèle validé, indépendant de ses fichiers d'origine."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET
import modeles_generes as M
import ui.modeles_generes as U
import test_modeles_generes as fixture_modeles


class ExportXmlModeleTest(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture_modeles.ModelesGeneresTest(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base=self.fixture.base
        self.destination=self.fixture.racine/'libre.xml'
        arbre=ET.parse(self.fixture.source)
        transport=ET.SubElement(arbre.getroot(),'Transport')
        moyens=ET.SubElement(transport,'Means_of_transport')
        arrivee=ET.SubElement(moyens,'Departure_arrival_information')
        ET.SubElement(arrivee,'Identity').text='T546ECQ/T618ECT'
        arbre.write(self.fixture.source)
        self.fixture.resultat['info']['camion']='T546ECQ/T618ECT'
        self.identifiant=self.fixture.enregistrer()

    def valider(self):
        M.changer_statut(self.identifiant,'valide','alice',base=self.base)

    def exporter(self,**options):
        return M.exporter_xml(self.identifiant,self.destination,'alice',base=self.base,**options)

    def test_valide_sans_origine_telecharge_et_devient_comparable(self):
        self.valider()
        d=M.detail(self.identifiant,base=self.base)
        self.fixture.source.unlink()
        self.assertFalse(M.lister(base=self.base)[0]['exporte'])
        self.exporter()
        self.assertEqual(self.destination.read_bytes(),d['modele_xml'])
        self.assertEqual(M.lire_export(self.identifiant,base=self.base),d['modele_xml'])
        self.assertTrue(M.lister(base=self.base)[0]['exporte'])
        self.assertEqual(M.detail(self.identifiant,base=self.base)['statut'],'valide')

    def test_export_preexistant_octets_exacts_prioritaires(self):
        self.valider()
        origine=self.fixture.racine/'export-original.xml'
        octets=self.fixture.xml+b'\n<!-- octets exportes exacts -->'
        origine.write_bytes(octets)
        self.fixture.enregistrer(export=origine)
        origine.unlink()
        self.fixture.source.unlink()
        self.exporter()
        self.assertEqual(self.destination.read_bytes(),octets)

    def test_statut_attente_ou_rejete_refuse_sans_fichier(self):
        for statut in ('en_attente','rejete'):
            if statut=='rejete':
                M.changer_statut(self.identifiant,statut,'alice','Motif',base=self.base)
            with self.assertRaisesRegex(ValueError,'Validé localement'):
                self.exporter()
            self.assertFalse(self.destination.exists())

    def test_nom_propose_plaque_sans_chemin_ni_caracteres_interdits(self):
        d=M.detail(self.identifiant,base=self.base)
        self.assertEqual(M.nom_export(d),'T546ECQ-T618ECT - proposition.xml')
        d['resultat']['info']['camion']='../../DB:\\test?*<>\n'
        d['nom']='../../fichier|dangereux.xml'
        nom=M.nom_export(d)
        self.assertEqual(Path(nom).name,nom)
        self.assertTrue(nom.endswith('.xml'))
        self.assertFalse(any(c in nom for c in '<>:"/\\|?*\n'))

    def test_echec_ecriture_aucun_faux_evenement(self):
        self.valider()
        avant=M.detail(self.identifiant,base=self.base)['evenements']
        with patch('os.link',side_effect=PermissionError('dossier interdit')):
            with self.assertRaises(PermissionError):
                self.exporter()
        self.assertEqual(M.detail(self.identifiant,base=self.base)['evenements'],avant)
        self.assertFalse(self.destination.exists())
        self.assertFalse(list(self.fixture.racine.glob('.asydec-*')))

    def test_ecrasement_exige_option_explicite(self):
        self.valider()
        self.destination.write_bytes(b'original')
        with self.assertRaises(FileExistsError):
            self.exporter()
        self.assertEqual(self.destination.read_bytes(),b'original')
        self.exporter(ecraser=True)
        self.assertEqual(self.destination.read_bytes(),M.lire_export(self.identifiant,base=self.base))

    def test_extension_et_destination_base_protegees(self):
        self.valider()
        avant=self.base.read_bytes()
        with self.assertRaises(ValueError):
            M.exporter_xml(self.identifiant,self.base,'alice',ecraser=True,base=self.base)
        self.assertEqual(self.base.read_bytes(),avant)
        with self.assertRaises(ValueError):
            M.exporter_xml(self.identifiant,self.destination.with_suffix('.txt'),'alice',base=self.base)

    def test_echec_suivi_signale_fichier_deja_cree(self):
        self.valider()
        with patch.object(M,'_evenement',side_effect=RuntimeError('base indisponible')):
            with self.assertRaises(M.ErreurSuiviExport):
                self.exporter()
        self.assertTrue(self.destination.exists())
        self.assertFalse(M.lister(base=self.base)[0]['exporte'])


class ActionExportXmlTest(unittest.TestCase):
    def page(self):
        return SimpleNamespace(app=SimpleNamespace(session_verrouillee=False,utilisateur='alice'),
                               selection=lambda:7,afficher=Mock())

    def test_verrouillage_et_statut_refuse_avant_dialogue(self):
        for statut,verrouille in (('valide',True),('en_attente',False),('rejete',False)):
            page=self.page()
            page.app.session_verrouillee=verrouille
            with patch.object(U.service,'detail',return_value={'statut':statut}), \
                 patch.object(U.messagebox,'showerror'),patch.object(U.filedialog,'asksaveasfilename') as choisir:
                U.PageModelesGeneres.telecharger_xml(page)
            choisir.assert_not_called()

    def test_nom_plaque_dossier_libre_confirmation_ecrasement(self):
        page=self.page()
        d={'id':7,'statut':'valide','nom':'modele.xml','resultat':{'info':{'camion':'ABC/123'}}}
        with patch.object(U.service,'detail',return_value=d), \
             patch.object(U.filedialog,'asksaveasfilename',return_value='choix.xml') as choisir, \
             patch.object(U.service,'exporter_xml',return_value='choix.xml') as exporter,patch.object(U.messagebox,'showinfo'):
            U.PageModelesGeneres.telecharger_xml(page)
        self.assertEqual(choisir.call_args.kwargs['initialfile'],'ABC-123 - modele.xml')
        self.assertTrue(choisir.call_args.kwargs['confirmoverwrite'])
        self.assertNotIn('initialdir',choisir.call_args.kwargs)
        exporter.assert_called_once()
        page.afficher.assert_called_once()

    def test_etat_bouton_xml_valide_et_session_libre(self):
        for statut,verrouille,etat in (('valide',False,'normal'),('en_attente',False,'disabled'),('valide',True,'disabled')):
            page=self.page()
            page.app.session_verrouillee=verrouille
            page.modeles={'7':{'statut':statut}}
            page.comparer_bouton=Mock()
            page.pdf_bouton=Mock()
            page.xml_bouton=Mock()
            U.PageModelesGeneres.actualiser_comparaison(page)
            page.xml_bouton.configure.assert_called_with(state=etat)


if __name__=='__main__':
    unittest.main()
