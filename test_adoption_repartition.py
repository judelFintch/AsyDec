"""Adoption d'une simulation sans recharger un XML externe ni choisir ses données en silence."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from pathlib import Path
import xml.etree.ElementTree as ET
import ui.outils as O


class AdoptionRepartitionTest(unittest.TestCase):
    def setUp(self):
        self.chemin = str(Path('archive.xml').resolve())
        self.autre = str(Path('autre.xml').resolve())
        self.proposition = {'controle': self.chemin, 'profil': {'signature': ['articles']},
                            'poids': [100]*8, 'fob': [50]*8, 'colis': list(range(10,18))}
        articles = SimpleNamespace(var_fob_total=Mock(), remplir=Mock())
        self.app = SimpleNamespace(base=None, session_verrouillee=False,
            xml_disponibles=Mock(return_value=[{'chemin':p,'nom':Path(p).name} for p in (self.chemin,self.autre)]),
            choisir_xml_disponibles=Mock(return_value=[self.autre]), ouvrir_base=Mock(return_value=True),
            choisir_reference=Mock(return_value=True), pages={'articles':articles}, montrer=Mock())
        self.page = SimpleNamespace(app=self.app, selection=Mock(return_value=self.proposition), message=Mock())
        self.page._ouvrir_dossier_proposition=lambda v: O.PageRepartitions._ouvrir_dossier_proposition(self.page,v)
        self.signature = patch.object(O.variantes,'signature',return_value=['articles']).start()
        self.charge = patch.object(O.moteur,'charger',return_value=ET.ElementTree(ET.fromstring(
            '<ASYCUDA><Valuation><Gs_external_freight><Amount_foreign_currency>25</Amount_foreign_currency>'
            '</Gs_external_freight></Valuation></ASYCUDA>'))).start()
        patch.object(O.moteur,'infos_dossier',return_value={'importateur':'IMPORTATEUR', 'reference':'REF', 'taux':2265.5}).start()
        self.confirmation = patch.object(O.messagebox,'askyesnocancel',return_value=True).start()
        self.addCleanup(patch.stopall)

    def test_confirmation_adopte_archive_puis_proposition(self):
        O.PageRepartitions.utiliser(self.page)
        texte = self.confirmation.call_args.args[1]
        for donnee in ('IMPORTATEUR','REF','2265.5','25','Assurance'):
            self.assertIn(donnee, texte)
        self.app.ouvrir_base.assert_called_once_with(self.chemin)
        self.app.choisir_xml_disponibles.assert_not_called()
        self.app.pages['articles'].remplir.assert_called_once_with([100]*8,[50]*8,list(range(10,18)),mode='SAISI')
        self.app.montrer.assert_called_once_with('verifier')

    def test_annulation_conserve_simulation_sans_ouvrir(self):
        self.confirmation.return_value=None
        O.PageRepartitions.utiliser(self.page)
        self.app.ouvrir_base.assert_not_called()
        self.app.pages['articles'].remplir.assert_not_called()
        self.app.montrer.assert_not_called()

    def test_autre_archive_confirmation_explicite(self):
        self.confirmation.side_effect=[False,True]
        O.PageRepartitions.utiliser(self.page)
        self.app.choisir_xml_disponibles.assert_called_once_with(generation=True)
        self.assertEqual(self.confirmation.call_count,2)
        self.app.ouvrir_base.assert_called_once_with(self.autre)

    def test_autre_archive_incompatible_ne_change_pas_dossier(self):
        self.confirmation.return_value=False
        self.signature.side_effect=[['articles'],['autres']]
        O.PageRepartitions.utiliser(self.page)
        self.app.ouvrir_base.assert_not_called()
        self.app.choisir_reference.assert_not_called()
        self.page.message.afficher.assert_called_once()

    def test_ouverture_echouee_nadopte_pas_proposition(self):
        self.app.ouvrir_base.return_value=False
        O.PageRepartitions.utiliser(self.page)
        self.app.choisir_reference.assert_not_called()
        self.app.pages['articles'].remplir.assert_not_called()

    def test_dossier_actif_reste_utilise(self):
        self.app.base='dossier-actif.xml'
        O.PageRepartitions.utiliser(self.page)
        self.app.ouvrir_base.assert_not_called()
        self.confirmation.assert_not_called()
        self.app.choisir_reference.assert_called_once()
        self.app.montrer.assert_called_once_with('verifier')

    def test_archive_retiree_ou_partielle_pas_adoptee(self):
        self.app.xml_disponibles.return_value=[]
        O.PageRepartitions.utiliser(self.page)
        self.confirmation.assert_not_called()
        self.app.ouvrir_base.assert_not_called()

    def test_session_verrouillee_pas_daction(self):
        self.app.session_verrouillee=True
        O.PageRepartitions.utiliser(self.page)
        self.app.xml_disponibles.assert_not_called()
        self.app.ouvrir_base.assert_not_called()


if __name__ == '__main__':
    unittest.main()
