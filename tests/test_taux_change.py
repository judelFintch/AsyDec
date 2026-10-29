"""Le taux provient du XML et exige une confirmation par contexte en session."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

from asydec.ui.app import AsyDec
from asydec.ui.outils import PageRepartitions
from asydec.ui.taux_change import confirmer
from tests.test_references import declaration, item


class TauxChangeTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source=Path(self.temp.name)/'base.xml'
        self.source.write_bytes(declaration([item()]))
        self.app=SimpleNamespace(session_verrouillee=False)

    def modifier(self,chemin,valeur):
        arbre=ET.parse(self.source)
        arbre.getroot().find(chemin).text=valeur
        arbre.write(self.source)

    def test_confirmation_non_repetee_puis_taux_modifie_reconfirme(self):
        with patch('asydec.ui.taux_change.messagebox.askyesno',return_value=True) as dialogue:
            self.assertTrue(confirmer(self.app,[self.source]))
            self.assertTrue(confirmer(self.app,[self.source]))
            self.assertEqual(dialogue.call_count,1)
            self.modifier('Valuation/Gs_Invoice/Currency_rate','2500')
            self.assertTrue(confirmer(self.app,[self.source]))
            self.assertEqual(dialogue.call_count,2)
            self.assertIn('2500',dialogue.call_args.args[1])

    def test_refus_non_memorise_et_verrouillage(self):
        with patch('asydec.ui.taux_change.messagebox.askyesno',return_value=False) as dialogue:
            self.assertFalse(confirmer(self.app,[self.source]))
            self.assertFalse(confirmer(self.app,[self.source]))
            self.assertEqual(dialogue.call_count,2)
            self.app.session_verrouillee=True
            self.assertFalse(confirmer(self.app,[self.source]))
            self.assertEqual(dialogue.call_count,2)

    def test_taux_invalide_pas_de_confirmation(self):
        for taux in ('0','-1','NaN',''):
            self.modifier('Valuation/Gs_Invoice/Currency_rate',taux)
            with patch('asydec.ui.taux_change.messagebox.askyesno') as dialogue:
                with self.assertRaises(ValueError):
                    confirmer(self.app,[self.source])
                dialogue.assert_not_called()

    def test_plusieurs_taux_affiches_avant_predictions(self):
        autre=Path(self.temp.name)/'autre.xml'
        autre.write_bytes(self.source.read_bytes().replace(b'2265.5',b'2500'))
        with patch('asydec.ui.taux_change.messagebox.askyesno',return_value=True) as dialogue:
            confirmer(self.app,[self.source,autre])
        self.assertIn('2265.5',dialogue.call_args.args[1])
        self.assertIn('2500',dialogue.call_args.args[1])

    def test_calcul_et_export_revalides_avant_produire(self):
        self.app.base=str(self.source)
        self.app.pages={'articles':SimpleNamespace(valeurs=Mock(return_value={
            'poids':[100], 'mode':'SAISI','fob_total':150,'fob':[150],'colis_total':10,'colis':[10]}))}
        self.app.profil={'ratios':[1.5]}
        self.app.table_imp=[]
        with patch('asydec.ui.taux_change.messagebox.askyesno',return_value=False),patch('asydec.ui.app.generer.produire') as produire:
            with self.assertRaises(ValueError):
                AsyDec.calculer(self.app)
            produire.assert_not_called()
        with patch('asydec.ui.taux_change.messagebox.askyesno',return_value=True) as dialogue, \
             patch('asydec.ui.app.generer.produire',return_value={'resume':{}}), \
             patch('asydec.ui.app.generer.lire_registre',return_value={}),patch('asydec.ui.app.generer.ecrire_registre'):
            AsyDec.calculer(self.app)
            self.modifier('Valuation/Gs_Invoice/Currency_rate','2500')
            AsyDec.calculer(self.app,enregistrer=True)
            self.assertEqual(dialogue.call_count,2)

    def test_repartitions_refus_avant_recherche_fiscale(self):
        self.app.chemins_xml_disponibles=Mock(return_value=[str(self.source)])
        page=SimpleNamespace(app=self.app,champs={k:Mock(get=Mock(return_value=v)) for k,v in
            (('fob','150'),('poids','100'),('colis','108'))},message=Mock(),update_idletasks=Mock(),
            deja_vues={},selection_modeles=None)
        with patch('asydec.ui.taux_change.messagebox.askyesno',return_value=False), \
             patch('asydec.ui.outils.variantes.rechercher_modeles') as chercher:
            PageRepartitions.rechercher(page)
        chercher.assert_not_called()


if __name__=='__main__':
    unittest.main()
