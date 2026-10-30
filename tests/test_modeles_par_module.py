"""Les modèles Friperie ne doivent jamais être proposés dans Divers."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from asydec.calcul import variantes
from asydec.declarations import modeles_generes as M, correction_modele
from asydec.ui.modeles_generes import PageModelesGeneres
from asydec.ui.outils import PageHistorique
from tests import test_modeles_generes as fixtures


class ModelesParModuleTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ModelesGeneresTest(methodName='runTest')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def enregistrer(self, module):
        return M.enregistrer(self.f.resultat,self.f.source,'alice',base=self.f.base,module=module)

    def test_meme_xml_et_repartition_restent_distincts_selon_le_module(self):
        friperie, divers = self.enregistrer('friperie'), self.enregistrer('divers')
        self.assertNotEqual(friperie, divers)
        for module, identifiant in [('friperie',friperie),('divers',divers)]:
            lignes=M.lister(base=self.f.base,module=module)
            self.assertEqual([m['id'] for m in lignes],[identifiant])
            self.assertEqual(lignes[0]['resultat']['module'],module)
            self.assertEqual(self.enregistrer(module),identifiant)
        self.assertNotIn('module',self.f.resultat)  # aucun changement du dictionnaire de l'appelant

    def test_ancien_modele_sans_type_reste_uniquement_en_friperie(self):
        with M._connexion(self.f.base) as conn:
            identifiant=conn.execute('INSERT INTO modeles(empreinte,cree_utc,auteur,importateur,nom,resultat_json,base_xml,modele_xml) '
                'VALUES(?,?,?,?,?,?,?,?)',('ancien',M._maintenant(),'alice','IMPORT A','ancien.xml',
                json.dumps(self.f.resultat),self.f.source.read_bytes(),self.f.xml)).lastrowid
            M._evenement(conn,identifiant,'alice',M.CREATION,'en_attente')
        self.assertEqual([m['id'] for m in M.lister(base=self.f.base,module='friperie')],[identifiant])
        self.assertEqual(M.lister(base=self.f.base,module='divers'),[])

    def test_bons_modeles_ne_traversent_pas_les_modules(self):
        identifiant=self.enregistrer('friperie')
        M.marquer_bon(identifiant,'alice',True,base=self.f.base)
        signature=variantes.signature(self.f.source)
        self.assertEqual(len(M.bons_modeles(signature,base=self.f.base,module='friperie')),1)
        self.assertEqual(M.bons_modeles(signature,base=self.f.base,module='divers'),[])

    def test_reprise_depuis_une_ancienne_fiche_bloquee_dans_autre_module(self):
        identifiant=self.enregistrer('friperie')
        page=SimpleNamespace(app=SimpleNamespace(session_verrouillee=False,module_travail='divers'))
        with patch.object(M,'BASE',self.f.base), patch('asydec.ui.modeles_generes.messagebox.showerror') as erreur, \
             patch('asydec.ui.reprise_modele.reprendre') as reprendre:
            PageModelesGeneres.reprendre(page,identifiant)
        reprendre.assert_not_called()
        erreur.assert_called_once()

    def test_historique_filtre_tous_les_exports_du_modele(self):
        identifiant=self.enregistrer('divers')
        historique=self.f.racine/'IMP'/'1 - HISTORIQUE'
        historique.mkdir(parents=True)
        ancien=historique/'friperie.xml'
        ancien.write_bytes(self.f.xml)
        export=historique/'divers.xml'
        export.write_bytes(self.f.xml)
        with M._connexion(self.f.base) as conn:
            M._rattacher_export(conn,identifiant,'alice',export)
            # Un autre export ne doit pas faire perdre le classement de l'ancien.
            autre=self.f.racine/'telechargement.xml'
            autre.write_bytes(self.f.xml)
            M._rattacher_export(conn,identifiant,'alice',autre)
        with patch.object(M,'BASE',self.f.base),patch('asydec.ui.outils.generer.DEC',self.f.racine):
            for module, attendu in [('friperie',ancien),('divers',export)]:
                page=SimpleNamespace(app=SimpleNamespace(module_travail=module))
                self.assertEqual([p for _,_,p in PageHistorique.fichiers(page)],[attendu])
