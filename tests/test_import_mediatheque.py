"""Un seul chemin d'import ; réactivation des seuls XML réellement rechargés."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from asydec.references import base_references as B
from asydec.references import catalogue_xml as C
from asydec.references import import_fond
from asydec.references import import_references as I
from asydec.references import service_references as S
from asydec.systeme import gestion_locale as L
from asydec.ui.mediatheque import PageMediatheque
from asydec.ui.references import PageReferences
from tests.test_references import declaration, item


class RedirectionMediathequeTest(unittest.TestCase):
    def page(self):
        references=SimpleNamespace(tache=None,message=Mock(),importer_fichiers=Mock(),importer_dossier=Mock())
        app=SimpleNamespace(session_verrouillee=False,pages={'references':references},montrer=Mock())
        page=SimpleNamespace(app=app)
        page._importer_bibliotheque=lambda **v:PageMediatheque._importer_bibliotheque(page,**v)
        return page,references

    def test_fichiers_et_dossier_delegues_sans_second_import(self):
        page,ref=self.page()
        PageMediatheque.ajouter(page)
        PageMediatheque.dossier(page)
        self.assertEqual(page.app.montrer.call_count,2)
        ref.importer_fichiers.assert_called_once()
        ref.importer_dossier.assert_called_once()

    def test_import_deja_actif_ou_terminal_non_consomme_pas_de_second(self):
        page,ref=self.page()
        ref.tache=object()
        PageMediatheque.ajouter(page)
        ref.importer_fichiers.assert_not_called()
        ref.message.afficher.assert_called_once()

    def test_session_verrouillee_pas_de_navigation_ni_choix(self):
        page,ref=self.page()
        page.app.session_verrouillee=True
        PageMediatheque.dossier(page)
        page.app.montrer.assert_not_called()
        ref.importer_dossier.assert_not_called()

    def test_bibliotheque_garde_avant_dialogue(self):
        for verrouille,tache in ((True,None),(False,object())):
            page=SimpleNamespace(app=SimpleNamespace(session_verrouillee=verrouille),tache=tache)
            with patch('asydec.ui.references.filedialog.askopenfilenames') as fichiers,patch('asydec.ui.references.filedialog.askdirectory') as dossier:
                PageReferences.importer_fichiers(page)
                PageReferences.importer_dossier(page)
            fichiers.assert_not_called()
            dossier.assert_not_called()


class ReactivationApresImportTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.racine=Path(self.temp.name)
        configuration=patch.object(L,'CONFIGURATION',self.racine/'CONFIG_LOCAL')
        configuration.start()
        self.addCleanup(configuration.stop)
        self.base=self.racine/'DONNEES/asydec.db'
        self.conn=B.ouvrir(self.base)
        self.addCleanup(self.conn.close)
        self.chemins=[]
        for k in range(2):
            p=self.racine/f'{k}.xml'
            p.write_bytes(declaration([item(code=str(k))]))
            self.chemins.append(p)
        C.partager(self.conn,self.chemins)
        self.documents=C.lister(self.conn)
        C.retirer(self.documents)
        self.page=SimpleNamespace(tache=object(),bouton_annuler=None,boutons_import=[],message=Mock(),
            _etat_boutons=Mock(),winfo_exists=lambda:False,conn=lambda:self.conn)

    def terminer(self,bilan):
        PageReferences._terminer(self.page,bilan=bilan)

    def test_doublon_retire_recharge_reactive_sans_changer_statut(self):
        identifiant=self.documents[0]['id']
        S.enregistrer_statut(self.conn,identifiant,'accepte',preuve='preuve test')
        chemin=next(p for p in self.chemins if p.name==self.documents[0]['nom'])
        bilan=I.importer_lot([chemin],self.conn)
        self.assertEqual(bilan.documents,[])
        self.assertEqual(bilan.documents_traites,[identifiant])
        self.terminer(bilan)
        self.assertEqual(len(C.lister(self.conn)),1)
        self.assertEqual(S.statut(self.conn,identifiant),'accepte')

    def test_annulation_et_refus_ne_restaurent_pas_non_traites(self):
        appels=[]
        def annuler():
            appels.append(True)
            return len(appels)>1
        bilan=I.importer_lot(self.chemins,self.conn,annulation=annuler)
        self.terminer(bilan)
        self.assertEqual(bilan.etat,'annule')
        self.assertFalse(C.est_retire(self.chemins[0]))
        self.assertTrue(C.est_retire(self.chemins[1]))
        empreinte=next(d['empreinte'] for d in self.documents if d['nom']==self.chemins[1].name)
        self.chemins[1].write_text('<autre/>')
        bilan=I.importer_lot([self.chemins[1]],self.conn)
        self.terminer(bilan)
        self.assertEqual(bilan.refuses,1)
        self.assertIn(empreinte,C.retraits())

    def test_worker_existant_transmet_ids_doublons_dans_bilan_final(self):
        tache=import_fond.TacheImport(self.chemins,self.base)
        self.addCleanup(lambda:tache.arreter(5))
        tache.demarrer()
        while True:
            evenement=tache.evenements.get(timeout=5)
            if evenement[0] in ('fin','erreur'):
                break
        self.assertTrue(tache.arreter(5))
        self.assertEqual(evenement[0],'fin')
        self.assertEqual(evenement[1].doublons,2)
        self.assertEqual(len(evenement[1].documents_traites),2)
        self.terminer(evenement[1])
        self.assertEqual(len(C.lister(self.conn)),2)


if __name__=='__main__':
    unittest.main()
