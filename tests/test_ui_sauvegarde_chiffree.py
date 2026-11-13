from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from asydec.ui.sauvegarde_chiffree import PageSauvegardeChiffree
from asydec.ui import sauvegarde_chiffree as UI


class ParcoursSauvegardeTest(TestCase):
    def setUp(self):
        self.page = object.__new__(PageSauvegardeChiffree)
        self.page.app = SimpleNamespace(session_verrouillee=False)
        self.page.occupe = False
        self.page.mdp = Mock(get=Mock(return_value=''))
        self.page.confirmation = Mock(get=Mock(return_value=''))
        self.page.jeton = Mock(get=Mock(return_value=''))
        self.page.choix = Mock(current=Mock(return_value=0))
        self.page.sauvegardes = [dict(id=1, nom='test.asydec.enc', taille=100)]
        self.page.travailler = Mock()

    def test_mot_de_passe_demande_avant_telechargement(self):
        with patch.object(UI.messagebox, 'showerror'), \
             patch.object(self.page, '_confirmer_import') as confirmer:
            self.page.recuperer()
        confirmer.assert_not_called()
        self.page.travailler.assert_not_called()

    def test_refus_remplacement_ne_telecharge_pas(self):
        self.page.mdp.get.return_value = 'phrase-secrete-de-test'
        with patch.object(self.page, '_confirmer_import', return_value=False):
            self.page.recuperer()
        self.page.travailler.assert_not_called()

    def test_session_verrouillee_ne_telecharge_pas(self):
        self.page.app.session_verrouillee = True
        self.page.recuperer()
        self.page.travailler.assert_not_called()

    def test_creation_exige_confirmation_du_mot_de_passe(self):
        self.page.mdp.get.return_value = 'phrase-secrete-de-test'
        self.page.confirmation.get.return_value = 'autre-phrase-de-test'
        with patch.object(UI.messagebox, 'showerror'), \
             patch.object(UI.filedialog, 'asksaveasfilename') as choisir:
            self.page.exporter()
        choisir.assert_not_called()
        self.page.travailler.assert_not_called()
